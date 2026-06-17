from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import WorkflowMemoryContextRequest, WorkflowMemoryScope
from app.services.execution_plan import PackageMemoryRetrievalPolicy, PackageResolvedMemoryPolicy
from app.services.workflow_memory_context_service import WorkflowMemoryContextService

UTC_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def _scope(namespace: str = "research") -> WorkflowMemoryScope:
    return WorkflowMemoryScope(
        package_key="research_pkg",
        workflow_key="due_diligence",
        agent_key="analyst",
        step_id="summarize",
        namespace=namespace,
    )


def _retrieval_policy(
    *,
    max_items: int = 5,
    relevance_threshold: float | None = None,
) -> PackageResolvedMemoryPolicy:
    return PackageResolvedMemoryPolicy(
        enabled=True,
        retrieval=PackageMemoryRetrievalPolicy(
            enabled=True,
            namespaces=("research",),
            max_items=max_items,
            relevance_threshold=relevance_threshold,
            include_kinds=("fact", "decision"),
        ),
    )


def test_context_pack_filters_to_authorized_active_committed_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        included = repo.create_memory_item(
            memory_id="mem-context-visible",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Revenue grew year over year."},
            summary="Revenue growth fact",
            provenance_json={"runId": 701, "source": "runtime"},
            valid_from=UTC_NOW - timedelta(minutes=5),
            run_id=701,
            invocation_id="invoke-visible",
        )
        _ = repo.create_memory_item(
            memory_id="mem-context-review",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Review only."},
            summary="Review pending",
            policy_status="review_pending",
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        _ = repo.create_memory_item(
            memory_id="mem-context-private",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="private",
            kind="fact",
            content_json={"text": "Private namespace."},
            summary="Private namespace",
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        _ = repo.create_memory_item(
            memory_id="mem-context-other-agent",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="critic",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Wrong agent."},
            summary="Wrong agent",
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        session.commit()

        pack = WorkflowMemoryContextService(session).build_context_pack(
            request=WorkflowMemoryContextRequest(scope=_scope(), policy=_retrieval_policy()),
            now=UTC_NOW,
        )

        assert pack.authoritative is False
        assert pack.policy_scope == _scope()
        assert [item.item_id for item in pack.items] == [included.memory_id]
        assert pack.items[0].content == {"text": "Revenue grew year over year."}
        assert pack.items[0].kind == "fact"
        assert pack.items[0].namespace == "research"
        assert pack.items[0].provenance == {"runId": 701, "source": "runtime"}
        assert pack.items[0].scope == _scope()
        assert pack.items[0].valid_from == included.valid_from
        assert pack.items[0].created_at == included.created_at


def test_context_pack_filters_owner_before_namespace_scope(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        default_owner = repo.create_memory_item(
            memory_id="mem-default-owner",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Default owner memory."},
            summary="Default owner",
            valid_from=UTC_NOW - timedelta(minutes=5),
        )
        _ = repo.create_memory_item(
            memory_id="mem-other-owner-same-namespace",
            owner_type="local_user",
            owner_id="other",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Other owner memory."},
            summary="Other owner",
            valid_from=UTC_NOW - timedelta(minutes=10),
        )
        session.commit()

        pack = WorkflowMemoryContextService(session).build_context_pack(
            request=WorkflowMemoryContextRequest(scope=_scope(), policy=_retrieval_policy()),
            now=UTC_NOW,
        )

        assert [item.item_id for item in pack.items] == [default_owner.memory_id]


def test_context_pack_ranks_exact_candidates_and_enforces_relevance_threshold(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        relevant_old = repo.create_memory_item(
            memory_id="mem-rank-relevant-old",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="decision",
            content_json={
                "text": "AAPL supplier margin risk is material.",
                "importance": "high",
                "confidence": 0.9,
            },
            summary="AAPL margin risk",
            valid_from=UTC_NOW - timedelta(days=20),
        )
        recent_irrelevant = repo.create_memory_item(
            memory_id="mem-rank-recent-irrelevant",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="fact",
            content_json={"text": "Generic market update."},
            summary="Generic update",
            valid_from=UTC_NOW - timedelta(minutes=1),
        )
        _ = repo.create_memory_item(
            memory_id="mem-rank-review-pending",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="decision",
            content_json={"text": "AAPL supplier margin risk pending review."},
            summary="Pending",
            policy_status="review_pending",
            valid_from=UTC_NOW - timedelta(minutes=1),
        )
        _ = repo.create_memory_item(
            memory_id="mem-rank-superseded",
            package_key="research_pkg",
            workflow_key="due_diligence",
            agent_key="analyst",
            step_id="summarize",
            namespace="research",
            kind="decision",
            content_json={"text": "AAPL supplier margin risk superseded."},
            summary="Superseded",
            lifecycle_status="superseded",
            superseded_by_id=relevant_old.id,
            valid_from=UTC_NOW - timedelta(minutes=1),
        )
        session.commit()

        pack = WorkflowMemoryContextService(session).build_context_pack(
            request=WorkflowMemoryContextRequest(
                scope=_scope(),
                policy=_retrieval_policy(max_items=2, relevance_threshold=0.86),
                query_terms=("aapl", "supplier", "margin", "risk"),
            ),
            now=UTC_NOW,
        )

        assert [item.item_id for item in pack.items] == [relevant_old.memory_id]
        assert recent_irrelevant.memory_id not in [item.item_id for item in pack.items]
        assert pack.ranking["relevanceThreshold"] == 0.86
        assert pack.ranking["queryTermCount"] == 4
        assert pack.ranking["selectedCount"] == 1
        assert pack.ranking["items"][0]["itemId"] == relevant_old.memory_id
        assert pack.ranking["items"][0]["components"]["keywordOverlap"] == 1.0


def test_proposal_service_extracts_normalizes_and_deduplicates_runtime_output(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        from app.models.workflow_memory import WorkflowMemoryProposal
        from app.services.workflow_memory_proposal_service import (
            WorkflowMemoryProposalService,
            workflow_memory_content_fingerprint,
        )

        result = WorkflowMemoryProposalService(session).stage_from_runtime_output(
            scope=_scope(),
            runtime_output={
                "memoryProposals": [
                    {"kind": "FACT", "namespace": " research ", "content": "Revenue grew."},
                    {"kind": "fact", "namespace": "research", "content": "Revenue grew."},
                    {"kind": "decision", "content": {"summary": "Increase allocation"}},
                    {"kind": "unsupported", "content": "skip me"},
                ]
            },
            metadata={
                "memoryProposals": [
                    {"kind": "fact", "namespace": "research", "content": "Revenue grew."},
                ]
            },
            run_id=702,
            invocation_id="invoke-proposals",
            source_output_path="steps.summarize.output.memoryProposals",
        )
        session.commit()

        proposals = session.query(WorkflowMemoryProposal).order_by(WorkflowMemoryProposal.id).all()

        assert len(result.proposals) == 2
        assert result.rejected_count == 1
        assert len(proposals) == 2
        assert proposals[0].kind == "fact"
        assert proposals[0].namespace == "research"
        assert proposals[0].content_json == {"text": "Revenue grew."}
        assert proposals[0].content_fingerprint == workflow_memory_content_fingerprint(
            kind="fact",
            namespace="research",
            content={"text": "Revenue grew."},
        )
        assert len(proposals[0].idempotency_key) == 64
        assert proposals[0].source_output_path == "steps.summarize.output.memoryProposals"
        assert proposals[1].kind == "decision"
        assert proposals[1].content_json == {"summary": "Increase allocation"}


def test_proposal_staging_reuses_existing_row_for_duplicate_idempotency_key(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        from app.models.workflow_memory import WorkflowMemoryProposal
        from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService

        service = WorkflowMemoryProposalService(session)
        first = service.stage_from_runtime_output(
            scope=_scope(),
            runtime_output={
                "memoryProposals": [
                    {
                        "kind": " FACT ",
                        "namespace": " Research ",
                        "content": {"text": " Revenue grew.\r\n", "unused": None},
                        "reason": "first detector reason",
                    }
                ]
            },
            run_id=703,
            invocation_id="invoke-idempotent",
            source_output_path="steps.summarize.output.memoryProposals[0]",
        )
        second = service.stage_from_runtime_output(
            scope=_scope(),
            runtime_output={
                "memoryProposals": [
                    {
                        "kind": "fact",
                        "namespace": "research",
                        "content": {"unused": None, "text": "Revenue grew."},
                        "reason": "retry reason should not affect fingerprint",
                    }
                ]
            },
            run_id=703,
            invocation_id="invoke-idempotent",
            source_output_path="steps.summarize.output.memoryProposals[0]",
        )
        session.commit()

        proposals = session.query(WorkflowMemoryProposal).all()

        assert len(proposals) == 1
        assert first.proposals == second.proposals
        assert first.proposals[0].id == second.proposals[0].id
        assert first.proposals[0].content_json == {"text": "Revenue grew."}


def test_proposal_staging_allows_same_idempotency_key_across_owners(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        from app.models.workflow_memory import WorkflowMemoryProposal
        from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService

        runtime_output = {
            "memoryProposals": [
                {
                    "kind": "fact",
                    "namespace": "research",
                    "content": {"text": "Revenue grew."},
                    "reason": "runtime output",
                }
            ]
        }
        service = WorkflowMemoryProposalService(session)

        default_owner = service.stage_from_runtime_output(
            scope=_scope(),
            runtime_output=runtime_output,
            run_id=704,
            invocation_id="invoke-owner-idempotency",
            source_output_path="steps.summarize.output.memoryProposals[0]",
        )
        other_owner = service.stage_from_runtime_output(
            scope=_scope(),
            runtime_output=runtime_output,
            run_id=704,
            invocation_id="invoke-owner-idempotency",
            source_output_path="steps.summarize.output.memoryProposals[0]",
            owner_type="local_user",
            owner_id="other",
        )
        same_owner_retry = service.stage_from_runtime_output(
            scope=_scope(),
            runtime_output=runtime_output,
            run_id=704,
            invocation_id="invoke-owner-idempotency",
            source_output_path="steps.summarize.output.memoryProposals[0]",
        )
        session.commit()

        proposals = session.query(WorkflowMemoryProposal).order_by(WorkflowMemoryProposal.id).all()

        assert len(proposals) == 2
        assert default_owner.proposals[0].id == same_owner_retry.proposals[0].id
        assert default_owner.proposals[0].id != other_owner.proposals[0].id
        assert (
            default_owner.proposals[0].idempotency_key
            == other_owner.proposals[0].idempotency_key
        )
        assert [proposal.owner_id for proposal in proposals] == ["default", "other"]
