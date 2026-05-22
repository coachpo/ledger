from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.repositories.run import RunRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.memory import MemoryArtifactRead
from app.schemas.run import (
    RunInvocationResourceScope,
    RunMemoryArtifactRead,
    RunMemoryEventRead,
    RunRead,
    RunTargetKind,
)
from app.services.extension_dependency_service import ExtensionDependencyService
from app.services.memory_service import MemoryService

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
        self._workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver = (
            workflow_package_snapshot_for_run
        )

    def to_read_model(self, run: Run) -> RunRead:
        return self._to_read_model(run)

    def package_provenance_payload(self, run: Run) -> dict[str, Any] | None:
        return self._package_provenance_payload(run)

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
                "memoryArtifacts": self._memory_artifact_links(run.id),
                "memoryEvents": self._memory_event_evidence(run.id),
                "extensionDependencies": ExtensionDependencyService.normalize_dependency_payloads(
                    run.extension_dependencies
                ),
                "packageProvenance": self._package_provenance_payload(run),
            }
        )

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
            "resolvedModelConnections": deepcopy(snapshot.resolved_model_connections),
            "preflightSummary": deepcopy(snapshot.preflight_summary),
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

    def _memory_artifact_links(self, run_id: int) -> list[RunMemoryArtifactRead]:
        artifacts = MemoryService(self.session).list_run_artifacts(run_id)

        seen_memory_ids: set[str] = set()
        artifact_links: list[RunMemoryArtifactRead] = []
        for artifact in artifacts:
            if artifact.memory_id in seen_memory_ids:
                continue
            seen_memory_ids.add(artifact.memory_id)
            artifact_links.append(self._memory_artifact_link(artifact))
        return artifact_links

    def _memory_event_evidence(self, run_id: int) -> list[RunMemoryEventRead]:
        return [
            RunMemoryEventRead.model_validate(event)
            for event in self.run_repository.list_memory_events_for_run(run_id)
        ]

    @staticmethod
    def _memory_artifact_link(artifact: MemoryArtifactRead) -> RunMemoryArtifactRead:
        return RunMemoryArtifactRead.model_validate(artifact)

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
