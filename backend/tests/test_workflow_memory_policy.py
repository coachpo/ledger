from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.workflow_memory import (
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
)
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
        assert active_items[0].content_fingerprint == proposal.content_fingerprint
        assert active_items[0].content_json == {"text": "Revenue increased."}


def test_repeated_policy_evaluation_does_not_duplicate_activation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal = _stage_candidate(session)
        policy = _policy(default_decision="commit")

        first_decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=policy,
        )
        second_decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
            proposal=proposal,
            policy=policy,
        )
        session.commit()

        active_items = list(session.scalars(select(WorkflowMemoryItem)))
        decisions = list(session.scalars(select(WorkflowMemoryDecision)))

        assert first_decision.id == second_decision.id
        assert len(active_items) == 1
        assert active_items[0].proposal_id == proposal.id
        assert len(decisions) == 1


def test_review_lists_and_actions_filter_to_default_owner(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = WorkflowMemoryPolicyService(session)
        repo = service.repository
        default_proposal = _stage_candidate(session)
        other_result = WorkflowMemoryProposalService(session).stage_candidates(
            scope=_scope(),
            candidates=(
                WorkflowMemoryProposalCandidate(
                    kind="fact",
                    namespace="research",
                    content={"text": "Other owner should stay hidden."},
                    reason="runtime output",
                    source_output_path="steps.summarize.output.memory[1]",
                ),
            ),
            run_id=501,
            invocation_id="invoke-policy-other-owner",
            owner_type="local_user",
            owner_id="other",
        )
        other_proposal = other_result.proposals[0]
        default_proposal.status = "review_pending"
        other_proposal.status = "review_pending"
        _ = repo.record_audit_event(
            event_type="memory_policy_review",
            target_type="proposal",
            target_id=default_proposal.proposal_id,
            package_key=default_proposal.package_key,
            workflow_key=default_proposal.workflow_key,
            run_id=501,
        )
        _ = repo.record_audit_event(
            event_type="memory_policy_review",
            target_type="proposal",
            target_id=other_proposal.proposal_id,
            owner_type="local_user",
            owner_id="other",
            package_key=other_proposal.package_key,
            workflow_key=other_proposal.workflow_key,
            run_id=501,
        )
        _ = repo.quarantine_proposal(
            proposal=default_proposal,
            reason_code="default_owner_review",
            run_id=501,
        )
        _ = repo.quarantine_proposal(
            proposal=other_proposal,
            reason_code="other_owner_review",
            run_id=501,
        )
        _ = repo.record_decision(
            decision_id="decision-default-owner-review",
            proposal=default_proposal,
            decision="review",
            reason_code="default_review",
            decided_by="policy",
        )
        _ = repo.record_decision(
            decision_id="decision-other-owner-review",
            proposal=other_proposal,
            decision="review",
            reason_code="default_review",
            decided_by="policy",
        )
        default_item = repo.create_memory_item(
            memory_id="memory-default-owner-review",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Default owner evidence."},
            summary="Default owner evidence",
            run_id=501,
            invocation_id="invoke-policy",
        )
        _ = repo.create_memory_item(
            memory_id="memory-other-owner-review",
            owner_type="local_user",
            owner_id="other",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Other owner evidence."},
            summary="Other owner evidence",
            run_id=501,
            invocation_id="invoke-policy-other-owner",
        )
        session.commit()

        proposals = service.list_review_proposals(status=None, limit=10, offset=0)
        audits = service.list_audit_events(limit=10, offset=0)
        quarantines = service.list_quarantine(unresolved_only=True, limit=10, offset=0)

        assert [proposal.proposal_id for proposal in proposals.items] == [
            default_proposal.proposal_id
        ]
        assert [event.target_id for event in audits.items] == [default_proposal.proposal_id]
        assert [row.proposal_id for row in quarantines.items] == [default_proposal.proposal_id]
        assert [proposal.proposal_id for proposal in repo.list_proposals_for_run(501)] == [
            default_proposal.proposal_id
        ]
        assert [item.memory_id for item in repo.list_memory_items_for_run(501)] == [
            default_item.memory_id
        ]
        assert [proposal.proposal_id for _, proposal in repo.list_decisions_for_run(501)] == [
            default_proposal.proposal_id
        ]
        assert [row.proposal_id for row in repo.list_quarantine_for_run(501)] == [
            default_proposal.id
        ]
        assert [event.target_id for event in repo.list_audit_events_for_run(501)] == [
            default_proposal.proposal_id
        ]
        with pytest.raises(ApiError):
            _ = service.approve_review_pending_proposal(
                proposal_id=other_proposal.proposal_id,
                reason=None,
            )
        refreshed_other = session.get(WorkflowMemoryProposal, other_proposal.id)
        assert refreshed_other is not None
        assert refreshed_other.status == "review_pending"
