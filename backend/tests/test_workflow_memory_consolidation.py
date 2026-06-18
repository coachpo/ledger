from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.models.workflow_memory import WorkflowMemoryAuditEvent, WorkflowMemoryConsolidationRun
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.services.workflow_memory_consolidation_service import WorkflowMemoryConsolidationService


def test_run_end_consolidation_supersedes_exact_duplicates_within_owner_scope(
    session_factory: sessionmaker[Session],
) -> None:
    now = utcnow()
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        prior = repo.create_memory_item(
            memory_id="mem-prior-duplicate",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="prior_agent",
            step_id="prior_step",
            namespace="research",
            kind="fact",
            content_json={"text": "Exact duplicate content."},
            summary="Prior duplicate",
            provenance_json={"confidence": 0.2, "importance": 0.3},
            valid_from=now - timedelta(days=2),
        )
        source = repo.create_memory_item(
            memory_id="mem-run-duplicate-survivor",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="run_agent",
            step_id="run_step",
            namespace="research",
            kind="fact",
            content_json={"text": "Exact duplicate content."},
            summary="Run duplicate",
            provenance_json={"confidence": 0.9, "importance": 0.9},
            run_id=501,
            invocation_id="invoke-501",
            valid_from=now - timedelta(days=1),
        )
        other_owner = repo.create_memory_item(
            memory_id="mem-other-owner-duplicate",
            owner_id="other-owner",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="run_agent",
            step_id="run_step",
            namespace="research",
            kind="fact",
            content_json={"text": "Exact duplicate content."},
            summary="Other owner duplicate",
            provenance_json={"confidence": 1.0},
            run_id=501,
            valid_from=now - timedelta(days=1),
        )
        non_exact = repo.create_memory_item(
            memory_id="mem-run-non-exact",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="run_agent",
            step_id="run_step",
            namespace="research",
            kind="fact",
            content_json={"text": "Different content."},
            summary="Different content",
            provenance_json={"confidence": 0.1},
            run_id=501,
            valid_from=now - timedelta(days=1),
        )
        session.commit()

        rows = WorkflowMemoryConsolidationService(session).consolidate_run_end(501)
        session.refresh(prior)
        session.refresh(source)
        session.refresh(other_owner)
        session.refresh(non_exact)

        assert [row.status for row in rows] == ["succeeded", "succeeded"]
        assert prior.lifecycle_status == "superseded"
        assert prior.superseded_by_id == source.id
        assert source.lifecycle_status == "active"
        assert other_owner.lifecycle_status == "active"
        assert non_exact.lifecycle_status == "active"

        default_owner_run = (
            session.query(WorkflowMemoryConsolidationRun).filter_by(owner_id="default").one()
        )
        assert set(default_owner_run.source_memory_ids_json) == {
            "mem-run-duplicate-survivor",
            "mem-run-non-exact",
        }
        assert default_owner_run.output_memory_ids_json == [
            "mem-run-duplicate-survivor",
            "mem-run-non-exact",
        ]
        assert default_owner_run.stats_json["duplicateSetCount"] == 1
        assert default_owner_run.stats_json["supersededMemoryIds"] == [prior.memory_id]
        audit_events = (
            session.query(WorkflowMemoryAuditEvent).order_by(WorkflowMemoryAuditEvent.id).all()
        )
        assert [event.event_type for event in audit_events] == [
            "memory_consolidation_supersede",
            "memory_consolidation_run",
            "memory_consolidation_run",
        ]


def test_run_end_consolidation_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    now = utcnow()
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        older = repo.create_memory_item(
            memory_id="mem-older-duplicate",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="agent",
            step_id="step",
            namespace="research",
            kind="fact",
            content_json={"text": "Repeatable duplicate."},
            summary="Older duplicate",
            provenance_json={},
            run_id=601,
            valid_from=now - timedelta(days=2),
        )
        newer = repo.create_memory_item(
            memory_id="mem-newer-duplicate",
            package_key="pkg",
            workflow_key="workflow",
            agent_key="agent",
            step_id="step",
            namespace="research",
            kind="fact",
            content_json={"text": "Repeatable duplicate."},
            summary="Newer duplicate",
            provenance_json={},
            run_id=601,
            valid_from=now - timedelta(days=1),
        )
        session.commit()

        first = WorkflowMemoryConsolidationService(session).consolidate_run_end(601)
        second = WorkflowMemoryConsolidationService(session).consolidate_run_end(601)
        session.refresh(older)
        session.refresh(newer)

        assert len(first) == 1
        assert len(second) == 1
        assert second[0].id == first[0].id
        assert older.lifecycle_status == "superseded"
        assert older.superseded_by_id == newer.id
        assert session.query(WorkflowMemoryConsolidationRun).count() == 1
        assert session.query(WorkflowMemoryAuditEvent).count() == 2


def test_run_end_consolidation_id_fits_persisted_column_limit(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        _ = repo.create_memory_item(
            memory_id="mem-long-scope-source",
            owner_type="local_user",
            owner_id="owner_" + ("x" * 114),
            package_key="pkg_" + ("y" * 116),
            workflow_key="workflow_" + ("z" * 111),
            agent_key="agent",
            step_id="step",
            namespace="namespace_" + ("n" * 110),
            kind="fact",
            content_json={"text": "Long scope content."},
            summary="Long scope content.",
            run_id=123456789,
        )
        session.commit()

        rows = WorkflowMemoryConsolidationService(session).consolidate_run_end(123456789)

        assert len(rows) == 1
        assert rows[0].consolidation_id.startswith("wmc_run_end_123456789_")
        assert len(rows[0].consolidation_id) <= 160
