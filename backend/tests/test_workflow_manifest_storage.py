# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp import DefaultMcpConnectionTester
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.workflow import (
    TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
    WORKFLOW_MANIFEST_API_VERSION,
    Workflow,
)
from app.schemas.workflow import WorkflowCreate, WorkflowCreateRequest, WorkflowUpdate
from app.schemas.workflow_manifest import WORKFLOW_MANIFEST_V2_API_VERSION
from app.services.agent_service import AgentService
from app.services.workflow_manifest_compiler import compile_workflow_manifest
from app.services.workflow_manifest_decompiler import decompile_workflow_model
from app.services.workflow_service import WorkflowService
from tests.test_agent_manifest_compiler import _seed_platform_graph_manifest_refs
from tests.test_workflow_manifest_parser import (
    GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES,
    GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
)


def _workflow_input_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
        "additionalProperties": False,
    }


def _agent_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }


def _seed_agent(session: Session) -> None:
    model_connection = ModelConnection(
        key="manifest_contract_model",
        status="active",
        name="Manifest Contract Model",
        description="Model connection for workflow manifest storage tests.",
        base_url="https://api.openai.com/v1",
        model_id="gpt-5.4-mini",
        reasoning_effort="medium",
        timeout_seconds=60,
        secret_payload={"apiKey": "configured-test-value"},
    )
    output_schema = OutputSchema(
        key="manifest_contract_note",
        version=1,
        status="published",
        kind="standalone",
        name="Manifest Contract Note",
        description="Output schema for workflow manifest storage tests.",
        json_schema=_agent_output_schema(),
        registry_refs=[],
    )
    session.add_all([model_connection, output_schema])
    session.flush()
    session.add(
        Agent(
            key="manifest_contract_agent",
            version=1,
            status="published",
            name="Manifest Contract Agent",
            description="Agent for workflow manifest storage tests.",
            model_connection_id=model_connection.id,
            model="openai:gpt-5.4-mini",
            system_prompt="Summarize the ticker.",
            input_schema=_workflow_input_schema(),
            output_schema_id=output_schema.id,
            output_schema_version=output_schema.version,
            capabilities=[],
            mcp_servers=[],
            budget_usd=Decimal("0.05000000"),
        )
    )
    session.commit()


def _agent_service(session: Session) -> AgentService:
    return AgentService(
        session,
        get_default_tool_catalog(),
        DefaultMcpConnectionTester(),
    )


def _seed_platform_graph_agents(session: Session) -> None:
    _seed_platform_graph_manifest_refs(session)
    agent_service = _agent_service(session)
    for source in GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES.values():
        _ = agent_service.create_agent_from_manifest(source)


def _workflow_create_payload() -> dict[str, object]:
    return {
        "key": "manifest_contract_workflow",
        "name": "Manifest Contract Workflow",
        "description": "Legacy workflow payload path stores a temporary manifest source.",
        "inputSchema": _workflow_input_schema(),
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": "manifest_contract_agent",
                        "slot": "analysis",
                        "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                    }
                ],
            }
        ],
        "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
    }


def _workflow_update_payload() -> dict[str, object]:
    payload = _workflow_create_payload()
    _ = payload.pop("key")
    payload["name"] = "Manifest Contract Workflow v2"
    payload["description"] = "Updated legacy payload path keeps manifest placeholders readable."
    return payload


def _v2_manifest_source() -> str:
    return """apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: manifest_contract_workflow_v2
  name: Manifest Contract Workflow V2
  description: V2 graph metadata persists alongside execution fields.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
flow:
  kind: step
  id: research
  slot: analysis
  uses: manifest_contract_agent@1
  with:
    ticker: ${{ inputs.ticker }}
output:
  from: ${{ nodes.research.outputs.analysis.summary }}
"""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_workflow_service_persists_manifest_placeholder_and_read_schema_aliases(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        service = WorkflowService(session)

        created = service.create_workflow(WorkflowCreate.model_validate(_workflow_create_payload()))
        created_payload = created.model_dump(mode="json", by_alias=True)
        created_row = session.get(Workflow, created.id)

        assert created_row is not None
        assert created.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
        assert created.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
        assert created_payload["manifestApiVersion"] == WORKFLOW_MANIFEST_API_VERSION
        assert created_payload["manifestSource"] == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
        assert created_row.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
        assert created_row.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE

        updated = service.update_workflow(
            created.id,
            WorkflowUpdate.model_validate(_workflow_update_payload()),
        )
        latest_list = service.list_workflows().items
        previous = service.get_workflow(updated.id, version=1)

        assert updated.version == 2
        assert updated.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
        assert updated.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
        assert latest_list[0].id == updated.id
        assert latest_list[0].manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
        assert previous.id == created.id
        assert previous.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
        assert previous.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE


def test_workflow_service_persists_v2_source_version_and_compiled_graph(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        service = WorkflowService(session)
        source = _v2_manifest_source()
        expected_graph = cast(dict[str, object], compile_workflow_manifest(source)["compiledGraph"])

        created = service.create_workflow(
            WorkflowCreateRequest.model_validate({"manifestSource": source})
        )
        created_row = session.get(Workflow, created.id)
        detail = service.get_workflow(created.id)

        assert created_row is not None
        assert created.manifest_api_version == WORKFLOW_MANIFEST_V2_API_VERSION
        assert created.manifest_source == source
        assert created.compiled_graph is not None
        assert detail.compiled_graph is not None
        assert created_row.manifest_api_version == WORKFLOW_MANIFEST_V2_API_VERSION
        assert created_row.manifest_source == source
        assert "compiledGraph" not in created.output_spec.model_dump(mode="json", by_alias=True)
        assert "compiledGraph" in created_row.output_spec
        stored_graph = cast(dict[str, object], created_row.output_spec["compiledGraph"])
        assert _canonical_json(created.compiled_graph) == _canonical_json(expected_graph)
        assert _canonical_json(detail.compiled_graph) == _canonical_json(expected_graph)
        assert _canonical_json(stored_graph) == _canonical_json(expected_graph)
        assert "secret" not in _canonical_json(stored_graph).lower()


def test_workflow_service_persists_platform_graph_v2_review_examples_with_compiled_graph(
    session_factory: sessionmaker[Session],
) -> None:
    examples = [
        (
            GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_strict_sequential_review",
            17,
        ),
        (
            GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_practical_fanout_review",
            14,
        ),
    ]
    with session_factory() as session:
        _seed_platform_graph_agents(session)
        service = WorkflowService(session)

        for source, expected_key, expected_step_count in examples:
            created = service.create_workflow(
                WorkflowCreateRequest.model_validate({"manifestSource": source})
            )
            created_row = session.get(Workflow, created.id)
            assert created_row is not None

            assert created.key == expected_key
            assert created.manifest_api_version == WORKFLOW_MANIFEST_V2_API_VERSION
            assert created.manifest_source == source
            assert len(created.steps) == expected_step_count
            assert created.compiled_graph is not None
            assert created.compiled_graph["apiVersion"] == WORKFLOW_MANIFEST_V2_API_VERSION
            assert "postRunMemory" in created.compiled_graph
            assert "compiledGraph" not in created.output_spec.model_dump(mode="json", by_alias=True)
            assert "compiledGraph" in created_row.output_spec
            stored_graph = cast(dict[str, object], created_row.output_spec["compiledGraph"])
            serialized_graph = _canonical_json(stored_graph)
            assert "sk-" not in serialized_graph
            assert "apiKey" not in serialized_graph
            assert "secret" not in serialized_graph.lower()


def test_workflow_service_persists_and_decompiles_platform_graph_v1_review_examples(
    session_factory: sessionmaker[Session],
) -> None:
    examples = [
        (
            GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_strict_sequential_review",
            14,
        ),
        (
            GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_practical_fanout_review",
            11,
        ),
    ]
    with session_factory() as session:
        _seed_platform_graph_agents(session)
        service = WorkflowService(session)

        for source, expected_key, expected_step_count in examples:
            created = service.create_workflow(
                WorkflowCreateRequest.model_validate({"manifestSource": source})
            )
            created_row = session.get(Workflow, created.id)
            assert created_row is not None

            decompiled = decompile_workflow_model(created_row, verify_lossless=False)
            compiled_source = compile_workflow_manifest(source)
            compiled_decompiled = compile_workflow_manifest(decompiled.source)
            compiled_decompiled_steps = cast(
                list[dict[str, object]],
                compiled_decompiled["steps"],
            )

            assert created.key == expected_key
            assert created.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
            assert created.manifest_source == source
            assert created_row.manifest_source == source
            assert len(created.steps) == expected_step_count
            assert len(compiled_decompiled_steps) == expected_step_count
            assert compiled_decompiled["key"] == expected_key
            assert compiled_decompiled["outputSpec"] == compiled_source["outputSpec"]
            assert decompiled.source.startswith("apiVersion: ledger.workflow/v1\n")
