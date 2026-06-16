from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.workflow_memory import WorkflowMemoryItem, WorkflowMemoryQuarantine
from app.schemas.workflow_memory import WorkflowMemoryProposalCandidate, WorkflowMemoryScope
from app.services.execution_plan import (
    MemoryDefaultDecision,
    PackageMemoryDetectorPolicy,
    PackageMemoryRetrievalPolicy,
    PackageMemoryWritePolicy,
    PackageResolvedMemoryPolicy,
)
from app.services.workflow_memory_policy_service import WorkflowMemoryPolicyService
from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService


def _scope(namespace: str = "research") -> WorkflowMemoryScope:
    return WorkflowMemoryScope(
        package_key="research_pkg",
        workflow_key="due_diligence",
        agent_key="analyst",
        step_id="summarize",
        namespace=namespace,
    )


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
    )


def _stage_candidate(
    session: Session,
    *,
    scope: WorkflowMemoryScope | None = None,
    content: dict[str, object] | None = None,
    kind: str = "fact",
):
    service = WorkflowMemoryProposalService(session)
    result = service.stage_candidates(
        scope=scope or _scope(),
        candidates=(
            WorkflowMemoryProposalCandidate(
                kind=kind,
                namespace=(scope or _scope()).namespace,
                content=content or {"text": "Revenue increased."},
                reason="runtime output",
                source_output_path="steps.summarize.output.memory[0]",
            ),
        ),
        run_id=501,
        invocation_id="invoke-policy",
    )
    assert len(result.proposals) == 1
    return result.proposals[0]


def test_secret_proposal_is_quarantined_and_never_activated(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal = _stage_candidate(
            session,
            content={"text": "Use sk-test_abcdefghijklmnopqrstuvwxyz123456 for calls."},
        )

        decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=_policy(default_decision="commit"),
        )
        session.commit()

        active_items = list(session.scalars(select(WorkflowMemoryItem)))
        quarantine = session.scalar(select(WorkflowMemoryQuarantine))

        assert decision.decision == "quarantine"
        assert decision.reason_code == "secret_detected"
        assert proposal.status == "quarantined"
        assert active_items == []
        assert quarantine is not None
        assert quarantine.proposal_id == proposal.id
        assert quarantine.detectors_json["secrets"][0]["detector"] == "api_key"


def test_sensitive_data_hit_cannot_auto_commit(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal = _stage_candidate(
            session,
            content={"text": "Contact the CFO at cfo@example.com before publishing."},
        )

        decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=_policy(default_decision="commit"),
        )
        session.commit()

        active_items = list(session.scalars(select(WorkflowMemoryItem)))

        assert decision.decision == "review"
        assert decision.reason_code == "sensitive_data_detected"
        assert proposal.status == "review_pending"
        assert active_items == []
        assert proposal.detectors_json["sensitiveData"][0]["detector"] == "email"


def test_unauthorized_scope_is_rejected_without_active_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal = _stage_candidate(session, scope=_scope(namespace="private"))

        decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=_policy(default_decision="commit"),
        )
        session.commit()

        assert decision.decision == "reject"
        assert decision.reason_code == "unauthorized_scope"
        assert proposal.status == "rejected"
        assert list(session.scalars(select(WorkflowMemoryItem))) == []


def test_safe_authorized_auto_commit_creates_active_memory_only_via_policy(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal = _stage_candidate(session)
        session.flush()
        assert list(session.scalars(select(WorkflowMemoryItem))) == []

        decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=_policy(default_decision="commit"),
        )
        session.commit()

        active_items = list(session.scalars(select(WorkflowMemoryItem)))

        assert decision.decision == "commit"
        assert proposal.status == "committed"
        assert len(active_items) == 1
        assert active_items[0].policy_status == "committed"
        assert active_items[0].lifecycle_status == "active"
        assert active_items[0].proposal_id == proposal.id
        assert active_items[0].content_json == {"text": "Revenue increased."}
