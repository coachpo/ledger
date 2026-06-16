from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.workflow_memory import WorkflowMemoryDecision, WorkflowMemoryItem
from app.schemas.workflow_memory import (
    WorkflowMemoryContextRequest,
    WorkflowMemoryProposalCandidate,
    WorkflowMemoryScope,
)
from app.services.execution_plan import (
    MemoryDefaultDecision,
    PackageMemoryDetectorPolicy,
    PackageMemoryRetrievalPolicy,
    PackageMemoryWritePolicy,
    PackageResolvedMemoryPolicy,
)
from app.services.workflow_memory_context_service import WorkflowMemoryContextService
from app.services.workflow_memory_policy_service import WorkflowMemoryPolicyService
from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService


def _scope(namespace: str = "research") -> WorkflowMemoryScope:
    return WorkflowMemoryScope(
        package_key="memory_api_pkg",
        workflow_key="memory_review_workflow",
        agent_key="analyst",
        step_id="review_step",
        namespace=namespace,
    )


def _policy(*, default_decision: MemoryDefaultDecision = "review") -> PackageResolvedMemoryPolicy:
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
        policy=PackageMemoryDetectorPolicy(secrets="quarantine", sensitive_data="review"),
    )


def _stage_review_pending_proposal(session: Session, *, text: str = "Revenue increased.") -> str:
    result = WorkflowMemoryProposalService(session).stage_candidates(
        scope=_scope(),
        candidates=(
            WorkflowMemoryProposalCandidate(
                kind="fact",
                namespace="research",
                content={"text": text},
                reason="runtime output",
                source_output_path="steps.review.output.memory[0]",
            ),
        ),
        run_id=701,
        invocation_id="invoke-review-api",
    )
    proposal = result.proposals[0]
    decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
        proposal=proposal,
        policy=_policy(default_decision="review"),
    )
    assert decision.decision == "review"
    session.commit()
    return proposal.proposal_id


def _stage_quarantined_proposal(session: Session) -> str:
    result = WorkflowMemoryProposalService(session).stage_candidates(
        scope=_scope(),
        candidates=(
            WorkflowMemoryProposalCandidate(
                kind="fact",
                namespace="research",
                content={"text": "Use sk-test_abcdefghijklmnopqrstuvwxyz123456 for calls."},
            ),
        ),
        run_id=702,
        invocation_id="invoke-quarantine-api",
    )
    proposal = result.proposals[0]
    decision = WorkflowMemoryPolicyService(session).evaluate_proposal(
        proposal=proposal,
        policy=_policy(default_decision="commit"),
    )
    assert decision.decision == "quarantine"
    session.commit()
    return proposal.proposal_id


def test_approve_review_pending_proposal_creates_active_memory_through_review_policy(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal_id = _stage_review_pending_proposal(session)

    list_before = client.get("/api/memory/proposals")
    approve = client.post(
        f"/api/memory/proposals/{proposal_id}/actions/approve",
        json={"reason": "Reviewed by operator."},
    )
    audit = client.get("/api/memory/audit-events")

    assert list_before.status_code == 200, list_before.json()
    assert [item["proposalId"] for item in list_before.json()["items"]] == [proposal_id]
    assert approve.status_code == 200, approve.json()
    approve_payload = approve.json()
    assert approve_payload["proposal"]["status"] == "committed"
    assert approve_payload["decision"]["decision"] == "commit"
    assert approve_payload["decision"]["decidedBy"] == "review_api"
    assert approve_payload["activeMemoryId"].startswith("workflow_memory_")
    assert audit.status_code == 200, audit.json()
    assert "memory_review_commit" in {item["eventType"] for item in audit.json()["items"]}

    with session_factory() as session:
        active_items = list(session.scalars(select(WorkflowMemoryItem)))
        review_decisions = list(
            session.scalars(
                select(WorkflowMemoryDecision).where(
                    WorkflowMemoryDecision.decided_by == "review_api"
                )
            )
        )
        assert len(active_items) == 1
        assert active_items[0].memory_id == approve_payload["activeMemoryId"]
        assert len(review_decisions) == 1
        assert review_decisions[0].decision == "commit"


def test_reject_review_pending_proposal_records_review_decision_without_active_memory(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal_id = _stage_review_pending_proposal(session, text="Reject this draft.")

    reject = client.post(
        f"/api/memory/proposals/{proposal_id}/actions/reject",
        json={"reason": "Not durable memory."},
    )

    assert reject.status_code == 200, reject.json()
    payload = reject.json()
    assert payload["proposal"]["status"] == "rejected"
    assert payload["decision"]["decision"] == "reject"
    assert payload["decision"]["decidedBy"] == "review_api"
    assert payload["activeMemoryId"] is None

    with session_factory() as session:
        assert list(session.scalars(select(WorkflowMemoryItem))) == []
        review_decision = session.scalar(
            select(WorkflowMemoryDecision).where(WorkflowMemoryDecision.decided_by == "review_api")
        )
        assert review_decision is not None
        assert review_decision.decision == "reject"


def test_quarantine_listing_exposes_evidence_without_runtime_retrieval(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        proposal_id = _stage_quarantined_proposal(session)
        context_pack = WorkflowMemoryContextService(session).build_context_pack(
            request=WorkflowMemoryContextRequest(
                scope=_scope(),
                policy=_policy(default_decision="commit"),
            )
        )
        assert context_pack.items == []

    quarantine = client.get("/api/memory/quarantine")

    assert quarantine.status_code == 200, quarantine.json()
    payload = quarantine.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["proposalId"] == proposal_id
    assert item["reasonCode"] == "secret_detected"
    assert item["evidence"]["text"].startswith("Use sk-test_")
    assert item["detectors"]["secrets"][0]["detector"] == "api_key"


def test_direct_write_lookup_unavailable_and_old_admin_memory_api_removed(
    client: TestClient,
) -> None:
    old_query_payload = {
        "accessContext": {
            "runId": 1,
            "packageKey": "pkg",
            "workflowKey": "workflow",
            "agentKey": "agent",
        },
        "scope": {"scopeType": "run", "scopeKey": "1"},
        "query": "old direct lookup",
    }
    old_write_payload = {
        "kind": "research.note",
        "summary": "Old direct write",
        "content": "Old direct writes must be gone.",
        "scope": {"scopeType": "run", "scopeKey": "1"},
        "provenance": {"runId": 1, "agentKey": "agent", "workflowKey": "workflow"},
    }

    assert client.post("/api/memory", json=old_query_payload).status_code == 404
    assert client.post("/api/memory/proposals", json=old_write_payload).status_code == 405
    assert client.get("/api/memory/admin/entries").status_code == 404
    assert client.post("/api/memory/admin/entries", json=old_write_payload).status_code == 404


def test_route_layer_no_longer_imports_old_memory_service() -> None:
    api_memory = Path("app/api/memory.py").read_text()
    dependencies = Path("app/api/dependencies.py").read_text()

    for forbidden in ("get_memory_service", "MemoryService", "MemoryWriteRequest", "MemoryQuery"):
        assert forbidden not in api_memory
    assert "get_memory_service" not in dependencies
    assert "MemoryService" not in dependencies
