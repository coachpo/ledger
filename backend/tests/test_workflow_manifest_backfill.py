# pyright: reportMissingImports=false
# ruff: noqa: E402

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skip(
    reason="Retired global workflow authoring is not a live platform surface"
)

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.workflow import (
    TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
    WORKFLOW_MANIFEST_API_VERSION,
    Workflow,
)
from app.schemas.workflow import WorkflowCreate
from app.services.workflow_manifest_backfill import (
    WorkflowManifestBackfillError,
    WorkflowManifestBackfillService,
)
from app.services.workflow_manifest_compiler import compile_workflow_manifest
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
    model_connection = ModelConnection(
        key="backfill_model",
        status="active",
        name="Backfill Model",
        description="Model connection for workflow manifest backfill tests.",
        base_url="https://api.openai.com/v1",
        model_id="gpt-5.4-mini",
        reasoning_effort="medium",
        timeout_seconds=60,
        secret_payload={"apiKey": "configured-test-value"},
    )
    output_schema = OutputSchema(
        key="backfill_note",
        version=1,
        status="published",
        kind="standalone",
        name="Backfill Note",
        description="Output schema for workflow manifest backfill tests.",
        json_schema=_agent_output_schema(),
        registry_refs=[],
    )
    session.add_all([model_connection, output_schema])
    session.flush()
    session.add(
        Agent(
            key="backfill_agent",
            version=1,
            status="published",
            name="Backfill Agent",
            description="Agent for workflow manifest backfill tests.",
            model_connection_id=model_connection.id,
            model="openai:gpt-5.4-mini",
            system_prompt="Summarize the ticker.",
            input_schema=_workflow_input_schema(),
            output_schema_id=output_schema.id,
            output_schema_version=output_schema.version,
            capabilities=[],
            mcp_servers=[],
        )
    )
    session.commit()


def _workflow_payload(key: str) -> dict[str, object]:
    return {
        "key": key,
        "name": key.replace("_", " ").title(),
        "description": "Backfill converts this legacy compiled payload to YAML.",
        "inputSchema": _workflow_input_schema(),
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": "backfill_agent",
                        "slot": "analysis",
                        "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                    }
                ],
            }
        ],
        "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
    }


def _create_workflow(session: Session, key: str) -> Workflow:
    created = WorkflowService(session).create_workflow(
        WorkflowCreate.model_validate(_workflow_payload(key))
    )
    workflow = session.get(Workflow, created.id)
    assert workflow is not None
    return workflow


def _make_workflow_lossy(session: Session, workflow: Workflow) -> None:
    workflow.output_spec = {**workflow.output_spec, "kind": "agent"}
    session.commit()


def test_workflow_manifest_backfill_dry_run_reports_counts_without_writes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        workflow = _create_workflow(session, "dry_run_workflow")

        report = WorkflowManifestBackfillService(session).audit()
        session.refresh(workflow)

        assert report.total == 1
        assert report.converted == 1
        assert report.failed == 0
        assert report.persisted == 0
        assert workflow.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE


def test_workflow_manifest_backfill_persists_lossless_manifest_source_and_detail_reads_it(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        workflow = _create_workflow(session, "persist_workflow")

        report = WorkflowManifestBackfillService(session).audit(persist=True)
        session.refresh(workflow)
        detail = WorkflowService(session).get_workflow(workflow.id)

        assert report.total == 1
        assert report.converted == 1
        assert report.failed == 0
        assert report.persisted == 1
        assert workflow.manifest_api_version == WORKFLOW_MANIFEST_API_VERSION
        assert workflow.manifest_source.startswith(
            "apiVersion: signaldeck.workflow/v1\nkind: Workflow\n"
        )
        assert detail.manifest_source == workflow.manifest_source
        assert compile_workflow_manifest(workflow.manifest_source)["key"] == "persist_workflow"


def test_workflow_manifest_backfill_reports_lossy_failures_by_workflow_identity(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        workflow = _create_workflow(session, "lossy_workflow")
        _make_workflow_lossy(session, workflow)

        report = WorkflowManifestBackfillService(session).audit()
        session.refresh(workflow)

        assert report.total == 1
        assert report.converted == 0
        assert report.failed == 1
        assert report.persisted == 0
        assert [(failure.key, failure.version) for failure in report.failures] == [
            ("lossy_workflow", 1)
        ]
        assert workflow.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE


def test_workflow_manifest_backfill_fail_on_lossy_rolls_back_without_partial_writes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent(session)
        good_workflow = _create_workflow(session, "good_workflow")
        lossy_workflow = _create_workflow(session, "bad_workflow")
        _make_workflow_lossy(session, lossy_workflow)

        with pytest.raises(WorkflowManifestBackfillError) as excinfo:
            _ = WorkflowManifestBackfillService(session).audit(persist=True, fail_on_lossy=True)
        report = excinfo.value.report
        session.refresh(good_workflow)
        session.refresh(lossy_workflow)

        assert report.total == 2
        assert report.converted == 1
        assert report.failed == 1
        assert report.persisted == 0
        assert [(failure.key, failure.version) for failure in report.failures] == [
            ("bad_workflow", 1)
        ]
        assert good_workflow.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
        assert lossy_workflow.manifest_source == TEMPORARY_WORKFLOW_MANIFEST_SOURCE
