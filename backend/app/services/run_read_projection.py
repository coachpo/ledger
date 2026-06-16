from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_memory import (
    WorkflowMemoryAuditEvent,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
)
from app.models.workflow_package import WorkflowPackage
from app.repositories.run import RunRepository
from app.repositories.workflow_checkpoints import WorkflowCheckpointRepository
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.run import (
    RunInvocationResourceScope,
    RunProgressRead,
    RunQueueRead,
    RunQueueReason,
    RunQueueState,
    RunRead,
    RunScheduleProvenanceRead,
    RunStatus,
    RunStepStatus,
    RunTargetKind,
    RunWorkflowMemoryEvidenceRead,
)
from app.services.extension_dependency_service import ExtensionDependencyService

_WorkflowPackageSnapshotResolver = Callable[[Run], RunWorkflowPackageSnapshot]


@dataclass(frozen=True)
class _RunInvocationIdentityContext:
    scope: RunInvocationResourceScope
    output_schema_keys_by_local_id: dict[int, str]


class RunReadProjection:
    def __init__(
        self,
        *,
        session: Session,
        run_repository: RunRepository,
        workflow_package_repository: WorkflowPackageRepository,
        workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver,
    ) -> None:
        self.session: Session = session
        self.run_repository: RunRepository = run_repository
        self.workflow_package_repository: WorkflowPackageRepository = workflow_package_repository
        self.workflow_memory_repository: WorkflowMemoryRepository = WorkflowMemoryRepository(
            session
        )
        self.workflow_checkpoint_repository: WorkflowCheckpointRepository = (
            WorkflowCheckpointRepository(session)
        )
        self._workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver = (
            workflow_package_snapshot_for_run
        )

    def to_read_model(self, run: Run) -> RunRead:
        return self._to_read_model(run)

    def package_provenance_payload(self, run: Run) -> dict[str, Any] | None:
        return self._package_provenance_payload(run)

    @staticmethod
    def schedule_provenance_payload(run: Run) -> RunScheduleProvenanceRead | None:
        if run.schedule_provenance is None:
            return None
        return RunScheduleProvenanceRead.model_validate(run.schedule_provenance)

    @staticmethod
    def queue_from_run(
        run: Run,
        *,
        serial_blocker_run_id: int | None,
    ) -> RunQueueRead | None:
        if run.status != RunStatus.QUEUED.value:
            return None
        if serial_blocker_run_id is not None:
            return RunQueueRead.model_validate(
                {
                    "state": RunQueueState.BLOCKED.value,
                    "reason": RunQueueReason.BLOCKED_BY_PACKAGE_SERIAL_POLICY.value,
                    "message": (
                        f"Queued behind run #{serial_blocker_run_id} from the same "
                        "Workflow Package because package runs execute one at a time."
                    ),
                    "blockingRunId": serial_blocker_run_id,
                }
            )
        return RunQueueRead.model_validate(
            {
                "state": RunQueueState.WAITING.value,
                "reason": RunQueueReason.AWAITING_WORKER_CAPACITY.value,
                "message": "Eligible to run and waiting for an available scheduler worker.",
                "blockingRunId": None,
            }
        )

    @staticmethod
    def progress_from_status_counts(
        status_counts: Mapping[str, int],
        *,
        run_status: str,
    ) -> RunProgressRead:
        counts = {
            status.value: max(0, int(status_counts.get(status.value, 0)))
            for status in RunStepStatus
        }
        terminal_count = (
            counts[RunStepStatus.SUCCEEDED.value]
            + counts[RunStepStatus.FAILED.value]
            + counts[RunStepStatus.SKIPPED.value]
        )
        total_count = sum(counts.values())
        if run_status in {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}:
            percent = 100
        else:
            percent = 0 if total_count == 0 else terminal_count * 100 // total_count
        return RunProgressRead.model_validate(
            {
                "unit": "invocation",
                "terminalCount": terminal_count,
                "totalCount": total_count,
                "percent": percent,
            }
        )

    def _to_read_model(self, run: Run) -> RunRead:
        identity_context = self._invocation_identity_context(run)
        return RunRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "input": run.input,
                "sourceRunId": run.source_run_id,
                "lineageRootRunId": run.lineage_root_run_id,
                "replayStepIndex": run.forked_from_step_index,
                "resumeStepIndex": run.resume_step_index,
                "finalOutput": run.final_output,
                "status": run.status,
                "progress": self._progress_for_loaded_run(run),
                "queue": self.queue_from_run(
                    run,
                    serial_blocker_run_id=self.run_repository.serial_queue_blocker_run_ids_by_run_id(
                        [run.id]
                    ).get(
                        run.id
                    ),
                ),
                "scheduleId": run.schedule_id,
                "scheduleFireId": run.schedule_fire_id,
                "scheduledFor": run.scheduled_for,
                "scheduleReason": run.schedule_reason,
                "scheduleProvenance": self.schedule_provenance_payload(run),
                "totalTokens": run.total_tokens,
                "inheritedTokens": run.inherited_tokens,
                "executedTokens": run.executed_tokens,
                "traceId": run.trace_id,
                "error": run.error,
                "queuedAt": run.queued_at,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
                "createdAt": run.created_at,
                "updatedAt": run.updated_at,
                "steps": [
                    self._to_step_read(step, identity_context=identity_context)
                    for step in sorted(
                        cast(list[RunStep], run.steps),
                        key=lambda item: (item.step_index, item.id),
                    )
                ],
                "workflowMemoryEvidence": self._workflow_memory_evidence(run),
                "extensionDependencies": ExtensionDependencyService.normalize_dependency_payloads(
                    run.extension_dependencies
                ),
                "packageProvenance": self._package_provenance_payload(run),
            }
        )

    def _progress_for_loaded_run(self, run: Run) -> RunProgressRead:
        status_counts: dict[str, int] = {}
        for step in cast(list[RunStep], run.steps):
            for invocation in cast(list[RunAgentInvocation], step.invocations):
                self._add_progress_status(status_counts, invocation.status)
            for operation in cast(list[RunOperationInvocation], step.operation_invocations):
                self._add_progress_status(status_counts, operation.status)
        return self.progress_from_status_counts(status_counts, run_status=run.status)

    @staticmethod
    def _add_progress_status(status_counts: dict[str, int], status: str) -> None:
        status_counts[status] = status_counts.get(status, 0) + 1

    def _package_provenance_payload(self, run: Run) -> dict[str, Any] | None:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return None
        snapshot = self._workflow_package_snapshot_for_run(run)
        package = self.workflow_package_repository.get(snapshot.workflow_package_id)
        return {
            "workflowPackageId": snapshot.workflow_package_id,
            "workflowPackageKey": snapshot.workflow_package_key,
            "workflowPackageName": snapshot.workflow_package_name,
            "workflowPackageDescription": snapshot.workflow_package_description,
            "workflowPackageStatus": snapshot.workflow_package_status,
            "workflowPackageManifestHash": snapshot.manifest_hash,
            "workflowPackageCompiledHash": snapshot.compiled_hash,
            "workflowKey": snapshot.workflow_key,
            "workflowName": snapshot.workflow_name,
            "workflowDescription": snapshot.workflow_description,
            "manifestSource": snapshot.manifest_source,
            "packageDefinition": deepcopy(snapshot.package_definition),
            "compiledPlan": deepcopy(snapshot.compiled_plan),
            "launchSnapshot": self._package_launch_snapshot_payload(snapshot),
            "extensionDependencies": deepcopy(snapshot.extension_dependencies),
            "localResourceRefs": deepcopy(snapshot.local_resource_refs),
            # Historical effective runtime profile evidence stays read-safe here.
            "resolvedModelConnections": deepcopy(snapshot.resolved_model_connections),
            # Historical readiness evidence is preserved separately from current launch checks.
            "preflightSummary": deepcopy(snapshot.preflight_summary),
            # Current package audit is display-only and never used to rebind the run.
            "currentPackage": self._current_package_audit_payload(snapshot, package),
        }

    @staticmethod
    def _package_launch_snapshot_payload(
        snapshot: RunWorkflowPackageSnapshot,
    ) -> dict[str, Any]:
        return {
            "workflowKey": snapshot.workflow_key,
            "workflowName": snapshot.workflow_name,
            "workflowDescription": snapshot.workflow_description,
            "inputSchema": deepcopy(snapshot.input_schema),
            "parameters": deepcopy(snapshot.launch_parameters),
        }

    @staticmethod
    def _current_package_audit_payload(
        snapshot: RunWorkflowPackageSnapshot,
        package: WorkflowPackage | None,
    ) -> dict[str, Any]:
        if package is None:
            return {
                "available": False,
                "manifestHash": None,
                "compiledHash": None,
                "manifestHashMatchesSnapshot": None,
                "compiledHashMatchesSnapshot": None,
                "unavailableReason": "missingPackage",
            }
        return {
            "available": True,
            "manifestHash": package.manifest_hash,
            "compiledHash": package.compiled_hash,
            "manifestHashMatchesSnapshot": package.manifest_hash == snapshot.manifest_hash,
            "compiledHashMatchesSnapshot": package.compiled_hash == snapshot.compiled_hash,
            "unavailableReason": None,
        }

    def _workflow_memory_evidence(self, run: Run) -> RunWorkflowMemoryEvidenceRead:
        proposals = self.workflow_memory_repository.list_proposals_for_run(run.id)
        memory_items = self.workflow_memory_repository.list_memory_items_for_run(run.id)
        decisions = self.workflow_memory_repository.list_decisions_for_run(run.id)
        quarantines = self.workflow_memory_repository.list_quarantine_for_run(run.id)
        audit_events = self.workflow_memory_repository.list_audit_events_for_run(run.id)
        checkpoints = self._workflow_memory_checkpoints(run)
        memory_ids_by_proposal_id = self._memory_ids_by_proposal_id(memory_items)

        return RunWorkflowMemoryEvidenceRead.model_validate(
            {
                "injections": self._workflow_memory_injections(run),
                "proposals": [
                    self._workflow_memory_proposal_payload(
                        proposal,
                        active_memory_ids=memory_ids_by_proposal_id.get(proposal.id, []),
                    )
                    for proposal in proposals
                ],
                "decisions": [
                    self._workflow_memory_decision_payload(decision, proposal=proposal)
                    for decision, proposal in decisions
                ],
                "quarantines": [
                    self._workflow_memory_quarantine_payload(quarantine)
                    for quarantine in quarantines
                ],
                "checkpoints": [
                    self._workflow_memory_checkpoint_payload(checkpoint)
                    for checkpoint in checkpoints
                ],
                "auditEvents": [
                    self._workflow_memory_audit_event_payload(event) for event in audit_events
                ],
            }
        )

    @staticmethod
    def _memory_ids_by_proposal_id(
        memory_items: list[WorkflowMemoryItem],
    ) -> dict[int | None, list[str]]:
        grouped: dict[int | None, list[str]] = {}
        for item in memory_items:
            grouped.setdefault(item.proposal_id, []).append(item.memory_id)
        return grouped

    def _workflow_memory_checkpoints(self, run: Run) -> list[WorkflowCheckpoint]:
        package_key = run.workflow_package_key
        workflow_key = run.workflow_package_workflow_key
        if (
            package_key is None or workflow_key is None
        ) and run.workflow_package_snapshot is not None:
            package_key = run.workflow_package_snapshot.workflow_package_key
            workflow_key = run.workflow_package_snapshot.workflow_key
        if package_key is None or workflow_key is None:
            return []
        return self.workflow_checkpoint_repository.list_checkpoints_for_run(
            package_key=package_key,
            workflow_key=workflow_key,
            run_id=run.id,
        )

    def _workflow_memory_injections(self, run: Run) -> list[dict[str, Any]]:
        injections: list[dict[str, Any]] = []
        for step in sorted(
            cast(list[RunStep], run.steps),
            key=lambda item: (item.step_index, item.id),
        ):
            for invocation in sorted(
                cast(list[RunAgentInvocation], step.invocations),
                key=lambda item: (item.position, item.id),
            ):
                workflow_memory = self._workflow_memory_metadata(invocation.graph_metadata)
                if workflow_memory is None:
                    continue
                injections.append(
                    {
                        "runAgentInvocationId": invocation.id,
                        "runStepId": invocation.run_step_id,
                        "stepIndex": invocation.step_index,
                        "slot": invocation.slot,
                        "agentKey": invocation.agent_key,
                        "invocationId": workflow_memory.get("invocationId"),
                        "scope": deepcopy(workflow_memory.get("scope") or {}),
                        "policySnapshot": deepcopy(workflow_memory.get("policySnapshot") or {}),
                        "contextItemIds": list(workflow_memory.get("contextItemIds") or []),
                        "checkpointIds": list(workflow_memory.get("checkpointIds") or []),
                        "completion": deepcopy(workflow_memory.get("completion")),
                    }
                )
        return injections

    @staticmethod
    def _workflow_memory_metadata(graph_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(graph_metadata, dict):
            return None
        model_gateway = graph_metadata.get("modelGateway")
        if not isinstance(model_gateway, dict):
            return None
        workflow_memory = model_gateway.get("workflowMemory")
        if not isinstance(workflow_memory, dict) or workflow_memory.get("enabled") is not True:
            return None
        return workflow_memory

    @staticmethod
    def _workflow_memory_proposal_payload(
        proposal: WorkflowMemoryProposal,
        *,
        active_memory_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "proposalId": proposal.proposal_id,
            "runId": proposal.run_id,
            "invocationId": proposal.invocation_id,
            "packageKey": proposal.package_key,
            "workflowKey": proposal.workflow_key,
            "agentKey": proposal.agent_key,
            "stepId": proposal.step_id,
            "namespace": proposal.namespace,
            "kind": proposal.kind,
            "status": proposal.status,
            "reason": proposal.reason,
            "sourceOutputPath": proposal.source_output_path,
            "detectors": deepcopy(proposal.detectors_json),
            "activeMemoryIds": active_memory_ids,
            "createdAt": proposal.created_at,
            "updatedAt": proposal.updated_at,
        }

    @staticmethod
    def _workflow_memory_decision_payload(
        decision: WorkflowMemoryDecision,
        *,
        proposal: WorkflowMemoryProposal,
    ) -> dict[str, Any]:
        return {
            "decisionId": decision.decision_id,
            "proposalId": proposal.proposal_id,
            "decision": decision.decision,
            "reasonCode": decision.reason_code,
            "reason": decision.reason,
            "policySnapshot": deepcopy(decision.policy_snapshot_json),
            "decidedBy": decision.decided_by,
            "createdAt": decision.created_at,
        }

    def _workflow_memory_quarantine_payload(
        self,
        quarantine: WorkflowMemoryQuarantine,
    ) -> dict[str, Any]:
        proposal = self.workflow_memory_repository.get_proposal_by_id(quarantine.proposal_id)
        memory_item = self.workflow_memory_repository.get_memory_item_by_id(
            quarantine.memory_item_id
        )
        target = proposal if proposal is not None else memory_item
        evidence: dict[str, Any] = {}
        if proposal is not None:
            evidence = deepcopy(proposal.content_json)
        elif memory_item is not None:
            evidence = deepcopy(memory_item.content_json)
        return {
            "quarantineId": quarantine.id,
            "proposalId": proposal.proposal_id if proposal is not None else None,
            "memoryId": memory_item.memory_id if memory_item is not None else None,
            "runId": quarantine.run_id,
            "invocationId": quarantine.invocation_id,
            "packageKey": target.package_key if target is not None else None,
            "workflowKey": target.workflow_key if target is not None else None,
            "agentKey": target.agent_key if target is not None else None,
            "stepId": target.step_id if target is not None else None,
            "namespace": target.namespace if target is not None else None,
            "kind": target.kind if target is not None else None,
            "evidence": evidence,
            "reasonCode": quarantine.reason_code,
            "reason": quarantine.reason,
            "detectors": deepcopy(quarantine.detectors_json),
            "resolvedAt": quarantine.resolved_at,
            "createdAt": quarantine.created_at,
        }

    @staticmethod
    def _workflow_memory_checkpoint_payload(checkpoint: WorkflowCheckpoint) -> dict[str, Any]:
        return {
            "checkpointId": checkpoint.checkpoint_id,
            "checkpointType": checkpoint.checkpoint_type,
            "sequence": checkpoint.sequence,
            "runId": checkpoint.run_id,
            "packageKey": checkpoint.package_key,
            "workflowKey": checkpoint.workflow_key,
            "agentKey": checkpoint.agent_key,
            "stepId": checkpoint.step_id,
            "invocationId": checkpoint.invocation_id,
            "state": deepcopy(checkpoint.state_json),
            "retention": checkpoint.retention,
            "metadata": deepcopy(checkpoint.metadata_json),
            "createdAt": checkpoint.created_at,
        }

    @staticmethod
    def _workflow_memory_audit_event_payload(event: WorkflowMemoryAuditEvent) -> dict[str, Any]:
        return {
            "auditEventId": event.id,
            "eventType": event.event_type,
            "targetType": event.target_type,
            "targetId": event.target_id,
            "runId": event.run_id,
            "invocationId": event.invocation_id,
            "packageKey": event.package_key,
            "workflowKey": event.workflow_key,
            "agentKey": event.agent_key,
            "stepId": event.step_id,
            "event": deepcopy(event.event_json),
            "createdAt": event.created_at,
        }

    def _invocation_identity_context(self, run: Run) -> _RunInvocationIdentityContext:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return _RunInvocationIdentityContext(
                scope=RunInvocationResourceScope.GLOBAL,
                output_schema_keys_by_local_id={},
            )
        snapshot = run.workflow_package_snapshot
        return _RunInvocationIdentityContext(
            scope=RunInvocationResourceScope.PACKAGE_LOCAL,
            output_schema_keys_by_local_id=self._package_local_key_map(
                None if snapshot is None else snapshot.compiled_plan,
                "outputSchemas",
            ),
        )

    @staticmethod
    def _package_local_key_map(
        compiled_plan: dict[str, Any] | None,
        section: str,
    ) -> dict[int, str]:
        if compiled_plan is None:
            return {}
        raw_items = compiled_plan.get(section) or []
        if not isinstance(raw_items, list):
            return {}
        return {
            index: str(item["key"])
            for index, item in enumerate(raw_items, start=1)
            if isinstance(item, dict) and item.get("key") is not None
        }

    def _to_step_read(
        self,
        step: RunStep,
        *,
        identity_context: _RunInvocationIdentityContext,
    ) -> dict[str, Any]:
        return {
            "id": step.id,
            "runId": step.run_id,
            "index": step.step_index,
            "status": step.status,
            "origin": step.origin,
            "sourceRunStepId": step.source_run_step_id,
            "sourceRunId": step.source_run_id,
            "sourceStepIndex": step.source_step_index,
            "graphMetadata": deepcopy(step.graph_metadata),
            "error": step.error,
            "startedAt": step.started_at,
            "finishedAt": step.finished_at,
            "persistedAt": step.persisted_at,
            "createdAt": step.created_at,
            "updatedAt": step.updated_at,
            "invocations": [
                self._to_invocation_read(
                    invocation,
                    identity_context=identity_context,
                )
                for invocation in sorted(
                    cast(list[RunAgentInvocation], step.invocations),
                    key=lambda item: (item.position, item.id),
                )
            ],
            "operationInvocations": [
                self._to_operation_invocation_read(
                    operation,
                    identity_context=identity_context,
                )
                for operation in sorted(
                    cast(list[RunOperationInvocation], step.operation_invocations),
                    key=lambda item: (item.position, item.id),
                )
            ],
        }

    @staticmethod
    def _to_invocation_read(
        invocation: RunAgentInvocation,
        *,
        identity_context: _RunInvocationIdentityContext,
    ) -> dict[str, Any]:
        output_schema_key = identity_context.output_schema_keys_by_local_id.get(
            invocation.output_schema_id
        )
        return {
            "id": invocation.id,
            "runStepId": invocation.run_step_id,
            "runId": invocation.run_id,
            "stepIndex": invocation.step_index,
            "slot": invocation.slot,
            "position": invocation.position,
            "agentId": invocation.agent_id,
            "agentKey": invocation.agent_key,
            "agentVersion": invocation.agent_version,
            "outputSchemaId": invocation.output_schema_id,
            "outputSchemaVersion": invocation.output_schema_version,
            "identityScope": identity_context.scope.value,
            "outputSchemaKey": output_schema_key,
            "inputMode": invocation.input_mode,
            "wiring": invocation.wiring,
            "graphMetadata": deepcopy(invocation.graph_metadata),
            "optional": invocation.optional,
            "status": invocation.status,
            "resolvedInput": invocation.resolved_input,
            "resolvedInputOrigin": invocation.resolved_input_origin,
            "output": invocation.output,
            "outputOrigin": invocation.output_origin,
            "errorCode": invocation.error_code,
            "errorMessage": invocation.error_message,
            "errorDetails": invocation.error_details,
            "tokens": invocation.tokens,
            "durationMs": invocation.duration_ms,
            "traceSpanId": invocation.trace_span_id,
            "sourceInvocationId": invocation.source_invocation_id,
            "startedAt": invocation.started_at,
            "finishedAt": invocation.finished_at,
            "persistedAt": invocation.persisted_at,
            "createdAt": invocation.created_at,
            "updatedAt": invocation.updated_at,
        }

    @staticmethod
    def _to_operation_invocation_read(
        operation: RunOperationInvocation,
        *,
        identity_context: _RunInvocationIdentityContext,
    ) -> dict[str, Any]:
        output_schema_key = identity_context.output_schema_keys_by_local_id.get(
            operation.output_schema_id
        )
        return {
            "id": operation.id,
            "runStepId": operation.run_step_id,
            "runId": operation.run_id,
            "stepIndex": operation.step_index,
            "slot": operation.slot,
            "position": operation.position,
            "operationKey": operation.operation_key,
            "operationKind": operation.operation_kind,
            "outputSchemaId": operation.output_schema_id,
            "outputSchemaVersion": operation.output_schema_version,
            "identityScope": identity_context.scope.value,
            "outputSchemaKey": output_schema_key,
            "method": operation.method,
            "timeoutSeconds": operation.timeout_seconds,
            "requestMetadata": deepcopy(operation.request_metadata),
            "responseMetadata": deepcopy(operation.response_metadata),
            "graphMetadata": deepcopy(operation.graph_metadata),
            "optional": operation.optional,
            "status": operation.status,
            "output": deepcopy(operation.output),
            "outputOrigin": operation.output_origin,
            "errorCode": operation.error_code,
            "errorMessage": operation.error_message,
            "errorDetails": operation.error_details,
            "durationMs": operation.duration_ms,
            "traceSpanId": operation.trace_span_id,
            "sourceOperationInvocationId": operation.source_operation_invocation_id,
            "sourceRunId": operation.source_run_id,
            "sourceRunStepId": operation.source_run_step_id,
            "sourceStepIndex": operation.source_step_index,
            "startedAt": operation.started_at,
            "finishedAt": operation.finished_at,
            "persistedAt": operation.persisted_at,
            "createdAt": operation.created_at,
            "updatedAt": operation.updated_at,
        }


__all__ = ["RunReadProjection"]
