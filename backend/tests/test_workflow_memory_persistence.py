from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.workflow_memory import (
    WorkflowMemoryAuditEvent,
    WorkflowMemoryConsolidationRun,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
    WorkflowMemoryRevision,
)
from app.repositories.workflow_memory import WorkflowMemoryRepository

UTC_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def test_workflow_memory_tables_match_plan_columns_and_states() -> None:
    expected_tables = {
        "workflow_memory_items",
        "workflow_memory_proposals",
        "workflow_memory_decisions",
        "workflow_memory_audit_events",
        "workflow_memory_revisions",
        "workflow_memory_quarantine",
        "workflow_memory_consolidation_runs",
    }

    assert expected_tables <= set(Base.metadata.tables)
    item_table = Base.metadata.tables["workflow_memory_items"]
    proposal_table = Base.metadata.tables["workflow_memory_proposals"]
    decision_table = Base.metadata.tables["workflow_memory_decisions"]

    assert {
        "id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "namespace",
        "kind",
        "content_json",
        "summary",
        "provenance_json",
        "policy_status",
        "lifecycle_status",
        "valid_from",
        "expires_at",
        "superseded_by_id",
        "deleted_at",
        "created_at",
        "updated_at",
    } <= set(item_table.c.keys())
    assert {
        "run_id",
        "invocation_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "kind",
        "content_json",
        "reason",
        "source_output_path",
        "detectors_json",
        "status",
    } <= set(proposal_table.c.keys())
    assert {
        "proposal_id",
        "decision",
        "reason_code",
        "reason",
        "policy_snapshot_json",
        "decided_by",
        "created_at",
    } <= set(decision_table.c.keys())
    constraints = "\n".join(
        str(constraint.sqltext)
        for table in (item_table, proposal_table, decision_table)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert "review_pending" in constraints
    assert "review" in constraints
    assert "expired" in constraints


def test_active_retrieval_filters_lifecycle_policy_validity_and_authorized_scope(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        visible = repo.create_memory_item(
            memory_id="mem-visible",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Revenue grew year over year."},
            summary="Visible committed fact",
            provenance_json={"runId": 101},
            run_id=101,
            invocation_id="invoke-visible",
            valid_from=UTC_NOW - timedelta(minutes=5),
        )

        def create_excluded(
            *,
            memory_id: str,
            package_key: str = "research_pkg",
            workflow_key: str = "due_diligence",
            agent_key: str = "analyst",
            step_id: str = "summarize",
            namespace: str = "research",
            policy_status: str = "committed",
            lifecycle_status: str = "active",
            valid_from: datetime = UTC_NOW - timedelta(minutes=5),
            expires_at: datetime | None = None,
            deleted_at: datetime | None = None,
        ) -> None:
            repo.create_memory_item(
                memory_id=memory_id,
                package_key=package_key,
                workflow_key=workflow_key,
                agent_key=agent_key,
                step_id=step_id,
                namespace=namespace,
                kind="fact",
                content_json={"text": "Excluded content."},
                summary="Excluded memory",
                provenance_json={"case": "excluded"},
                policy_status=policy_status,
                lifecycle_status=lifecycle_status,
                valid_from=valid_from,
                expires_at=expires_at,
                deleted_at=deleted_at,
            )

        create_excluded(memory_id="mem-proposed", policy_status="proposed")
        create_excluded(memory_id="mem-review", policy_status="review_pending")
        create_excluded(memory_id="mem-rejected", policy_status="rejected")
        create_excluded(memory_id="mem-policy-quarantined", policy_status="quarantined")
        create_excluded(memory_id="mem-superseded", lifecycle_status="superseded")
        create_excluded(memory_id="mem-expired-lifecycle", lifecycle_status="expired")
        create_excluded(memory_id="mem-deleted-lifecycle", lifecycle_status="deleted")
        create_excluded(memory_id="mem-expired-time", expires_at=UTC_NOW - timedelta(seconds=1))
        create_excluded(memory_id="mem-deleted-time", deleted_at=UTC_NOW - timedelta(seconds=1))
        create_excluded(memory_id="mem-future-valid", valid_from=UTC_NOW + timedelta(seconds=1))
        create_excluded(memory_id="mem-other-package", package_key="other_pkg")
        create_excluded(memory_id="mem-other-workflow", workflow_key="other_workflow")
        create_excluded(memory_id="mem-other-agent", agent_key="critic")
        create_excluded(memory_id="mem-other-step", step_id="review")
        create_excluded(memory_id="mem-other-namespace", namespace="private")
        superseder = repo.create_memory_item(
            memory_id="mem-superseder",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Newer content."},
            summary="Superseding row",
            provenance_json={},
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        superseded_by_id = repo.create_memory_item(
            memory_id="mem-has-superseded-by",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Old content."},
            summary="Old row",
            provenance_json={},
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        session.flush()
        superseded_by_id.superseded_by_id = superseder.id
        quarantined = repo.create_memory_item(
            memory_id="mem-unresolved-quarantine",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Quarantined content."},
            summary="Quarantined row",
            provenance_json={},
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        repo.quarantine_memory_item(
            memory_item=quarantined,
            reason_code="sensitive_data",
            reason="detector matched",
            run_id=101,
            detectors_json={"detector": "pii"},
        )
        session.commit()

        results = repo.list_active_memory(
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespaces=("research",),
            now=UTC_NOW,
            limit=50,
        )

        assert [item.memory_id for item in results] == [superseder.memory_id, visible.memory_id]


def test_plan_lifecycle_persistence_records_are_separate_from_retrieval(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        proposal = repo.create_proposal(
            proposal_id="proposal-1",
            run_id=201,
            invocation_id="invoke-proposal",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="decision",
            content_json={"recommendation": "increase_allocation"},
            reason="candidate output met write policy",
            source_output_path="steps.summarize.output.recommendation",
            detectors_json={"sensitiveData": False},
            status="review_pending",
        )
        decision = repo.record_decision(
            decision_id="decision-1",
            proposal=proposal,
            decision="review",
            reason_code="manual_review_required",
            reason="policy requires review",
            policy_snapshot_json={"defaultDecision": "review"},
            decided_by="policy",
        )
        item = repo.create_memory_item(
            memory_id="mem-decision",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="decision",
            content_json={"recommendation": "increase_allocation"},
            summary="Allocation decision",
            provenance_json={"proposalId": proposal.proposal_id},
            proposal_id=proposal.id,
            decision_id=decision.id,
            run_id=201,
            invocation_id="invoke-proposal",
            valid_from=UTC_NOW,
        )
        revision = repo.record_revision(
            memory_item=item,
            revision_id="mem-decision:rev-2",
            version=2,
            content_json={"recommendation": "increase_after_review"},
            summary="Updated allocation decision",
            provenance_json={"change": "supersession"},
            supersedes_revision_id="mem-decision:rev-1",
        )
        audit_event = repo.record_audit_event(
            event_type="memory_review_required",
            target_type="proposal",
            target_id=proposal.proposal_id,
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            run_id=201,
            invocation_id="invoke-proposal",
            event_json={"decisionId": decision.decision_id},
        )
        quarantine = repo.quarantine_proposal(
            proposal=proposal,
            reason_code="review_required",
            reason="operator review needed",
            run_id=203,
            invocation_id="invoke-quarantine",
            detectors_json={"review": True},
        )
        consolidation = repo.record_consolidation_run(
            consolidation_id="consolidation-1",
            package_key="research_pkg",
            workflow_key="due_diligence",
            namespace="research",
            status="succeeded",
            started_at=UTC_NOW,
            finished_at=UTC_NOW + timedelta(minutes=2),
            source_memory_ids_json=["mem-a", "mem-b"],
            output_memory_ids_json=[item.memory_id],
            stats_json={"strategy": "merge_duplicates"},
        )
        session.commit()

        assert proposal.status == "review_pending"
        assert proposal.content_json == {"recommendation": "increase_allocation"}
        assert proposal.source_output_path == "steps.summarize.output.recommendation"
        assert decision.decision == "review"
        assert decision.reason_code == "manual_review_required"
        assert decision.policy_snapshot_json == {"defaultDecision": "review"}
        assert decision.decided_by == "policy"
        assert item.policy_status == "committed"
        assert revision.content_json == {"recommendation": "increase_after_review"}
        assert revision.provenance_json == {"change": "supersession"}
        assert audit_event.event_json == {"decisionId": "decision-1"}
        assert quarantine.proposal_id == proposal.id
        assert quarantine.reason_code == "review_required"
        assert consolidation.source_memory_ids_json == ["mem-a", "mem-b"]
        assert consolidation.output_memory_ids_json == [item.memory_id]
        assert consolidation.stats_json == {"strategy": "merge_duplicates"}


@pytest.mark.parametrize(
    "model",
    [
        WorkflowMemoryItem,
        WorkflowMemoryProposal,
        WorkflowMemoryDecision,
        WorkflowMemoryAuditEvent,
        WorkflowMemoryRevision,
        WorkflowMemoryQuarantine,
        WorkflowMemoryConsolidationRun,
    ],
)
def test_workflow_memory_models_have_postgresql_backed_tables(
    session_factory: sessionmaker[Session],
    model,
) -> None:
    with session_factory() as session:
        inspector = sqlalchemy_inspect(session.get_bind())
        assert inspector.has_table(model.__tablename__)
