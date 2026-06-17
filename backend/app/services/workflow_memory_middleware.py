from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.workflow_memory import WorkflowMemoryDecision, WorkflowMemoryProposal
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
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
from app.services.workflow_memory_detection import detect_workflow_memory_policy_hits
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
    safety_scan: dict[str, Any] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)


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
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

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
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            owner_type=owner_type,
            owner_id=owner_id,
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
        query_terms: tuple[str, ...] = (),
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            request=WorkflowMemoryContextRequest(
                scope=scope,
                policy=policy,
                query_terms=query_terms,
                owner_type=owner_type,
                owner_id=owner_id,
            )
        )
        context, safety_scan = self._scan_context_before_injection(
            context=context,
            policy=policy,
            run_id=run_id,
            invocation_id=invocation_id,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        checkpoints = self._checkpoint_context(
            policy=policy,
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run_id,
            owner_type=owner_type,
            owner_id=owner_id,
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
                safety_scan=safety_scan,
                ranking=context.ranking,
            ),
        )

    def _scan_context_before_injection(
        self,
        *,
        context: WorkflowMemoryContextPack,
        policy: PackageResolvedMemoryPolicy,
        run_id: int,
        invocation_id: str,
        owner_type: str,
        owner_id: str,
    ) -> tuple[WorkflowMemoryContextPack, dict[str, Any]]:
        safe_items = []
        excluded: list[dict[str, Any]] = []
        for item in context.items:
            detected = detect_workflow_memory_policy_hits(item.content)
            reason_code, action = self._pre_injection_action(detected=detected, policy=policy)
            if reason_code is None:
                safe_items.append(item)
                continue
            excluded.append(
                {
                    "itemId": item.item_id,
                    "reasonCode": reason_code,
                    "action": action,
                    "detectors": detected,
                }
            )
            self._record_pre_injection_exclusion(
                item_id=item.item_id,
                scope=item.scope,
                run_id=run_id,
                invocation_id=invocation_id,
                reason_code=reason_code,
                action=action,
                detectors=detected,
                owner_type=owner_type,
                owner_id=owner_id,
            )
        safety_scan = {
            "preInjectionScan": True,
            "scannedItemIds": [item.item_id for item in context.items],
            "contextItemIds": [item.item_id for item in safe_items],
            "excludedItemIds": [item["itemId"] for item in excluded],
            "quarantinedItemIds": [
                item["itemId"] for item in excluded if item["action"] == "quarantine"
            ],
            "auditOnlyItemIds": [
                item["itemId"] for item in excluded if item["action"] == "audit"
            ],
            "excluded": excluded,
        }
        scanned_context = context.model_copy(
            update={"items": safe_items, "safety_scan": safety_scan}
        )
        return scanned_context, safety_scan

    def _pre_injection_action(
        self,
        *,
        detected: dict[str, list[dict[str, str]]],
        policy: PackageResolvedMemoryPolicy,
    ) -> tuple[str | None, str | None]:
        if detected.get("secrets"):
            return "secret_detected", "quarantine"
        for category, reason_code in (
            ("promptInjection", "prompt_injection_detected"),
            ("instructionOverride", "instruction_override_detected"),
            ("toolOutputPoisoning", "tool_output_poisoning_detected"),
            ("exfiltration", "exfiltration_detected"),
        ):
            if detected.get(category):
                return reason_code, "quarantine"
        if detected.get("sensitiveData"):
            action = policy.policy.sensitive_data if policy.policy is not None else "review"
            return "sensitive_data_detected", "quarantine" if action == "quarantine" else "audit"
        return None, None

    def _record_pre_injection_exclusion(
        self,
        *,
        item_id: str,
        scope: WorkflowMemoryScope,
        run_id: int,
        invocation_id: str,
        reason_code: str,
        action: str | None,
        detectors: dict[str, list[dict[str, str]]],
        owner_type: str,
        owner_id: str,
    ) -> None:
        memory_item = self.repository.get_memory_item_by_public_id(
            item_id,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        if action == "quarantine" and memory_item is not None:
            _ = self.repository.quarantine_memory_item(
                memory_item=memory_item,
                reason_code=reason_code,
                reason="Excluded by workflow memory pre-injection safety scan.",
                run_id=run_id,
                invocation_id=invocation_id,
                detectors_json=detectors,
            )
        _ = self.repository.record_audit_event(
            event_type="memory_pre_injection_scan_exclude",
            target_type="memory_item",
            target_id=item_id,
            owner_type=owner_type,
            owner_id=owner_id,
            package_key=scope.package_key,
            workflow_key=scope.workflow_key,
            agent_key=scope.agent_key,
            step_id=scope.step_id,
            run_id=run_id,
            invocation_id=invocation_id,
            event_json={
                "reasonCode": reason_code,
                "action": action,
                "detectors": detectors,
                "preInjectionScan": True,
            },
        )
        self.session.flush()

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
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            owner_type=owner_type,
            owner_id=owner_id,
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
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            owner_type=owner_type,
            owner_id=owner_id,
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
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            owner_type=owner_type,
            owner_id=owner_id,
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
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
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
            owner_type=owner_type,
            owner_id=owner_id,
        )
        return WorkflowMemoryCheckpointResult(checkpoint=checkpoint)

    def _checkpoint_context(
        self,
        *,
        policy: PackageResolvedMemoryPolicy,
        package_key: str,
        workflow_key: str,
        run_id: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> tuple[WorkflowCheckpointRead, ...]:
        if not policy.checkpoints or not policy.checkpoints.enabled:
            return ()
        return tuple(
            self.checkpoint_service.list_for_run(
                package_key=package_key,
                workflow_key=workflow_key,
                run_id=run_id,
                owner_type=owner_type,
                owner_id=owner_id,
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
