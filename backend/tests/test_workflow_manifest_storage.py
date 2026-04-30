from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.upgrades import upgrade_legacy_schema
from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.models.workflow import (
    TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
    WORKFLOW_MANIFEST_API_VERSION,
    Workflow,
)
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services.workflow_service import WorkflowService


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
    session.add(output_schema)
    session.flush()
    session.add(
        Agent(
            key="manifest_contract_agent",
            version=1,
            status="published",
            name="Manifest Contract Agent",
            description="Agent for workflow manifest storage tests.",
            model_connection_id=1,
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


def test_upgrade_legacy_schema_adds_workflow_manifest_columns_idempotently(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            _ = connection.exec_driver_sql(
                """
                CREATE TABLE workflows (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    input_schema JSONB NOT NULL,
                    steps JSONB NOT NULL,
                    output_spec JSONB NOT NULL,
                    aggregate_budget_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_workflows_key_version UNIQUE (key, version)
                )
                """
            )
            _ = connection.execute(
                text(
                    """
                    INSERT INTO workflows (
                        key, version, status, name, description, input_schema, steps,
                        output_spec, aggregate_budget_usd
                    ) VALUES (
                        :key, 1, 'published', :name, '', CAST(:input_schema AS jsonb),
                        CAST(:steps AS jsonb), CAST(:output_spec AS jsonb), 0
                    )
                    """
                ),
                {
                    "key": "legacy_manifest_workflow",
                    "name": "Legacy Manifest Workflow",
                    "input_schema": json.dumps(_workflow_input_schema()),
                    "steps": json.dumps([]),
                    "output_spec": json.dumps({"kind": "slot", "stepIndex": 1, "slot": "analysis"}),
                },
            )

        upgrade_legacy_schema(engine)
        upgrade_legacy_schema(engine)

        workflow_columns = {
            column["name"]: column for column in inspect(engine).get_columns("workflows")
        }
        with engine.connect() as connection:
            stored_manifest = connection.execute(
                text(
                    """
                    SELECT manifest_api_version, manifest_source
                    FROM workflows
                    WHERE key = :key
                    """
                ),
                {"key": "legacy_manifest_workflow"},
            ).one()

        assert "manifest_api_version" in workflow_columns
        assert "manifest_source" in workflow_columns
        assert workflow_columns["manifest_api_version"]["nullable"] is False
        assert workflow_columns["manifest_source"]["nullable"] is False
        assert stored_manifest == (
            WORKFLOW_MANIFEST_API_VERSION,
            TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
        )
    finally:
        engine.dispose()
