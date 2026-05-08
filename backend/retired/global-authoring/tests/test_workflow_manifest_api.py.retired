from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.schemas.workflow import WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH


def _seed_manifest_agent(
    session_factory: sessionmaker[Session],
    *,
    agent_key: str = "manifest_api_agent",
) -> None:
    with session_factory() as session:
        output_schema = OutputSchema(
            key=f"{agent_key}_output",
            version=1,
            status="published",
            kind="standalone",
            name=f"{agent_key} Output",
            description="Output schema for workflow manifest API tests.",
            json_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
            registry_refs=[],
        )
        session.add(output_schema)
        session.flush()
        session.add(
            Agent(
                key=agent_key,
                version=1,
                status="published",
                name=f"{agent_key} Agent",
                description="Agent for workflow manifest API tests.",
                model_connection_id=1,
                model="openai:gpt-5.4-mini",
                system_prompt="Summarize the ticker.",
                input_schema={
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                    "additionalProperties": False,
                },
                output_schema_id=output_schema.id,
                output_schema_version=output_schema.version,
                capabilities=[],
                mcp_servers=[],
                budget_usd=Decimal("0.05000000"),
            )
        )
        session.commit()


def _manifest_source(
    *,
    key: str = "manifest_api_workflow",
    name: str = "Manifest API Workflow",
    description: str = "Writes from YAML source.",
    uses: str = "manifest_api_agent@1",
    output_reference: str = "${{ steps.research.outputs.analysis }}",
) -> str:
    return f"""apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: {key}
  name: {name}
  description: {description}
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
steps:
  - id: research
    agents:
      - slot: analysis
        uses: {uses}
        with:
          ticker: ${{{{ inputs.ticker }}}}
output:
  from: {output_reference}
"""


def _v2_manifest_source(
    *,
    key: str = "manifest_api_workflow_v2",
    name: str = "Manifest API Workflow V2",
    description: str = "Writes v2 graph metadata from YAML source.",
    uses: str = "manifest_api_agent@1",
    output_reference: str = "${{ nodes.research.outputs.analysis.summary }}",
) -> str:
    return f"""apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: {key}
  name: {name}
  description: {description}
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
  uses: {uses}
  with:
    ticker: ${{{{ inputs.ticker }}}}
output:
  from: {output_reference}
"""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _create_manifest_workflow(client: TestClient, source: str) -> dict[str, object]:
    response = client.post("/api/workflows", json={"manifestSource": source})
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


@pytest.mark.parametrize(
    "path",
    ["/api/workflows/validate-manifest", "/api/workflows", "/api/workflows/1"],
)
def test_manifest_source_rejects_oversized_payloads(client: TestClient, path: str) -> None:
    oversized_source = "a" * (WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH + 1)

    response = client.post(path, json={"manifestSource": oversized_source})

    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    assert body["code"] == "validation_error"
    assert details[0]["field"] == "manifestSource"
    assert "at most" in str(details[0]["issue"])


def test_validate_manifest_returns_diagnostics_metadata_compiled_payload_and_input_preview(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = _manifest_source()

    response = client.post("/api/workflows/validate-manifest", json={"manifestSource": source})

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["diagnostics"] == []
    assert body["metadata"] == {
        "apiVersion": "ledger.workflow/v1",
        "key": "manifest_api_workflow",
        "name": "Manifest API Workflow",
        "description": "Writes from YAML source.",
    }
    compiled_payload = cast(dict[str, object], body["compiledPayload"])
    compiled_steps = cast(list[dict[str, object]], compiled_payload["steps"])
    compiled_agents = cast(list[dict[str, object]], compiled_steps[0]["agents"])
    assert compiled_payload["key"] == "manifest_api_workflow"
    assert "compiledGraph" not in compiled_payload
    assert "compiledGraph" not in body
    assert compiled_agents[0]["agentKey"] == "manifest_api_agent"
    assert compiled_agents[0]["agentVersion"] == 1
    assert cast(dict[str, object], body["runInputSchema"])["additionalProperties"] is False


def test_validate_v2_manifest_returns_separate_compiled_graph(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = _v2_manifest_source()

    response = client.post("/api/workflows/validate-manifest", json={"manifestSource": source})

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["diagnostics"] == []
    assert body["metadata"] == {
        "apiVersion": "ledger.workflow/v2",
        "key": "manifest_api_workflow_v2",
        "name": "Manifest API Workflow V2",
        "description": "Writes v2 graph metadata from YAML source.",
    }
    compiled_payload = cast(dict[str, object], body["compiledPayload"])
    compiled_graph = cast(dict[str, object], body["compiledGraph"])
    assert compiled_payload["key"] == "manifest_api_workflow_v2"
    assert "compiledGraph" not in compiled_payload
    assert compiled_graph["apiVersion"] == "ledger.workflow/v2"
    assert compiled_graph["rootNodeId"] == "research"
    assert cast(dict[str, object], compiled_graph["output"])["path"] == "summary"
    assert "secret" not in _canonical_json(compiled_graph).lower()
    assert "system_prompt" not in _canonical_json(compiled_graph).lower()


def test_validate_manifest_rejects_unsupported_input_schema_keywords(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: manifest_api_workflow
  name: Manifest API Workflow
  description: Writes from YAML source.
inputSchema:
  type: object
  patternProperties:
    ^x:
      type: string
  properties:
    ticker:
      type: string
  required:
    - ticker
steps:
  - id: research
    agents:
      - slot: analysis
        uses: manifest_api_agent@1
        with:
          ticker: ${{ inputs.ticker }}
output:
  from: ${{ steps.research.outputs.analysis }}
"""

    assert "patternProperties" in source

    response = client.post("/api/workflows/validate-manifest", json={"manifestSource": source})

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["metadata"] is None
    assert body["compiledPayload"] is None
    assert body["runInputSchema"] is None
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == "error"
    assert str(diagnostics[0]["path"]).startswith("inputSchema")
    assert diagnostics[0]["line"] is not None
    assert diagnostics[0]["column"] is not None
    assert "patternProperties" in str(diagnostics[0]["message"])


def test_validate_manifest_returns_location_aware_service_diagnostics(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/workflows/validate-manifest",
        json={"manifestSource": _manifest_source(uses="missing_manifest_agent@1")},
    )

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["metadata"] is None
    assert body["compiledPayload"] is None
    assert body["runInputSchema"] is None
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == "error"
    assert diagnostics[0]["path"] == "steps[0].agents[0].uses"
    assert diagnostics[0]["line"] is not None
    assert diagnostics[0]["column"] is not None
    assert "missing_manifest_agent" in str(diagnostics[0]["message"])


def test_create_workflow_from_manifest_persists_source_and_compiled_execution_fields(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = _manifest_source()

    created = _create_manifest_workflow(client, source)

    created_steps = cast(list[dict[str, object]], created["steps"])
    created_agents = cast(list[dict[str, object]], created_steps[0]["agents"])
    output_spec = cast(dict[str, object], created["outputSpec"])
    assert created["manifestApiVersion"] == "ledger.workflow/v1"
    assert created["manifestSource"] == source
    assert cast(dict[str, object], created["inputSchema"])["additionalProperties"] is False
    assert created_agents[0]["agentKey"] == "manifest_api_agent"
    assert created_agents[0]["agentVersion"] == 1
    assert created_agents[0]["outputSchemaVersion"] == 1
    assert created_agents[0]["budgetUsd"] == "0.05000000"
    assert output_spec["agentKey"] == "manifest_api_agent"
    assert output_spec["outputSchemaVersion"] == 1
    assert created["aggregateBudgetUsd"] == "0.05000000"


def test_create_v2_workflow_from_manifest_returns_persisted_compiled_graph(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = _v2_manifest_source()

    created = _create_manifest_workflow(client, source)

    output_spec = cast(dict[str, object], created["outputSpec"])
    compiled_graph = cast(dict[str, object], created["compiledGraph"])
    assert created["manifestApiVersion"] == "ledger.workflow/v2"
    assert created["manifestSource"] == source
    assert "compiledGraph" not in output_spec
    assert compiled_graph["rootNodeId"] == "research"
    assert cast(dict[str, object], compiled_graph["output"])["path"] == "summary"

    response = client.get(f"/api/workflows/{created['id']}")

    assert response.status_code == 200, response.json()
    detail = cast(dict[str, object], response.json())
    assert detail["manifestApiVersion"] == "ledger.workflow/v2"
    assert detail["manifestSource"] == source
    assert _canonical_json(detail["compiledGraph"]) == _canonical_json(compiled_graph)
    assert "compiledGraph" not in cast(dict[str, object], detail["outputSpec"])


def test_update_workflow_from_manifest_persists_new_source_and_creates_new_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    original_source = _manifest_source()
    created = _create_manifest_workflow(client, original_source)
    updated_source = _manifest_source(
        name="Manifest API Workflow v2",
        description="Updates from a new YAML source.",
        output_reference="${{ steps.research.outputs.analysis.summary }}",
    )

    response = client.post(
        f"/api/workflows/{created['id']}",
        json={"manifestSource": updated_source},
    )

    assert response.status_code == 200, response.json()
    updated = cast(dict[str, object], response.json())
    output_spec = cast(dict[str, object], updated["outputSpec"])
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["name"] == "Manifest API Workflow v2"
    assert updated["manifestSource"] == updated_source
    assert output_spec["path"] == "summary"

    previous_response = client.get(f"/api/workflows/{updated['id']}", params={"version": 1})
    assert previous_response.status_code == 200, previous_response.json()
    previous = cast(dict[str, object], previous_response.json())
    assert previous["id"] == created["id"]
    assert previous["status"] == "deprecated"
    assert previous["manifestSource"] == original_source


def test_workflow_detail_reads_persisted_manifest_source(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_manifest_agent(session_factory)
    source = _manifest_source()
    created = _create_manifest_workflow(client, source)

    response = client.get(f"/api/workflows/{created['id']}")

    assert response.status_code == 200, response.json()
    detail = cast(dict[str, object], response.json())
    assert detail["manifestApiVersion"] == "ledger.workflow/v1"
    assert detail["manifestSource"] == source
