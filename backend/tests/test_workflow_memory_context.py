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


def _retrieval_policy() -> PackageResolvedMemoryPolicy:
    return PackageResolvedMemoryPolicy(
        enabled=True,
        retrieval=PackageMemoryRetrievalPolicy(
            enabled=True,
            namespaces=("research",),
            max_items=5,
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


def test_proposal_service_extracts_normalizes_and_deduplicates_runtime_output(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        from app.models.workflow_memory import WorkflowMemoryProposal
        from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService

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
        assert proposals[0].source_output_path == "steps.summarize.output.memoryProposals"
        assert proposals[1].kind == "decision"
        assert proposals[1].content_json == {"summary": "Increase allocation"}
