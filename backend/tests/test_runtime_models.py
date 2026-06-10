from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.exc import IntegrityError

from app.models.agent_memory import (
    AgentMemoryChunk,
    AgentMemoryEmbedding,
    AgentMemoryEntry,
    AgentMemoryRevision,
    RunMemoryEvent,
)
from app.models.base import Base
from app.models.model_connection import ModelConnection
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.schemas.model_connection import default_model_connection_capabilities
from app.schemas.run import (
    RunListItemRead,
    RunMemoryArtifactRead,
    RunMemoryEventRead,
    RunPackageResolvedModelConnectionRead,
    RunRead,
    RunScheduleProvenanceRead,
    RunStatus,
)

UTC_TZ = timezone.utc  # noqa: UP017

RETIRED_GLOBAL_AUTHORING_TABLE_NAMES = {
    "agents",
    "workflows",
    "capabilities",
    "mcp_servers",
    "output_schemas",
    "workflow_agent_refs",
    "agent_capability_refs",
    "agent_mcp_server_refs",
}
LEGACY_BACKEND_TABLE_NAMES = {
    "agent_specs",
    "workflow_specs",
    "persona_profiles",
    "capability_registry_entries",
    "runtime_runs",
    "runtime_trace_events",
    "runtime_approvals",
    "runtime_checkpoints",
    "runtime_run_artifacts",
    "persona_projection_events",
    "orchestration_roles",
    "orchestration_characters",
}
AGENT_PLATFORM_PACKAGE_TABLE_NAMES = {
    "workflow_packages",
    "workflow_package_runtime_input_entries",
    "workflow_package_secret_bindings",
}
AGENT_PLATFORM_EXECUTION_TABLE_NAMES = {
    "runs",
    "run_workflow_package_snapshots",
    "run_steps",
    "run_agent_invocations",
    "run_operation_invocations",
    "run_forks",
}
CORE_MEMORY_TABLE_NAMES = {
    "agent_memory_entries",
    "agent_memory_revisions",
    "agent_memory_chunks",
    "agent_memory_embeddings",
    "run_memory_events",
}
REMOVED_WORKFLOW_PACKAGE_VERSION_TABLE_NAMES = {
    "workflow_package_versions",
    "workflow_package_version_model_connections",
}


def _build_run(
    *,
    target_id: int,
    target_key: str,
    status: str,
    final_output: object | None,
    total_tokens: int,
    trace_id: str | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    error: str | None = None,
    workflow_key: str = "runtime_workflow",
) -> Run:
    run = Run(
        target_kind="workflowPackage",
        target_id=target_id,
        target_key=target_key,
        target_version=1,
        workflow_package_id=target_id,
        workflow_package_key=target_key,
        workflow_package_workflow_key=workflow_key,
        input={"ticker": "NVDA", "horizonDays": 30},
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        trace_id=trace_id,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=target_id,
        workflow_package_key=target_key,
        workflow_package_name=target_key,
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key=workflow_key,
        workflow_name=workflow_key,
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=f"apiVersion: signaldeck.workflowPackage/v1\nkey: {target_key}\n",
        package_definition={"metadata": {"key": target_key}},
        compiled_plan={"workflows": [{"key": workflow_key}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": [workflow_key]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    return run


def test_retired_global_authoring_tables_are_not_registered_on_metadata() -> None:
    assert RETIRED_GLOBAL_AUTHORING_TABLE_NAMES.isdisjoint(Base.metadata.tables)
    assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(Base.metadata.tables)


def test_agent_platform_package_tables_are_current_only() -> None:
    assert AGENT_PLATFORM_PACKAGE_TABLE_NAMES <= set(Base.metadata.tables)
    assert REMOVED_WORKFLOW_PACKAGE_VERSION_TABLE_NAMES.isdisjoint(Base.metadata.tables)


def test_agent_platform_execution_tables_are_package_run_only() -> None:
    assert AGENT_PLATFORM_EXECUTION_TABLE_NAMES <= set(Base.metadata.tables)
    assert RETIRED_GLOBAL_AUTHORING_TABLE_NAMES.isdisjoint(Base.metadata.tables)

    run_table = Base.metadata.tables["runs"]
    target_kind_constraint = cast(
        CheckConstraint,
        next(
            constraint
            for constraint in run_table.constraints
            if constraint.name == "ck_runs_target_kind"
        ),
    )

    assert str(target_kind_constraint.sqltext) == "target_kind = 'workflowPackage'"
    assert "agent_id" not in run_table.c
    assert "workflow_id" not in run_table.c


def test_core_memory_tables_are_registered_on_metadata() -> None:
    assert CORE_MEMORY_TABLE_NAMES <= set(Base.metadata.tables)

    entry_table = Base.metadata.tables["agent_memory_entries"]
    revision_table = Base.metadata.tables["agent_memory_revisions"]
    chunk_table = Base.metadata.tables[AgentMemoryChunk.__tablename__]
    embedding_table = Base.metadata.tables[AgentMemoryEmbedding.__tablename__]
    event_table = Base.metadata.tables["run_memory_events"]

    assert {"report_id", "report_slug", "report_name"}.isdisjoint(entry_table.c.keys())
    assert {
        "memory_id",
        "scope_type",
        "scope_key",
        "kind",
        "status",
        "summary",
        "subject_refs",
        "attributes",
        "content_hash",
        "idempotency_key",
        "source_run_id",
        "source_agent_key",
        "source_agent_version",
    } <= set(entry_table.c.keys())
    assert {
        "revision_id",
        "memory_entry_id",
        "version",
        "status",
        "content",
        "content_hash",
        "source_run_id",
        "source_agent_key",
    } <= set(revision_table.c.keys())
    assert {
        "memory_entry_id",
        "memory_revision_id",
        "memory_id",
        "revision_id",
        "chunk_id",
        "chunk_index",
        "chunking_version",
        "content",
        "content_hash",
        "source_content_hash",
    } <= set(chunk_table.c.keys())
    assert {
        "memory_chunk_id",
        "memory_entry_id",
        "memory_revision_id",
        "embedding_model",
        "embedding_dimensions",
        "embedding",
        "content_hash",
        "chunking_version",
        "embedding_config_hash",
        "status",
        "metadata",
    } <= set(embedding_table.c.keys())
    assert str(embedding_table.c.embedding.type) == "VECTOR"
    assert {
        "run_id",
        "event_type",
        "memory_entry_id",
        "memory_revision_id",
        "memory_id",
        "revision_id",
        "filters",
        "budget",
        "result_snapshot",
        "status_snapshot",
    } <= set(event_table.c.keys())


def test_core_memory_models_persist_revisions_and_run_events(session_factory) -> None:
    first_content_hash = "a" * 64
    second_content_hash = "b" * 64
    with session_factory() as session:
        run = _build_run(
            target_id=1,
            target_key="memory_workflow_package",
            status="succeeded",
            final_output={"ok": True},
            total_tokens=0,
            trace_id="trace-memory",
            started_at=None,
            finished_at=None,
            workflow_key="memory_workflow",
        )
        session.add(run)
        session.flush()

        entry = AgentMemoryEntry(
            memory_id="memory-core-model-1",
            scope_type="run",
            scope_key=str(run.id),
            kind="decision",
            status="pending",
            summary="Model memory summary",
            content_hash=first_content_hash,
            source_run_id=run.id,
            source_agent_key="memory_agent",
            source_agent_version=1,
            source_step_id="write_memory",
            source_slot="decision",
            source_trace_id="span-write",
        )
        session.add(entry)
        session.flush()

        first_revision = AgentMemoryRevision(
            memory_entry_id=entry.id,
            revision_id="memory-core-model-1:rev-1",
            version=1,
            status="pending",
            summary=entry.summary,
            content="Model memory content.",
            content_hash=first_content_hash,
            source_run_id=run.id,
            source_agent_key="memory_agent",
            source_step_id="write_memory",
            source_slot="decision",
            trace_span_id="span-write",
        )
        second_revision = AgentMemoryRevision(
            memory_entry_id=entry.id,
            revision_id="memory-core-model-1:rev-2",
            version=2,
            status="pending",
            summary="Updated model memory summary",
            content="Model memory content B.",
            content_hash=second_content_hash,
            source_run_id=run.id,
            source_agent_key="memory_agent",
            source_step_id="write_memory",
            source_slot="decision",
            trace_span_id="span-write",
        )
        session.add_all([first_revision, second_revision])
        session.flush()

        chunk = AgentMemoryChunk(
            memory_entry_id=entry.id,
            memory_revision_id=second_revision.id,
            memory_id=entry.memory_id,
            revision_id=second_revision.revision_id,
            chunk_id="memory-core-model-1:rev-2:chunk-0",
            chunk_index=0,
            chunking_version="memory-core-chunker/v1",
            content="Model memory content B.",
            content_hash=second_content_hash,
            source_content_hash=second_revision.content_hash,
            token_count=4,
        )
        session.add(chunk)
        session.flush()

        event = RunMemoryEvent(
            run_id=run.id,
            event_type="written",
            memory_entry_id=entry.id,
            memory_revision_id=second_revision.id,
            memory_id=entry.memory_id,
            revision_id=second_revision.revision_id,
            retrieval_mode="write",
            filters={"scopeType": "run"},
            budget={"limit": 1},
            result_snapshot={"memoryId": entry.memory_id},
            status_snapshot={"status": entry.status},
            trace_span_id="span-write",
        )
        session.add(event)
        session.commit()

        stored_entry = session.get(AgentMemoryEntry, entry.id)
        stored_revision = session.get(AgentMemoryRevision, second_revision.id)
        stored_chunk = session.get(AgentMemoryChunk, chunk.id)
        stored_event = session.get(RunMemoryEvent, event.id)

        assert stored_entry is not None
        assert stored_entry.memory_id == "memory-core-model-1"
        assert stored_revision is not None
        assert stored_revision.revision_id == "memory-core-model-1:rev-2"
        assert stored_chunk is not None
        assert stored_chunk.chunking_version == "memory-core-chunker/v1"
        assert stored_event is not None
        assert stored_event.event_type == "written"


def test_model_connections_enforce_unique_keys(session_factory) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="primary_openai",
                status="active",
                name="Primary OpenAI",
                description="Primary model connection",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.4-mini",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
            )
        )
        session.commit()

        session.add(
            ModelConnection(
                key="primary_openai",
                status="active",
                name="Duplicate OpenAI",
                description="Duplicate model connection",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.4",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_agent_platform_run_models_persist_steps_invocations_totals_timestamps_and_trace_ids(
    session_factory,
) -> None:
    run_table = Base.metadata.tables["runs"]
    assert {"ix_runs_status", "ix_runs_target", "ix_runs_target_key"} <= {
        index.name for index in run_table.indexes
    }
    assert {"target_kind", "target_id", "target_key", "target_version", "queued_at"} <= set(
        run_table.c.keys()
    )
    assert {"agent_id", "workflow_id"}.isdisjoint(run_table.c.keys())
    assert {"workflow_key", "workflow_version", "per_step_outputs"}.isdisjoint(run_table.c.keys())

    assert RunWorkflowPackageSnapshot.__tablename__ == "run_workflow_package_snapshots"
    snapshot_table = Base.metadata.tables["run_workflow_package_snapshots"]
    assert list(snapshot_table.primary_key.columns.keys()) == ["run_id"]
    assert "id" not in snapshot_table.c

    with session_factory() as session:
        queued_at = datetime(2026, 4, 19, 9, 59, tzinfo=UTC_TZ)
        started_at = datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ)
        finished_at = datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ)
        run = _build_run(
            target_id=1,
            target_key="market_review_package",
            status="succeeded",
            final_output={"headline": "Buy"},
            total_tokens=321,
            trace_id="trace-market-review",
            started_at=started_at,
            finished_at=finished_at,
            workflow_key="market_review",
        )
        run.queued_at = queued_at
        session.add(run)
        session.flush()
        step = RunStep(
            run_id=run.id,
            step_index=1,
            status="succeeded",
            origin="planned",
            started_at=started_at,
            finished_at=finished_at,
            persisted_at=finished_at,
            graph_metadata={"nodeId": "analysis", "nodeKind": "step"},
        )
        session.add(step)
        session.flush()
        session.add(
            RunAgentInvocation(
                run_step_id=step.id,
                run_id=run.id,
                step_index=1,
                slot="analysis",
                position=0,
                agent_id=1001,
                agent_key="research_agent",
                agent_version=1,
                output_schema_id=2001,
                output_schema_version=1,
                input_mode="passthrough",
                wiring={},
                graph_metadata={"nodeId": "analysis", "nodeKind": "step"},
                optional=False,
                status="succeeded",
                resolved_input={"ticker": "NVDA"},
                resolved_input_origin="passthrough",
                output={"headline": "Buy"},
                output_origin="executed",
                tokens=321,
                duration_ms=1450,
                trace_span_id="span-analysis",
                started_at=started_at,
                finished_at=finished_at,
                persisted_at=finished_at,
            )
        )
        session.commit()
        session.refresh(run)

        stored_run = session.get(Run, run.id)
        assert stored_run is not None
        assert stored_run.target_kind == "workflowPackage"
        assert stored_run.target_id == 1
        assert stored_run.target_key == "market_review_package"
        assert stored_run.workflow_package_key == "market_review_package"
        assert stored_run.workflow_package_workflow_key == "market_review"
        assert len(stored_run.steps) == 1
        assert stored_run.steps[0].invocations[0].trace_span_id == "span-analysis"
        assert stored_run.steps[0].invocations[0].resolved_input == {"ticker": "NVDA"}
        assert stored_run.total_tokens == 321
        assert stored_run.trace_id == "trace-market-review"
        assert stored_run.queued_at == queued_at


def test_agent_platform_run_model_allows_queued_status_and_rejects_unknown_status(
    session_factory,
) -> None:
    queued_at = datetime(2026, 4, 20, 11, 0, tzinfo=UTC_TZ)

    with session_factory() as session:
        queued_run = _build_run(
            target_id=1,
            target_key="queued_workflow_package",
            status=RunStatus.QUEUED.value,
            final_output=None,
            total_tokens=0,
            trace_id=None,
            started_at=None,
            finished_at=None,
            workflow_key="queued_workflow",
        )
        queued_run.queued_at = queued_at
        session.add(queued_run)
        session.commit()
        session.refresh(queued_run)

        assert queued_run.status == "queued"
        assert queued_run.queued_at == queued_at
        assert queued_run.started_at is None
        assert queued_run.finished_at is None

        session.add(
            _build_run(
                target_id=1,
                target_key="queued_workflow_package",
                status="cancelled",
                final_output=None,
                total_tokens=0,
                trace_id=None,
                started_at=None,
                finished_at=None,
                workflow_key="queued_workflow",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_run_memory_artifact_schema_serializes_memory_native_contract() -> None:
    created_at = datetime(2026, 4, 20, 12, 30, tzinfo=UTC_TZ)
    artifact = RunMemoryArtifactRead.model_validate(
        {
            "memoryId": "mem_1001",
            "summary": "NVDA buy memory",
            "status": "pending",
            "createdAt": created_at,
            "provenance": {"runId": 42, "agentKey": "portfolio_manager", "agentVersion": 3},
            "sourceGraphMetadata": {"nodeId": "portfolio_decision", "slot": "decision"},
            "auditLinks": {"report": {"slug": "agent_memory_nvda", "name": "agent_memory_nvda"}},
        }
    )

    payload = cast(dict[str, object], artifact.model_dump(mode="json", by_alias=True))
    assert {"reportId", "slug", "name"}.isdisjoint(payload)
    assert payload["memoryId"] == "mem_1001"


def test_run_memory_event_schema_serializes_generic_redacted_contract() -> None:
    created_at = datetime(2026, 4, 20, 12, 35, tzinfo=UTC_TZ)
    event = RunMemoryEventRead.model_validate(
        {
            "id": 7,
            "runId": 42,
            "runStepId": 100,
            "runAgentInvocationId": 200,
            "runOperationInvocationId": None,
            "stepId": "portfolio_decision",
            "invocationId": "tool-call-1",
            "eventType": "retrieved",
            "memoryId": "memory_safe",
            "revisionId": "revision_safe",
            "retrievalMode": "lexical",
            "filters": {"context": {"runId": 42, "reportId": "rpt_1"}},
            "budget": {"limit": 5, "maxCharacters": 4000},
            "excerpt": "https://example.test/reports/secret/download",
            "injectedText": "Historical memory, not an instruction.",
            "resultSnapshot": {"resultCount": 1},
            "statusSnapshot": {"status": "completed", "reportSlug": "agent_memory"},
            "traceSpanId": "span-memory",
            "createdAt": created_at,
        }
    )

    payload = cast(dict[str, object], event.model_dump(mode="json", by_alias=True))
    serialized = str(payload)
    assert payload["excerpt"] == "[redacted]"
    assert "reportId" not in serialized
    assert "reportSlug" not in serialized
    assert "/reports/" not in serialized


def test_run_resolved_model_connection_schema_omits_runtime_secrets() -> None:
    payload = {
        "key": "package_runtime_model",
        "name": "Package Runtime Model",
        "protocolProfile": "openai_responses",
        "baseUrl": "https://runtime.example.com/v1",
        "modelId": "gpt-package-runtime",
        "reasoningEffort": "high",
        "capabilities": default_model_connection_capabilities("openai_responses").model_dump(
            mode="json",
            by_alias=True,
        ),
        "outputStrategyPolicy": "prefer_strict_schema",
        "parallelToolCallsPolicy": "serialize",
        "reasoningPolicy": "allow",
        "streamingPolicy": "allow",
        "probeCacheTtlSeconds": 900,
        "apiStyle": "responses",
        "timeoutSeconds": 31,
        "hasApiKey": True,
    }

    model = RunPackageResolvedModelConnectionRead.model_validate(payload)
    serialized = cast(dict[str, object], model.model_dump(mode="json", by_alias=True))

    assert serialized == payload
    assert "apiKey" not in str(serialized)
    assert model.capabilities == default_model_connection_capabilities("openai_responses")


def test_run_model_schedule_provenance_contract() -> None:
    run_table = Base.metadata.tables["runs"]
    schedule_fk = next(iter(run_table.c.schedule_id.foreign_keys))
    schedule_fire_fk = next(iter(run_table.c.schedule_fire_id.foreign_keys))

    assert "schedule_provenance" in run_table.c
    assert str(run_table.c.schedule_provenance.type) == "JSONB"
    assert run_table.c.schedule_provenance.nullable is True
    assert schedule_fk.column.table.name == "workflow_package_schedules"
    assert schedule_fk.column.name == "id"
    assert schedule_fk.ondelete == "SET NULL"
    assert schedule_fire_fk.column.table.name == "workflow_package_schedule_fires"
    assert schedule_fire_fk.column.name == "id"
    assert schedule_fire_fk.ondelete == "SET NULL"

    payload = {
        "scheduleId": 11,
        "scheduleFireId": 29,
        "scheduleName": "Daily research",
        "packageId": 7,
        "packageKey": "daily_research_package",
        "workflowKey": "daily_research",
        "timezone": "UTC",
        "recurrence": {"type": "daily", "time": "13:00"},
        "fireKey": "daily-2026-06-01",
        "reason": "scheduled",
        "scheduledFor": datetime(2026, 6, 1, 13, 0, tzinfo=UTC_TZ),
        "scheduledLocalDate": "2026-06-01",
        "scheduledLocalTime": "13:00:00",
        "scheduledLocalDateTime": "2026-06-01T13:00:00",
        "materializedAt": datetime(2026, 6, 1, 12, 59, tzinfo=UTC_TZ),
        "scheduleDeletedAt": None,
    }

    model = RunScheduleProvenanceRead.model_validate(payload)
    serialized = cast(dict[str, object], model.model_dump(mode="json", by_alias=True))

    assert set(RunScheduleProvenanceRead.model_fields) == {
        "schedule_id",
        "schedule_fire_id",
        "schedule_name",
        "package_id",
        "package_key",
        "workflow_key",
        "timezone",
        "recurrence",
        "fire_key",
        "reason",
        "scheduled_for",
        "scheduled_local_date",
        "scheduled_local_time",
        "scheduled_local_datetime",
        "materialized_at",
        "schedule_deleted_at",
    }
    assert serialized["scheduledFor"] == "2026-06-01T13:00:00Z"


def test_agent_platform_run_schemas_serialize_queued_without_started_at() -> None:
    queued_at = datetime(2026, 4, 20, 11, 0, tzinfo=UTC_TZ)
    common_payload = {
        "id": 42,
        "targetKind": "workflowPackage",
        "targetId": 7,
        "targetKey": "queued_workflow_package",
        "status": "queued",
        "progress": {"unit": "invocation", "terminalCount": 0, "totalCount": 0, "percent": 0},
        "queue": None,
        "workflowKey": "queued_workflow",
        "totalTokens": 0,
        "traceId": None,
        "queuedAt": queued_at,
        "startedAt": None,
        "finishedAt": None,
    }

    list_item = RunListItemRead.model_validate(common_payload)
    detail = RunRead.model_validate(
        {
            **{key: value for key, value in common_payload.items() if key != "workflowKey"},
            "input": {"ticker": "NVDA"},
            "resumeStepIndex": 1,
            "finalOutput": None,
            "inheritedTokens": 0,
            "executedTokens": 0,
            "error": None,
            "createdAt": queued_at,
            "updatedAt": queued_at,
            "extensionDependencies": [],
            "steps": [],
            "memoryArtifacts": [],
            "packageProvenance": {
                "workflowPackageId": 7,
                "workflowPackageKey": "queued_workflow_package",
                "workflowPackageName": "Queued Workflow Package",
                "workflowPackageDescription": "",
                "workflowPackageStatus": "active",
                "workflowPackageManifestHash": "a" * 64,
                "workflowPackageCompiledHash": "b" * 64,
                "workflowKey": "queued_workflow",
                "workflowName": "Queued Workflow",
                "workflowDescription": "",
                "manifestSource": (
                    "apiVersion: signaldeck.workflowPackage/v1\n" "key: queued_workflow_package\n"
                ),
                "packageDefinition": {"metadata": {"key": "queued_workflow_package"}},
                "compiledPlan": {"workflows": [{"key": "queued_workflow"}]},
                "launchSnapshot": None,
                "extensionDependencies": [],
                "localResourceRefs": {"workflows": ["queued_workflow"]},
                "resolvedModelConnections": [],
                "preflightSummary": None,
                "currentPackage": None,
            },
        }
    )

    list_payload = cast(dict[str, object], list_item.model_dump(mode="json", by_alias=True))
    detail_payload = cast(dict[str, object], detail.model_dump(mode="json", by_alias=True))

    assert list_payload["queuedAt"] == "2026-04-20T11:00:00Z"
    assert detail_payload["startedAt"] is None
    assert detail_payload["targetKind"] == "workflowPackage"
