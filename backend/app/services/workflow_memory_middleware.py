from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.workflow_memory import WorkflowMemoryDecision, WorkflowMemoryProposal
from app.schemas.workflow_memory import (
    WorkflowCheckpointRead,
    WorkflowCheckpointRecord,
    WorkflowCheckpointScope,
    WorkflowMemoryContextPack,
    WorkflowMemoryContextRequest,
    WorkflowMemoryScope,
)
from app.services.execution_plan import PackageResolvedMemoryPolicy
from app.services.workflow_checkpoint_service import WorkflowCheckpointService
from app.services.workflow_memory_context_service import WorkflowMemoryContextService
from app.services.workflow_memory_policy_service import WorkflowMemoryPolicyService
from app.services.workflow_memory_proposal_service import WorkflowMemoryProposalService


@dataclass(frozen=True)
class WorkflowMemoryInvocationMetadata:
    enabled: bool
    scope: WorkflowMemoryScope
    run_id: int | None = None
    invocation_id: str | None = None
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    context_item_ids: tuple[str, ...] = ()
    checkpoint_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowMemoryPreparation:
    context: WorkflowMemoryContextPack
    checkpoints: tuple[WorkflowCheckpointRead, ...]
    metadata: WorkflowMemoryInvocationMetadata


@dataclass(frozen=True)
class WorkflowMemoryCompletion:
    proposals: tuple[WorkflowMemoryProposal, ...] = ()
    decisions: tuple[WorkflowMemoryDecision, ...] = ()
    rejected_count: int = 0


@dataclass(frozen=True)
class WorkflowMemoryCheckpointResult:
    checkpoint: WorkflowCheckpointRead | None = None


class WorkflowMemoryMiddleware:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.context_service: WorkflowMemoryContextService = WorkflowMemoryContextService(session)
        self.proposal_service: WorkflowMemoryProposalService = WorkflowMemoryProposalService(
            session
        )
        self.policy_service: WorkflowMemoryPolicyService = WorkflowMemoryPolicyService(session)
        self.checkpoint_service: WorkflowCheckpointService = WorkflowCheckpointService(session)

    def begin_step(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        step_id: str,
        sequence: int,
        state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowMemoryCheckpointResult:
        return self._record_checkpoint_if_enabled(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run_id,
            step_id=step_id,
            checkpoint_type="step_begin",
            sequence=sequence,
            state=state or {},
            metadata=metadata or {"phase": "begin_step"},
        )

    def prepare_invocation(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        agent_key: str,
        step_id: str,
        invocation_id: str,
        namespace: str | None = None,
    ) -> WorkflowMemoryPreparation:
        scope = self._memory_scope(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace,
        )
        if not policy.enabled:
            context = WorkflowMemoryContextPack(items=[], policy_scope=scope)
            return WorkflowMemoryPreparation(
                context=context,
                checkpoints=(),
                metadata=WorkflowMemoryInvocationMetadata(
                    enabled=False,
                    scope=scope,
                    run_id=run_id,
                    invocation_id=invocation_id,
                ),
            )

        context = self.context_service.build_context_pack(
            request=WorkflowMemoryContextRequest(scope=scope, policy=policy)
        )
        checkpoints = self._checkpoint_context(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run_id,
        )
        return WorkflowMemoryPreparation(
            context=context,
            checkpoints=checkpoints,
            metadata=WorkflowMemoryInvocationMetadata(
                enabled=True,
                scope=scope,
                run_id=run_id,
                invocation_id=invocation_id,
                policy_snapshot=self._policy_snapshot(policy),
                context_item_ids=tuple(item.item_id for item in context.items),
                checkpoint_ids=tuple(checkpoint.checkpoint_id for checkpoint in checkpoints),
            ),
        )

    def complete_invocation(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        scope: WorkflowMemoryScope,
        runtime_output: dict[str, Any],
        runtime_metadata: dict[str, Any] | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
        source_output_path: str | None = None,
    ) -> WorkflowMemoryCompletion:
        if not policy.enabled or policy.writes is None or not policy.writes.proposals:
            return WorkflowMemoryCompletion()

        stage_result = self.proposal_service.stage_from_runtime_output(
            scope=scope,
            runtime_output=runtime_output,
            metadata=runtime_metadata,
            run_id=run_id,
            invocation_id=invocation_id,
            source_output_path=source_output_path,
        )
        decisions = tuple(
            self.policy_service.evaluate_proposal(proposal=proposal, policy=policy)
            for proposal in stage_result.proposals
        )
        return WorkflowMemoryCompletion(
            proposals=stage_result.proposals,
            decisions=decisions,
            rejected_count=stage_result.rejected_count,
        )

    def finalize_step(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        step_id: str,
        sequence: int,
        state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowMemoryCheckpointResult:
        return self._record_checkpoint_if_enabled(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run_id,
            step_id=step_id,
            checkpoint_type="step_finalize",
            sequence=sequence,
            state=state or {},
            metadata=metadata or {"phase": "finalize_step"},
        )

    def finalize_run(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        sequence: int,
        state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowMemoryCheckpointResult:
        return self._record_checkpoint_if_enabled(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run_id,
            checkpoint_type="run_finalize",
            sequence=sequence,
            state=state or {},
            metadata=metadata or {"phase": "finalize_run"},
        )

    def _record_checkpoint_if_enabled(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        checkpoint_type: str,
        sequence: int,
        state: dict[str, Any],
        metadata: dict[str, Any],
        step_id: str | None = None,
    ) -> WorkflowMemoryCheckpointResult:
        if not policy.enabled or policy.checkpoints is None or not policy.checkpoints.enabled:
            return WorkflowMemoryCheckpointResult()
        checkpoint = self.checkpoint_service.record_checkpoint(
            scope=WorkflowCheckpointScope(
                package_key=package_key,
                workflow_key=workflow_key,
                run_id=run_id,
                step_id=step_id,
            ),
            checkpoint=WorkflowCheckpointRecord(
                checkpoint_type=checkpoint_type,
                sequence=sequence,
                state=state,
                retention=policy.checkpoints.retention,
                metadata=metadata,
            ),
        )
        return WorkflowMemoryCheckpointResult(checkpoint=checkpoint)

    def _checkpoint_context(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
    ) -> tuple[WorkflowCheckpointRead, ...]:
        if not policy.checkpoints or not policy.checkpoints.enabled:
            return ()
        return tuple(
            self.checkpoint_service.list_for_run(
                package_key=package_key,
                workflow_key=workflow_key,
                run_id=run_id,
            )
        )

    def _memory_scope(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespace: str | None,
    ) -> WorkflowMemoryScope:
        if namespace is None and policy.retrieval is not None and policy.retrieval.namespaces:
            namespace = policy.retrieval.namespaces[0]
        return WorkflowMemoryScope(
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace or "default",
        )

    def _policy_snapshot(self, policy: PackageResolvedMemoryPolicy) -> dict[str, Any]:
        return {
            "enabled": policy.enabled,
            "retrieval": policy.retrieval.__dict__ if policy.retrieval is not None else None,
            "writes": policy.writes.__dict__ if policy.writes is not None else None,
            "policy": policy.policy.__dict__ if policy.policy is not None else None,
            "checkpoints": policy.checkpoints.__dict__ if policy.checkpoints is not None else None,
        }


__all__ = [
    "WorkflowMemoryCheckpointResult",
    "WorkflowMemoryCompletion",
    "WorkflowMemoryInvocationMetadata",
    "WorkflowMemoryMiddleware",
    "WorkflowMemoryPreparation",
]
