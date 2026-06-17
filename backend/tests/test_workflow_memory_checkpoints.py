from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_memory import WorkflowMemoryItem
from app.repositories.workflow_checkpoints import WorkflowCheckpointRepository
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import WorkflowCheckpointRecord, WorkflowCheckpointScope
from app.services.workflow_checkpoint_service import WorkflowCheckpointService

UTC_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def test_workflow_checkpoints_table_uses_plan_fields_and_is_separate() -> None:
    checkpoint_table = Base.metadata.tables["workflow_checkpoints"]
    memory_tables = {
        "workflow_memory_items",
        "workflow_memory_proposals",
        "workflow_memory_decisions",
        "workflow_memory_audit_events",
        "workflow_memory_revisions",
        "workflow_memory_quarantine",
        "workflow_memory_consolidation_runs",
    }

    assert WorkflowCheckpoint.__tablename__ == "workflow_checkpoints"
    assert "workflow_checkpoints" in Base.metadata.tables
    assert memory_tables.isdisjoint({WorkflowCheckpoint.__tablename__})
    assert {
        "checkpoint_id",
        "owner_type",
        "owner_id",
        "run_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "invocation_id",
        "checkpoint_type",
        "sequence",
        "state_json",
        "retention",
        "metadata_json",
        "created_at",
    } <= set(checkpoint_table.c.keys())
    assert {"state_json", "metadata_json"} <= set(checkpoint_table.c.keys())


def test_checkpoint_repository_persists_and_reads_only_checkpoint_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        checkpoint_repo = WorkflowCheckpointRepository(session)
        memory_repo = WorkflowMemoryRepository(session)
        _ = memory_repo.create_memory_item(
            memory_id="mem-not-a-checkpoint",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "This must not appear in checkpoint reads."},
            summary="Long term memory",
            provenance_json={"runId": 301},
            run_id=301,
            invocation_id="invoke-memory",
            valid_from=UTC_NOW - timedelta(minutes=1),
        )
        first = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-1",
            run_id=301,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-checkpoint-1",
            checkpoint_type="step_state",
            sequence=1,
            state_json={"cursor": 1},
            retention="run_lifecycle",
            metadata_json={"source": "middleware"},
        )
        second = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-2",
            run_id=301,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-checkpoint-2",
            checkpoint_type="step_state",
            sequence=2,
            state_json={"cursor": 2},
            retention="run_lifecycle",
            metadata_json={"source": "middleware"},
        )
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-other-type",
            run_id=301,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-checkpoint-other-type",
            checkpoint_type="agent_state",
            sequence=3,
            state_json={"cursor": "agent"},
            retention="run_lifecycle",
        )
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-other-run",
            run_id=302,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-checkpoint-other-run",
            checkpoint_type="step_state",
            sequence=1,
            state_json={"cursor": "other"},
            retention="run_lifecycle",
        )
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-other-owner",
            owner_type="local_user",
            owner_id="other",
            run_id=301,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-checkpoint-other-owner",
            checkpoint_type="step_state",
            sequence=4,
            state_json={"cursor": "other-owner"},
            retention="run_lifecycle",
        )
        session.commit()

        latest = checkpoint_repo.get_latest_checkpoint(
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=301,
            agent_key="analyst",
            step_id="summarize",
            checkpoint_type="step_state",
        )
        run_checkpoints = checkpoint_repo.list_checkpoints_for_run(
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=301,
        )

        assert latest is not None
        assert latest.checkpoint_id == second.checkpoint_id
        assert latest.state_json == {"cursor": 2}
        assert latest.retention == "run_lifecycle"
        assert [checkpoint.checkpoint_id for checkpoint in run_checkpoints] == [
            first.checkpoint_id,
            second.checkpoint_id,
            "checkpoint-other-type",
        ]
        assert (
            memory_repo.list_active_memory(
                package_key="research_pkg",
                workflow_key="due_diligence",
                agent_key="analyst",
                step_id="summarize",
                namespaces=("research",),
                now=UTC_NOW,
                limit=10,
            )[0].memory_id
            == "mem-not-a-checkpoint"
        )


def test_checkpoint_model_has_postgresql_backed_table(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        inspector = sqlalchemy_inspect(session.get_bind())
        assert inspector.has_table(WorkflowCheckpoint.__tablename__)


def test_checkpoint_service_records_run_local_state_without_long_term_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        record = WorkflowCheckpointService(session).record_checkpoint(
            scope=WorkflowCheckpointScope(
                package_key="research_pkg",
                workflow_key="due_diligence",
                run_id=401,
                agent_key="analyst",
                step_id="summarize",
                invocation_id="invoke-checkpoint-service",
            ),
            checkpoint=WorkflowCheckpointRecord(
                checkpoint_type="step_state",
                sequence=1,
                state={"cursor": 10},
                retention="run_lifecycle",
                metadata={"source": "test"},
            ),
        )
        session.commit()

        checkpoint_rows = session.query(WorkflowCheckpoint).all()
        memory_rows = session.query(WorkflowMemoryItem).all()

        assert record.checkpoint_id == checkpoint_rows[0].checkpoint_id
        assert record.state == {"cursor": 10}
        assert record.retention == "run_lifecycle"
        assert checkpoint_rows[0].checkpoint_type == "step_state"
        assert checkpoint_rows[0].state_json == {"cursor": 10}
        assert checkpoint_rows[0].retention == "run_lifecycle"
        assert memory_rows == []


def test_checkpoint_repository_filters_run_reads_by_owner(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        checkpoint_repo = WorkflowCheckpointRepository(session)
        default_checkpoint = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-default-owner",
            run_id=901,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-default-owner",
            checkpoint_type="step_state",
            sequence=1,
            state_json={"cursor": "default"},
            retention="run_lifecycle",
        )
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-hidden-owner",
            owner_type="local_user",
            owner_id="other",
            run_id=901,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-hidden-owner",
            checkpoint_type="step_state",
            sequence=2,
            state_json={"cursor": "other"},
            retention="run_lifecycle",
        )
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-hidden-finalize",
            owner_type="local_user",
            owner_id="other",
            run_id=901,
            package_key="research_pkg",
            workflow_key="due_diligence",
            checkpoint_type="run_finalize",
            sequence=3,
            state_json={"status": "other"},
            retention="run_lifecycle",
        )
        session.commit()

        latest = checkpoint_repo.get_latest_checkpoint(
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=901,
            agent_key="analyst",
            step_id="summarize",
            checkpoint_type="step_state",
        )
        run_checkpoints = checkpoint_repo.list_checkpoints_for_run(
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=901,
        )
        run_finalize = checkpoint_repo.get_run_finalize_checkpoint(
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=901,
        )

        assert latest is not None
        assert latest.checkpoint_id == default_checkpoint.checkpoint_id
        assert [checkpoint.checkpoint_id for checkpoint in run_checkpoints] == [
            default_checkpoint.checkpoint_id
        ]
        assert run_finalize is None
