from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_memory import (
    WorkflowMemoryAuditEvent,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
    WorkflowMemoryRevision,
)
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.services.execution_plan import (
    MemoryDefaultDecision,
    PackageMemoryCheckpointPolicy,
    PackageMemoryDetectorPolicy,
    PackageMemoryRetrievalPolicy,
    PackageMemoryWritePolicy,
    PackageResolvedMemoryPolicy,
)

WorkflowMemoryMiddleware = cast(
    Any,
    import_module("app.services.workflow_memory_middleware").WorkflowMemoryMiddleware,
)

UTC_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def _policy(*, default_decision: MemoryDefaultDecision = "commit") -> PackageResolvedMemoryPolicy:
    return PackageResolvedMemoryPolicy(
        enabled=True,
        retrieval=PackageMemoryRetrievalPolicy(
            enabled=True,
            namespaces=("research",),
            max_items=5,
            include_kinds=("fact", "observation", "preference", "decision"),
        ),
        writes=PackageMemoryWritePolicy(
            proposals=True,
            allowed_kinds=("fact", "observation", "preference", "decision"),
            default_decision=default_decision,
            auto_commit_kinds=("fact", "observation", "preference"),
        ),
        policy=PackageMemoryDetectorPolicy(
            secrets="quarantine",
            sensitive_data="review",
            unauthorized="reject",
        ),
        checkpoints=PackageMemoryCheckpointPolicy(enabled=True, retention="run_lifecycle"),
    )


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_disabled_is_inert(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        middleware = WorkflowMemoryMiddleware(session)
        disabled_policy = PackageResolvedMemoryPolicy()

        begin = middleware.begin_step(
            policy=disabled_policy,
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=801,
            step_id="summarize",
            sequence=1,
            state={"started": True},
        )
        prepared = middleware.prepare_invocation(
            policy=disabled_policy,
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=801,
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-disabled",
            namespace="research",
        )
        completed = middleware.complete_invocation(
            policy=disabled_policy,
            scope=prepared.metadata.scope,
            runtime_output={"memoryProposals": [{"kind": "fact", "content": "Skip me."}]},
            run_id=801,
            invocation_id="invoke-disabled",
        )
        finalized_step = middleware.finalize_step(
            policy=disabled_policy,
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=801,
            step_id="summarize",
            sequence=2,
            state={"done": True},
        )
        finalized_run = middleware.finalize_run(
            policy=disabled_policy,
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=801,
            sequence=3,
            state={"done": True},
        )
        session.commit()

        assert begin.checkpoint is None
        assert finalized_step.checkpoint is None
        assert finalized_run.checkpoint is None
        assert prepared.context.items == []
        assert prepared.checkpoints == ()
        assert prepared.metadata.enabled is False
        assert prepared.metadata.policy_snapshot == {}
        assert prepared.metadata.context_item_ids == ()
        assert prepared.metadata.checkpoint_ids == ()
        assert completed.proposals == ()
        assert completed.decisions == ()
        assert completed.rejected_count == 0
        for model in (
            WorkflowMemoryItem,
            WorkflowMemoryProposal,
            WorkflowMemoryDecision,
            WorkflowMemoryAuditEvent,
            WorkflowMemoryRevision,
            WorkflowMemoryQuarantine,
            WorkflowCheckpoint,
        ):
            assert _count(session, model) == 0


def test_proposal_policy_gate(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        existing = repo.create_memory_item(
            memory_id="mem-middleware-context",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Existing approved context."},
            summary="Existing context",
            provenance_json={"runId": 800},
            valid_from=UTC_NOW - timedelta(days=365),
        )
        middleware = WorkflowMemoryMiddleware(session)
        begin = middleware.begin_step(
            policy=_policy(default_decision="commit"),
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=802,
            step_id="summarize",
            sequence=1,
            state={"step": "started"},
        )
        prepared = middleware.prepare_invocation(
            policy=_policy(default_decision="commit"),
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=802,
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-policy-gate",
            namespace="research",
        )

        completed = middleware.complete_invocation(
            policy=_policy(default_decision="commit"),
            scope=prepared.metadata.scope,
            runtime_output={
                "memoryProposals": [
                    {
                        "kind": "fact",
                        "namespace": "research",
                        "content": "Revenue accelerated in Q4.",
                        "reason": "summarized result",
                    }
                ]
            },
            run_id=802,
            invocation_id="invoke-policy-gate",
            source_output_path="steps.summarize.output.memoryProposals",
        )
        session.commit()

        proposals = list(session.scalars(select(WorkflowMemoryProposal)))
        decisions = list(session.scalars(select(WorkflowMemoryDecision)))
        active_items = list(
            session.scalars(select(WorkflowMemoryItem).order_by(WorkflowMemoryItem.memory_id))
        )
        audit_events = list(session.scalars(select(WorkflowMemoryAuditEvent)))
        checkpoints = list(session.scalars(select(WorkflowCheckpoint)))

        assert begin.checkpoint is not None
        assert prepared.context.items[0].item_id == existing.memory_id
        assert prepared.metadata.enabled is True
        assert prepared.metadata.context_item_ids == (existing.memory_id,)
        assert prepared.metadata.checkpoint_ids == (begin.checkpoint.checkpoint_id,)
        assert len(completed.proposals) == 1
        assert len(completed.decisions) == 1
        assert completed.rejected_count == 0
        assert proposals[0].status == "committed"
        assert decisions[0].decision == "commit"
        assert decisions[0].reason_code == "auto_commit_allowed"
        assert len(active_items) == 2
        committed = [item for item in active_items if item.memory_id != existing.memory_id][0]
        assert committed.policy_status == "committed"
        assert committed.lifecycle_status == "active"
        assert committed.content_json == {"text": "Revenue accelerated in Q4."}
        assert committed.proposal_id == proposals[0].id
        assert committed.decision_id == decisions[0].id
        assert audit_events[0].event_type == "memory_policy_commit"
        assert checkpoints[0].checkpoint_type == "step_begin"


def test_secret_proposal_quarantines_without_activation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        middleware = WorkflowMemoryMiddleware(session)
        prepared = middleware.prepare_invocation(
            policy=_policy(default_decision="commit"),
            package_key="research_pkg",
            workflow_key="due_diligence",
            run_id=803,
            agent_key="analyst",
            step_id="summarize",
            invocation_id="invoke-secret",
            namespace="research",
        )

        completed = middleware.complete_invocation(
            policy=_policy(default_decision="commit"),
            scope=prepared.metadata.scope,
            runtime_output={
                "memoryProposals": [
                    {
                        "kind": "fact",
                        "namespace": "research",
                        "content": "Use sk-test_abcdefghijklmnopqrstuvwxyz123456 for calls.",
                    }
                ]
            },
            run_id=803,
            invocation_id="invoke-secret",
        )
        session.commit()

        proposal = session.scalar(select(WorkflowMemoryProposal))
        decision = session.scalar(select(WorkflowMemoryDecision))
        quarantine = session.scalar(select(WorkflowMemoryQuarantine))

        assert len(completed.proposals) == 1
        assert len(completed.decisions) == 1
        assert proposal is not None
        assert decision is not None
        assert quarantine is not None
        assert decision.decision == "quarantine"
        assert decision.reason_code == "secret_detected"
        assert proposal.status == "quarantined"
        assert quarantine.proposal_id == proposal.id
        assert quarantine.detectors_json["secrets"][0]["detector"] == "api_key"
        assert _count(session, WorkflowMemoryItem) == 0
