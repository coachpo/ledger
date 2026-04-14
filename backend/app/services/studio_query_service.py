from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.core.errors import not_found_error
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.repositories.runtime_approval import RuntimeApprovalRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_run_artifact import RuntimeRunArtifactRepository
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.schemas.runtime import (
    ApprovalDetailSummary,
    CapabilityRef,
    ResolvedCapabilityRead,
    RuntimeApprovalListItem,
    RuntimeApprovalListRead,
    RuntimeApprovalRead,
    RuntimeApprovalStatus,
    RuntimeArtifactListRead,
    RuntimeArtifactRead,
    RuntimeCallerType,
    RuntimeRunListItem,
    RuntimeRunListRead,
    RuntimeRunRead,
    RuntimeTraceEventListRead,
    RuntimeTraceEventRead,
    RuntimeTraceEventType,
    WorkflowAgentRef,
)


class StudioQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.run_repository = RuntimeRunRepository(session)
        self.artifact_repository = RuntimeRunArtifactRepository(session)
        self.approval_repository = RuntimeApprovalRepository(session)
        self.trace_event_repository = RuntimeTraceEventRepository(session)

    def list_runs(
        self,
        *,
        caller_type: RuntimeCallerType | None = None,
        caller_id: int | None = None,
        caller_scope_key: str | None = None,
        caller_identity_key: str | None = None,
        workflow_spec_key: str | None = None,
    ) -> RuntimeRunListRead:
        runs = self.run_repository.list_all(
            caller_type=caller_type.value if caller_type is not None else None,
            caller_id=caller_id,
            caller_scope_key=caller_scope_key,
            caller_identity_key=caller_identity_key,
            workflow_spec_key=workflow_spec_key,
        )
        return RuntimeRunListRead(
            items=[RuntimeRunListItem.model_validate(run) for run in runs],
            next_cursor=None,
        )

    def get_run(self, run_id: int) -> RuntimeRunRead:
        run = self._get_run_or_raise(run_id)
        artifact = self._get_artifact_or_raise(run_id)
        return self._serialize_run(run, artifact)

    def get_artifact(self, run_id: int) -> RuntimeArtifactRead:
        run = self._get_run_or_raise(run_id)
        artifact = self._get_artifact_or_raise(run_id)
        return self._serialize_artifact(run, artifact)

    def list_artifacts(
        self,
        *,
        run_id: int | None = None,
        caller_type: RuntimeCallerType | None = None,
        caller_id: int | None = None,
        workflow_spec_key: str | None = None,
        persona_profile_key: str | None = None,
        capability_key: str | None = None,
    ) -> RuntimeArtifactListRead:
        artifacts = self.artifact_repository.list_all(
            run_id=run_id,
            caller_type=caller_type.value if caller_type is not None else None,
            caller_id=caller_id,
            workflow_spec_key=workflow_spec_key,
            persona_profile_key=persona_profile_key,
            capability_key=capability_key,
        )
        runs_by_id = self._load_runs_by_id(artifact.run_id for artifact in artifacts)
        return RuntimeArtifactListRead(
            items=[
                self._serialize_artifact(runs_by_id[artifact.run_id], artifact)
                for artifact in artifacts
            ],
            next_cursor=None,
        )

    def list_approvals(
        self,
        *,
        run_id: int | None = None,
        caller_type: RuntimeCallerType | None = None,
        caller_id: int | None = None,
        workflow_spec_key: str | None = None,
        capability_key: str | None = None,
        status: RuntimeApprovalStatus | None = None,
    ) -> RuntimeApprovalListRead:
        approvals = self.approval_repository.list_all(
            run_id=run_id,
            caller_type=caller_type.value if caller_type is not None else None,
            caller_id=caller_id,
            workflow_spec_key=workflow_spec_key,
            capability_key=capability_key,
            status=status.value if status is not None else None,
        )
        runs_by_id = self._load_runs_by_id(approval.run_id for approval in approvals)
        return RuntimeApprovalListRead(
            items=[
                self._serialize_approval_list_item(approval, runs_by_id[approval.run_id])
                for approval in approvals
            ],
            next_cursor=None,
        )

    def get_approval(self, approval_id: int) -> RuntimeApprovalRead:
        approval = self.approval_repository.get(approval_id)
        if approval is None:
            raise not_found_error("Runtime approval")
        run = self._get_run_or_raise(approval.run_id)
        artifact = self._get_artifact_or_raise(approval.run_id)
        return self._serialize_approval(approval, run, artifact)

    def list_trace_events(
        self,
        *,
        run_id: int | None = None,
        caller_type: RuntimeCallerType | None = None,
        caller_id: int | None = None,
        workflow_spec_key: str | None = None,
        capability_key: str | None = None,
        event_type: RuntimeTraceEventType | None = None,
    ) -> RuntimeTraceEventListRead:
        events = self.trace_event_repository.list_all(
            run_id=run_id,
            caller_type=caller_type.value if caller_type is not None else None,
            caller_id=caller_id,
            workflow_spec_key=workflow_spec_key,
            capability_key=capability_key,
            event_type=event_type.value if event_type is not None else None,
        )
        runs_by_id = self._load_runs_by_id(event.run_id for event in events)
        return RuntimeTraceEventListRead(
            items=[
                self._serialize_trace_event(event, runs_by_id[event.run_id]) for event in events
            ],
            next_cursor=None,
        )

    def list_run_trace(self, run_id: int) -> RuntimeTraceEventListRead:
        self._get_run_or_raise(run_id)
        return self.list_trace_events(run_id=run_id)

    def _serialize_run(self, run: RuntimeRun, artifact: RuntimeRunArtifact) -> RuntimeRunRead:
        payload = {
            "id": run.id,
            "status": run.status,
            "caller_type": run.caller_type,
            "caller_id": run.caller_id,
            "caller_scope_key": run.caller_scope_key,
            "caller_identity_key": run.caller_identity_key,
            "execution_kind": run.execution_kind,
            "workflow_spec_key": run.workflow_spec_key,
            "workflow_spec_version": run.workflow_spec_version,
            "agent_spec_key": run.agent_spec_key,
            "agent_spec_version": run.agent_spec_version,
            "attempt_number": run.attempt_number,
            "expires_at": run.expires_at,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "pending_approval_ids": [
                approval.id for approval in self.approval_repository.list_pending_for_run(run.id)
            ],
            "final_output": artifact.final_output,
            "trace_summary": run.trace_summary,
            "approval_summary": run.approval_summary,
            "terminal_error_code": artifact.terminal_error_code,
            "terminal_error_message": artifact.terminal_error_message,
        }
        return RuntimeRunRead.model_validate(payload)

    def _serialize_artifact(
        self,
        run: RuntimeRun,
        artifact: RuntimeRunArtifact,
    ) -> RuntimeArtifactRead:
        payload = {
            "run_id": artifact.run_id,
            "final_output": artifact.final_output,
            "terminal_error_code": artifact.terminal_error_code,
            "terminal_error_message": artifact.terminal_error_message,
            "report_markdown": artifact.report_markdown,
            "normalized_trade_decisions": artifact.normalized_trade_decisions,
            "entry_prompt_hash": artifact.entry_prompt_hash,
            "full_user_prompt_hash": artifact.full_user_prompt_hash,
            "authored_entry_prompt_body": artifact.authored_entry_prompt_body,
            "compiled_entry_prompt_body": artifact.compiled_entry_prompt_body,
            "execution_context_body": artifact.execution_context_body,
            "prompt_report_slug": artifact.prompt_report_slug,
            "raw_mention_handles": artifact.raw_mention_handles,
            "resolved_mentions": artifact.resolved_mentions,
            "mentioned_target_outputs": artifact.mentioned_target_outputs,
            "resolved_persona_profile_refs": artifact.resolved_persona_profile_refs,
            "resolved_workflow_agent_refs": artifact.resolved_workflow_agent_refs,
            "resolved_capabilities": artifact.resolved_capabilities,
            "resolved_builtin_versions": artifact.resolved_builtin_versions,
            "resolved_role_versions": artifact.resolved_role_versions,
            "resolved_character_versions": artifact.resolved_character_versions,
            "resolved_bundle_versions": artifact.resolved_bundle_versions,
            "resolved_tool_versions": artifact.resolved_tool_versions,
            "resolved_connector_versions": artifact.resolved_connector_versions,
            "trace_summary": run.trace_summary,
            "approval_summary": run.approval_summary,
            "created_at": artifact.created_at,
        }
        return RuntimeArtifactRead.model_validate(payload)

    @staticmethod
    def _serialize_approval_list_item(
        approval: RuntimeApproval,
        run: RuntimeRun,
    ) -> RuntimeApprovalListItem:
        return RuntimeApprovalListItem.model_validate(
            {
                "approval_id": approval.id,
                "run_id": approval.run_id,
                "status": approval.status,
                "capability_key": approval.capability_key,
                "step_key": approval.step_key,
                "caller_type": run.caller_type,
                "caller_id": run.caller_id,
                "created_at": approval.created_at,
            }
        )

    def _serialize_approval(
        self,
        approval: RuntimeApproval,
        run: RuntimeRun,
        artifact: RuntimeRunArtifact,
    ) -> RuntimeApprovalRead:
        item = self._serialize_approval_list_item(approval, run)
        return RuntimeApprovalRead.model_validate(
            {
                **item.model_dump(by_alias=True),
                "summary": self._build_approval_detail_summary(approval, artifact),
                "allowed_actions": ["approve", "deny"] if approval.status == "PENDING" else [],
            }
        )

    @staticmethod
    def _serialize_trace_event(
        event: RuntimeTraceEvent,
        run: RuntimeRun,
    ) -> RuntimeTraceEventRead:
        return RuntimeTraceEventRead.model_validate(
            {
                "run_id": event.run_id,
                "event_index": event.event_index,
                "event_type": event.event_type,
                "step_key": event.step_key,
                "capability_key": event.capability_key,
                "caller_type": run.caller_type,
                "caller_id": run.caller_id,
                "created_at": event.created_at,
                "approval_id": event.approval_id,
                "payload": event.payload,
            }
        )

    def _build_approval_detail_summary(
        self,
        approval: RuntimeApproval,
        artifact: RuntimeRunArtifact,
    ) -> ApprovalDetailSummary:
        resolved_capability = self._find_resolved_capability(artifact, approval.capability_key)
        step_capability_ref = self._find_step_capability_ref(
            artifact,
            step_key=approval.step_key,
            capability_key=approval.capability_key,
        )
        approval_mode = (
            step_capability_ref.effective_approval_mode
            if step_capability_ref is not None
            and step_capability_ref.effective_approval_mode is not None
            else resolved_capability.approval_mode if resolved_capability is not None else None
        )
        return ApprovalDetailSummary(
            approval_mode=approval_mode,
            display_name=(
                resolved_capability.display_name if resolved_capability is not None else None
            ),
            transport=resolved_capability.transport if resolved_capability is not None else None,
        )

    @staticmethod
    def _find_resolved_capability(
        artifact: RuntimeRunArtifact,
        capability_key: str,
    ) -> ResolvedCapabilityRead | None:
        for item in artifact.resolved_capabilities:
            capability = ResolvedCapabilityRead.model_validate(item)
            if capability.capability_key == capability_key:
                return capability
        return None

    @staticmethod
    def _find_step_capability_ref(
        artifact: RuntimeRunArtifact,
        *,
        step_key: str,
        capability_key: str,
    ) -> CapabilityRef | None:
        for raw_ref in artifact.resolved_workflow_agent_refs or []:
            workflow_ref = WorkflowAgentRef.model_validate(raw_ref)
            if workflow_ref.step_key != step_key:
                continue
            for capability_ref in workflow_ref.capability_refs:
                if capability_ref.capability_key == capability_key:
                    return capability_ref
        return None

    def _load_runs_by_id(self, run_ids: Iterable[int]) -> dict[int, RuntimeRun]:
        return {run.id: run for run in self.run_repository.list_by_ids(run_ids)}

    def _get_run_or_raise(self, run_id: int) -> RuntimeRun:
        run = self.run_repository.get(run_id)
        if run is None:
            raise not_found_error("Runtime run")
        return run

    def _get_artifact_or_raise(self, run_id: int) -> RuntimeRunArtifact:
        artifact = self.artifact_repository.get_for_run(run_id)
        if artifact is None:
            raise not_found_error("Runtime run artifact")
        return artifact
