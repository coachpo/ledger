from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import utcnow
from app.db.engine import get_session_factory
from app.models.agent_spec import AgentSpec
from app.models.persona_profile import PersonaProfile
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_checkpoint import RuntimeCheckpoint
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.models.workflow_spec import WorkflowSpec
from app.repositories.agent_spec import AgentSpecRepository
from app.repositories.capability_registry_entry import CapabilityRegistryEntryRepository
from app.repositories.persona_profile import PersonaProfileRepository
from app.repositories.runtime_approval import RuntimeApprovalRepository
from app.repositories.runtime_checkpoint import RuntimeCheckpointRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_run_artifact import RuntimeRunArtifactRepository
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.repositories.workflow_spec import WorkflowSpecRepository
from app.schemas.runtime import (
    ApprovalMode,
    ApprovalSummary,
    CapabilityRef,
    CapabilityType,
    PersonaProfileKind,
    PersonaProfileRef,
    ResolvedBundleVersionRead,
    ResolvedCapabilityRead,
    ResolvedConnectorVersionRead,
    ResolvedToolVersionRead,
    RuntimeApprovalActionRead,
    RuntimeArtifactRead,
    RuntimeCallerType,
    RuntimeCancelRead,
    RuntimeCheckpointRead,
    RuntimeExecutionKind,
    RuntimeRunCreate,
    RuntimeRunCreated,
    RuntimeRunListRead,
    RuntimeRunRead,
    SpecOrigin,
    TraceSummary,
    WorkflowAgentRef,
)
from app.services.execution_adapters import (
    ExecutionAdapter,
    ExecutionAdapterDispatchMode,
    ExecutionAdapterRequest,
    ExecutionAdapterResult,
    ExecutionAdapterTraceEvent,
    ExecutionApprovalRequest,
    ExecutionApprovalState,
    ExecutionArtifactPatch,
    ExecutionCheckpointRecord,
    FrozenExecutionSnapshot,
    GenericWorkflowExecutionAdapter,
    SingleAgentExecutionAdapter,
)
from app.services.studio_query_service import StudioQueryService

_QUEUEABLE_RUN_STATUSES = {"QUEUED"}
_RESUMABLE_RUN_STATUSES = {"WAITING_APPROVAL"}
_RETRYABLE_RUN_STATUSES = {"FAILED", "WAITING_APPROVAL", "CANCELLED"}
_APPROVAL_REQUIRED = "required"
_APPROVAL_NOT_REQUIRED = "not_required"
_RUN_CREATED_EVENT_TYPE = "RUN_CREATED"
_RUN_COMPLETED_EVENT_TYPE = "RUN_COMPLETED"
_RUN_FAILED_EVENT_TYPE = "RUN_FAILED"
_RUN_CANCELLED_EVENT_TYPE = "RUN_CANCELLED"
_APPROVAL_REQUESTED_EVENT_TYPE = "APPROVAL_REQUESTED"
_APPROVAL_RESOLVED_EVENT_TYPE = "APPROVAL_RESOLVED"
_TOOL_EVENT_TYPE = "TOOL_CALLED"
_WARNING_EVENT_TYPE = "WARNING_EMITTED"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_CANCELLABLE_RUN_STATUSES = {"QUEUED", "RUNNING", "WAITING_APPROVAL"}
_CANCELLED_PENDING_APPROVAL_REASON = "Run cancelled before approval resolution"
_PUBLIC_RUN_START_TIMEOUT_SECONDS = 0.25
_PUBLIC_RUN_START_POLL_INTERVAL_SECONDS = 0.01
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedRuntimeExecution:
    dispatch_mode: ExecutionAdapterDispatchMode
    run_id: int
    snapshot: FrozenExecutionSnapshot


@dataclass(frozen=True)
class RuntimeRunShellOptions:
    retention_class: str | None = None
    expires_at: datetime | None = None


class InvalidExecutionAdapterResult(RuntimeError):
    pass


class AgentRuntimeService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.agent_repository = AgentSpecRepository(session)
        self.workflow_repository = WorkflowSpecRepository(session)
        self.persona_repository = PersonaProfileRepository(session)
        self.capability_repository = CapabilityRegistryEntryRepository(session)
        self.run_repository = RuntimeRunRepository(session)
        self.artifact_repository = RuntimeRunArtifactRepository(session)
        self.approval_repository = RuntimeApprovalRepository(session)
        self.checkpoint_repository = RuntimeCheckpointRepository(session)
        self.trace_event_repository = RuntimeTraceEventRepository(session)
        self.query_service = StudioQueryService(session)

    def prepare_run(
        self,
        payload: RuntimeRunCreate,
        *,
        shell_options: RuntimeRunShellOptions | None = None,
    ) -> PreparedRuntimeExecution:
        snapshot = self._resolve_snapshot_from_create(payload)
        input_hash = self._hash_frozen_input(snapshot)
        retention_class = (
            shell_options.retention_class
            if shell_options is not None and shell_options.retention_class is not None
            else "persistent"
            if payload.persist_run
            else "ephemeral"
        )
        return self._create_run_shell(
            dispatch_mode="start",
            caller_type=payload.caller_type.value,
            caller_id=payload.caller_id,
            caller_scope_key=payload.caller_scope_key,
            caller_identity_key=payload.caller_identity_key,
            snapshot=snapshot,
            input_hash=input_hash,
            retention_class=retention_class,
            expires_at=shell_options.expires_at if shell_options is not None else None,
        )

    def run(self, payload: RuntimeRunCreate, adapter: ExecutionAdapter) -> RuntimeRunRead:
        prepared = self.prepare_run(payload)
        return self.execute_prepared_run(prepared, adapter)

    def execute_run(
        self,
        payload: RuntimeRunCreate,
        *,
        shell_options: RuntimeRunShellOptions | None = None,
    ) -> RuntimeRunRead:
        prepared = self.prepare_run(payload, shell_options=shell_options)
        adapter = self._build_execution_adapter_for_create(payload)
        return self.execute_prepared_run(prepared, adapter)

    def create_public_run(self, payload: RuntimeRunCreate) -> RuntimeRunCreated:
        self._validate_public_create_payload(payload)
        prepared = self.prepare_run(payload)
        created = self._build_run_created(prepared.run_id)
        try:
            self._dispatch_prepared_run_in_background(prepared)
        except Exception as exc:
            self._mark_run_failed(
                prepared.run_id,
                code="runtime_dispatch_failed",
                message=f"Failed to dispatch runtime run {prepared.run_id}: {exc}",
            )
            raise
        return self._await_public_run_start(prepared.run_id, fallback=created)

    def _build_run_created(self, run_id: int) -> RuntimeRunCreated:
        run = self._get_run_or_raise(run_id)
        return RuntimeRunCreated.model_validate(
            {"run_id": run.id, "status": run.status, "expires_at": run.expires_at}
        )

    def _dispatch_prepared_run_in_background(self, prepared: PreparedRuntimeExecution) -> None:
        def _run() -> None:
            with self.session_factory() as session:
                service = AgentRuntimeService(session, self.session_factory)
                adapter = service._build_runtime_execution_adapter(
                    prepared.snapshot.execution_kind
                )
                try:
                    service.execute_prepared_run(prepared, adapter)
                except Exception:
                    logger.exception(
                        "Background runtime execution failed for run %d",
                        prepared.run_id,
                    )

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"ledger-runtime-run-{prepared.run_id}",
        )
        thread.start()

    def _await_public_run_start(
        self,
        run_id: int,
        *,
        fallback: RuntimeRunCreated,
    ) -> RuntimeRunCreated:
        observed = fallback
        deadline = time.monotonic() + _PUBLIC_RUN_START_TIMEOUT_SECONDS
        while observed.status == "QUEUED" and time.monotonic() < deadline:
            time.sleep(_PUBLIC_RUN_START_POLL_INTERVAL_SECONDS)
            observed = self._load_run_created_from_fresh_session(run_id)
        return observed

    def _load_run_created_from_fresh_session(self, run_id: int) -> RuntimeRunCreated:
        with self.session_factory() as session:
            return AgentRuntimeService(session, self.session_factory)._build_run_created(run_id)

    def execute_prepared_run(
        self,
        prepared: PreparedRuntimeExecution,
        adapter: ExecutionAdapter,
    ) -> RuntimeRunRead:
        self._transition_run_status(
            prepared.run_id,
            allowed_statuses=_QUEUEABLE_RUN_STATUSES,
            next_status="RUNNING",
        )
        request = self._build_execution_request(
            run_id=prepared.run_id,
            snapshot=prepared.snapshot,
            dispatch_mode=prepared.dispatch_mode,
        )
        return self._execute_request(run_id=prepared.run_id, request=request, adapter=adapter)

    def resume_run(self, run_id: int, adapter: ExecutionAdapter) -> RuntimeRunRead:
        run = self._get_run_or_raise(run_id)
        if run.status not in _RESUMABLE_RUN_STATUSES:
            raise business_rule_error(
                "runtime_resume_not_allowed",
                f"Run {run_id} cannot be resumed from status {run.status}",
            )
        pending = self.approval_repository.list_pending_for_run(run_id)
        if pending:
            raise business_rule_error(
                "runtime_pending_approvals",
                f"Run {run_id} still has pending approvals",
            )
        snapshot = self._load_frozen_snapshot(run_id)
        self._transition_run_status(
            run_id,
            allowed_statuses=_RESUMABLE_RUN_STATUSES,
            next_status="RUNNING",
        )
        request = self._build_execution_request(
            run_id=run_id,
            snapshot=snapshot,
            dispatch_mode="resume",
        )
        return self._execute_request(run_id=run_id, request=request, adapter=adapter)

    def prepare_retry_run(self, run_id: int) -> PreparedRuntimeExecution:
        source_run = self._get_run_or_raise(run_id)
        if source_run.status not in _RETRYABLE_RUN_STATUSES:
            raise business_rule_error(
                "runtime_retry_not_allowed",
                f"Run {run_id} cannot be retried from status {source_run.status}",
            )
        snapshot = self._load_frozen_snapshot(run_id)
        return self._create_run_shell(
            dispatch_mode="retry",
            caller_type=source_run.caller_type,
            caller_id=source_run.caller_id,
            caller_scope_key=source_run.caller_scope_key,
            caller_identity_key=source_run.caller_identity_key,
            snapshot=snapshot,
            input_hash=source_run.input_hash,
            retention_class=source_run.retention_class,
            expires_at=source_run.expires_at,
        )

    def retry_run(self, run_id: int, adapter: ExecutionAdapter) -> RuntimeRunRead:
        prepared = self.prepare_retry_run(run_id)
        return self.execute_prepared_run(prepared, adapter)

    def load_frozen_snapshot(self, run_id: int) -> FrozenExecutionSnapshot:
        return self._load_frozen_snapshot(run_id)

    def approve_approval(
        self,
        approval_id: int,
        *,
        actor: str,
        reason: str,
        resume_callback: Callable[[int], RuntimeRunRead] | None = None,
    ) -> RuntimeApprovalActionRead:
        return self._resolve_approval_action(
            approval_id=approval_id,
            next_status="APPROVED",
            actor=actor,
            reason=reason,
            resume_callback=resume_callback,
        )

    def deny_approval(
        self,
        approval_id: int,
        *,
        actor: str,
        reason: str,
    ) -> RuntimeApprovalActionRead:
        return self._resolve_approval_action(
            approval_id=approval_id,
            next_status="DENIED",
            actor=actor,
            reason=reason,
        )

    def list_runs(
        self,
        *,
        caller_type: RuntimeCallerType | None = None,
        caller_id: int | None = None,
        caller_scope_key: str | None = None,
        caller_identity_key: str | None = None,
        workflow_spec_key: str | None = None,
    ) -> RuntimeRunListRead:
        return self.query_service.list_runs(
            caller_type=caller_type,
            caller_id=caller_id,
            caller_scope_key=caller_scope_key,
            caller_identity_key=caller_identity_key,
            workflow_spec_key=workflow_spec_key,
        )

    def get_run(self, run_id: int) -> RuntimeRunRead:
        return self.query_service.get_run(run_id)

    def get_artifact(self, run_id: int) -> RuntimeArtifactRead:
        return self.query_service.get_artifact(run_id)

    def cancel_run(self, run_id: int, *, commit: bool = True) -> RuntimeCancelRead:
        run = self._get_run_or_raise(run_id)
        if run.status not in _CANCELLABLE_RUN_STATUSES:
            raise business_rule_error(
                "runtime_cancel_not_allowed",
                f"Run {run_id} cannot be cancelled from status {run.status}",
            )

        artifact = self._get_artifact_or_raise(run_id)
        resolved_at = utcnow()
        trace_events: list[ExecutionAdapterTraceEvent] = []
        for approval in self.approval_repository.list_pending_for_run(run_id):
            approval.status = "EXPIRED"
            approval.actor = None
            approval.reason = _CANCELLED_PENDING_APPROVAL_REASON
            approval.resolved_at = resolved_at
            trace_events.append(
                ExecutionAdapterTraceEvent(
                    event_type=_APPROVAL_RESOLVED_EVENT_TYPE,
                    step_key=approval.step_key,
                    capability_key=approval.capability_key,
                    approval_id=approval.id,
                    payload={
                        "approvalId": approval.id,
                        "status": approval.status,
                        "actor": None,
                        "reason": approval.reason,
                    },
                )
            )

        run.status = "CANCELLED"
        run.output_hash = None
        self._clear_terminal_error(artifact)
        trace_events.append(
            ExecutionAdapterTraceEvent(
                event_type=_RUN_CANCELLED_EVENT_TYPE,
                payload={"reason": "Run cancelled by caller"},
            )
        )
        self._append_trace_events(run.id, trace_events)
        self._refresh_run_summaries(run)

        if commit:
            try:
                self.session.commit()
                self.session.refresh(run)
            except Exception:
                self.session.rollback()
                raise

        return RuntimeCancelRead.model_validate(
            {
                "run_id": run.id,
                "status": run.status,
                "approval_summary": run.approval_summary,
            }
        )

    def persist_run_in_place(self, run_id: int) -> RuntimeRunRead:
        run = self._get_run_or_raise(run_id)
        if run.retention_class == "persistent" and run.expires_at is None:
            return self.get_run(run_id)

        run.retention_class = "persistent"
        run.expires_at = None
        try:
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise
        return self.get_run(run_id)

    def _execute_request(
        self,
        *,
        run_id: int,
        request: ExecutionAdapterRequest,
        adapter: ExecutionAdapter,
    ) -> RuntimeRunRead:
        try:
            result = adapter.execute(request)
            self._apply_adapter_result(run_id=run_id, result=result)
        except InvalidExecutionAdapterResult as exc:
            self.session.rollback()
            self._mark_run_failed(
                run_id,
                code="invalid_adapter_result",
                message=str(exc),
            )
            raise
        except Exception as exc:
            self.session.rollback()
            self._mark_run_failed(
                run_id,
                code="adapter_execution_failed",
                message=str(exc),
            )
            raise
        return self.get_run(run_id)

    def _create_run_shell(
        self,
        *,
        dispatch_mode: ExecutionAdapterDispatchMode,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None,
        caller_identity_key: str | None,
        snapshot: FrozenExecutionSnapshot,
        input_hash: str,
        retention_class: str,
        expires_at: Any,
    ) -> PreparedRuntimeExecution:
        attempt_number = self._next_attempt_number(
            caller_type=caller_type,
            caller_id=caller_id,
            caller_scope_key=caller_scope_key,
        )
        run = RuntimeRun(
            caller_type=caller_type,
            caller_id=caller_id,
            execution_kind=snapshot.execution_kind,
            workflow_spec_key=snapshot.workflow_spec_key,
            workflow_spec_version=snapshot.workflow_spec_version,
            agent_spec_key=snapshot.agent_spec_key,
            agent_spec_version=snapshot.agent_spec_version,
            caller_scope_key=caller_scope_key,
            caller_identity_key=caller_identity_key,
            attempt_number=attempt_number,
            status="QUEUED",
            input_hash=input_hash,
            output_hash=None,
            retention_class=retention_class,
            expires_at=expires_at,
        )

        try:
            self.run_repository.add(run)
            self.session.flush()
            self.artifact_repository.add(
                self._build_artifact_shell(run_id=run.id, snapshot=snapshot)
            )
            self.session.flush()
            self._append_trace_events(
                run.id,
                [
                    ExecutionAdapterTraceEvent(
                        event_type=_RUN_CREATED_EVENT_TYPE,
                        payload=self._build_run_created_payload(
                            dispatch_mode=dispatch_mode,
                            snapshot=snapshot,
                            input_hash=input_hash,
                        ),
                    )
                ],
            )
            self._refresh_run_summaries(run)
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        return PreparedRuntimeExecution(
            dispatch_mode=dispatch_mode,
            run_id=run.id,
            snapshot=snapshot,
        )

    def _build_artifact_shell(
        self,
        *,
        run_id: int,
        snapshot: FrozenExecutionSnapshot,
    ) -> RuntimeRunArtifact:
        authored_entry_prompt_body = self._artifact_input_text(
            snapshot,
            "authored_entry_prompt_body",
        )
        compiled_entry_prompt_body = self._artifact_input_text(
            snapshot,
            "compiled_entry_prompt_body",
        )
        execution_context_body = self._artifact_input_text(
            snapshot,
            "execution_context_body",
        )
        full_user_prompt = self._artifact_input_text(snapshot, "full_user_prompt")
        prompt_report_slug = self._artifact_input_text(snapshot, "prompt_report_slug")
        resolved_mentions = self._artifact_input_json_list(snapshot, "resolved_mentions_json")
        mentioned_target_outputs = self._artifact_input_json_list(
            snapshot,
            "mentioned_target_outputs_json",
        )
        return RuntimeRunArtifact(
            run_id=run_id,
            entry_prompt_hash=self._hash_artifact_text(authored_entry_prompt_body),
            full_user_prompt_hash=self._hash_artifact_text(full_user_prompt),
            authored_entry_prompt_body=authored_entry_prompt_body,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
            prompt_report_slug=prompt_report_slug,
            raw_mention_handles=(
                self._artifact_input_json_text_list(snapshot, "raw_mention_handles_json")
                or self._extract_raw_mention_handles(resolved_mentions)
            ),
            resolved_persona_profile_refs=self._dump_models(
                snapshot.resolved_persona_profile_refs,
            ),
            resolved_builtin_versions=self._artifact_input_json_list(
                snapshot,
                "resolved_builtin_versions_json",
            ),
            resolved_role_versions=self._artifact_input_json_list(
                snapshot,
                "resolved_role_versions_json",
            ),
            resolved_character_versions=self._artifact_input_json_list(
                snapshot,
                "resolved_character_versions_json",
            ),
            resolved_bundle_versions=self._dump_models(snapshot.resolved_bundle_versions),
            resolved_tool_versions=self._dump_models(snapshot.resolved_tool_versions),
            resolved_connector_versions=self._dump_models(snapshot.resolved_connector_versions),
            mentioned_target_outputs=mentioned_target_outputs,
            resolved_mentions=resolved_mentions,
            resolved_workflow_agent_refs=(
                self._dump_models(snapshot.resolved_workflow_agent_refs)
                if snapshot.resolved_workflow_agent_refs
                else None
            ),
            resolved_capabilities=self._dump_models(snapshot.resolved_capabilities),
            final_output=None,
            terminal_error_code=None,
            terminal_error_message=None,
        )

    @staticmethod
    def _artifact_input_text(
        snapshot: FrozenExecutionSnapshot,
        field_name: str,
    ) -> str | None:
        raw_value = snapshot.inputs.get(field_name)
        if raw_value is None:
            return None
        value = str(raw_value)
        return value if value else None

    @staticmethod
    def _artifact_input_json_list(
        snapshot: FrozenExecutionSnapshot,
        field_name: str,
    ) -> list[dict[str, Any]]:
        raw_value = snapshot.inputs.get(field_name)
        if raw_value is None:
            return []
        try:
            payload = json.loads(str(raw_value))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _artifact_input_json_text_list(
        snapshot: FrozenExecutionSnapshot,
        field_name: str,
    ) -> list[str]:
        raw_value = snapshot.inputs.get(field_name)
        if raw_value is None:
            return []
        try:
            payload = json.loads(str(raw_value))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        values: list[str] = []
        for item in payload:
            text = str(item).strip()
            if text:
                values.append(text)
        return values

    @staticmethod
    def _extract_raw_mention_handles(resolved_mentions: Sequence[dict[str, Any]]) -> list[str]:
        handles: list[str] = []
        for mention in resolved_mentions:
            raw_handle = mention.get("sourceHandle")
            if raw_handle is None:
                raw_handle = mention.get("source_handle")
            handle = str(raw_handle or "").strip()
            if handle:
                handles.append(handle)
        return handles

    @staticmethod
    def _hash_artifact_text(value: str | None) -> str:
        if value is None:
            return _EMPTY_SHA256
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _build_run_created_payload(
        self,
        *,
        dispatch_mode: ExecutionAdapterDispatchMode,
        snapshot: FrozenExecutionSnapshot,
        input_hash: str,
    ) -> dict[str, Any]:
        return {
            "dispatchMode": dispatch_mode,
            "executionKind": snapshot.execution_kind,
            "workflowSpecKey": snapshot.workflow_spec_key,
            "workflowSpecVersion": snapshot.workflow_spec_version,
            "agentSpecKey": snapshot.agent_spec_key,
            "agentSpecVersion": snapshot.agent_spec_version,
            "inputs": dict(snapshot.inputs),
            "inputHash": input_hash,
        }

    def _transition_run_status(
        self,
        run_id: int,
        *,
        allowed_statuses: set[str],
        next_status: str,
    ) -> None:
        run = self._get_run_or_raise(run_id)
        if run.status not in allowed_statuses:
            raise business_rule_error(
                "runtime_invalid_status_transition",
                f"Run {run_id} cannot transition from {run.status} to {next_status}",
            )
        run.status = next_status
        self.session.commit()
        self.session.refresh(run)

    def _build_execution_request(
        self,
        *,
        run_id: int,
        snapshot: FrozenExecutionSnapshot,
        dispatch_mode: ExecutionAdapterDispatchMode,
    ) -> ExecutionAdapterRequest:
        run = self._get_run_or_raise(run_id)
        checkpoints = tuple(
            RuntimeCheckpointRead.model_validate(checkpoint)
            for checkpoint in self.checkpoint_repository.list_for_run(run_id)
        )
        approvals = tuple(
            ExecutionApprovalState(
                approval_id=approval.id,
                step_key=approval.step_key,
                capability_key=approval.capability_key,
                status=cast(Any, approval.status),
                actor=approval.actor,
                reason=approval.reason,
                resolved_at=approval.resolved_at,
            )
            for approval in self.approval_repository.list_for_run(run_id)
        )
        return ExecutionAdapterRequest(
            dispatch_mode=dispatch_mode,
            run_id=run.id,
            attempt_number=run.attempt_number,
            caller_type=run.caller_type,
            caller_id=run.caller_id,
            caller_scope_key=run.caller_scope_key,
            caller_identity_key=run.caller_identity_key,
            snapshot=snapshot,
            trace_summary=TraceSummary.model_validate(run.trace_summary),
            approval_summary=ApprovalSummary.model_validate(run.approval_summary),
            checkpoints=checkpoints,
            current_checkpoint=checkpoints[-1] if checkpoints else None,
            approvals=approvals,
        )

    def _apply_adapter_result(self, *, run_id: int, result: ExecutionAdapterResult) -> None:
        self._validate_adapter_result(result)
        run = self._get_run_or_raise(run_id)
        artifact = self._get_artifact_or_raise(run_id)

        self._append_trace_events(run_id, result.trace_events)
        self._upsert_checkpoints(run_id, result.checkpoints)

        if result.status == "WAITING_APPROVAL":
            approvals = self._create_approval_requests(run_id, result.approval_requests)
            self._append_trace_events(
                run_id,
                [
                    ExecutionAdapterTraceEvent(
                        event_type=_APPROVAL_REQUESTED_EVENT_TYPE,
                        step_key=approval.step_key,
                        capability_key=approval.capability_key,
                        approval_id=approval.id,
                        payload={"approvalId": approval.id, "status": approval.status},
                    )
                    for approval in approvals
                ],
            )
            run.status = "WAITING_APPROVAL"
            run.output_hash = None
            self._clear_terminal_error(artifact)
            self._apply_artifact_patch(artifact, result.artifact_patch)
        else:
            self._apply_artifact_patch(artifact, result.artifact_patch)
            run.status = "SUCCEEDED"
            run.output_hash = self._hash_output_payload(artifact.final_output)
            self._clear_terminal_error(artifact)
            self._append_trace_events(
                run_id,
                [
                    ExecutionAdapterTraceEvent(
                        event_type=_RUN_COMPLETED_EVENT_TYPE,
                        payload={"status": "SUCCEEDED"},
                    )
                ],
            )

        self._refresh_run_summaries(run)
        self.session.commit()
        self.session.refresh(run)

    def _validate_adapter_result(self, result: ExecutionAdapterResult) -> None:
        if result.status == "WAITING_APPROVAL":
            if not result.approval_requests:
                raise InvalidExecutionAdapterResult(
                    "WAITING_APPROVAL results must include at least one approval request"
                )
            if not result.checkpoints:
                raise InvalidExecutionAdapterResult(
                    "WAITING_APPROVAL results must include at least one checkpoint"
                )
            if result.artifact_patch is not None and result.artifact_patch.final_output is not None:
                raise InvalidExecutionAdapterResult(
                    "WAITING_APPROVAL results cannot persist a final output"
                )
            return
        if result.approval_requests:
            raise InvalidExecutionAdapterResult(
                "SUCCEEDED results cannot include new approval requests"
            )

    def _upsert_checkpoints(
        self,
        run_id: int,
        checkpoints: Sequence[ExecutionCheckpointRecord],
    ) -> None:
        for checkpoint in checkpoints:
            existing = self.checkpoint_repository.get_for_run_index(
                run_id,
                checkpoint.checkpoint_index,
            )
            if existing is None:
                self.checkpoint_repository.add(
                    RuntimeCheckpoint(
                        run_id=run_id,
                        checkpoint_index=checkpoint.checkpoint_index,
                        step_key=checkpoint.step_key,
                        serialized_state=dict(checkpoint.serialized_state),
                    )
                )
                continue
            existing.step_key = checkpoint.step_key
            existing.serialized_state = dict(checkpoint.serialized_state)
        self.session.flush()

    def _create_approval_requests(
        self,
        run_id: int,
        approvals: Sequence[ExecutionApprovalRequest],
    ) -> list[RuntimeApproval]:
        created: list[RuntimeApproval] = []
        for approval_request in approvals:
            approval = RuntimeApproval(
                run_id=run_id,
                step_key=approval_request.step_key,
                capability_key=approval_request.capability_key,
                status="PENDING",
            )
            self.approval_repository.add(approval)
            created.append(approval)
        self.session.flush()
        return created

    def _apply_artifact_patch(
        self,
        artifact: RuntimeRunArtifact,
        patch: ExecutionArtifactPatch | None,
    ) -> None:
        if patch is None:
            return
        artifact.final_output = patch.final_output
        artifact.report_markdown = patch.report_markdown
        artifact.normalized_trade_decisions = (
            list(patch.normalized_trade_decisions)
            if patch.normalized_trade_decisions is not None
            else None
        )

    def _mark_run_failed(self, run_id: int, *, code: str, message: str) -> None:
        run = self._get_run_or_raise(run_id)
        artifact = self._get_artifact_or_raise(run_id)
        run.status = "FAILED"
        run.output_hash = None
        artifact.final_output = None
        artifact.terminal_error_code = code
        artifact.terminal_error_message = message
        self._append_trace_events(
            run_id,
            [
                ExecutionAdapterTraceEvent(
                    event_type=_RUN_FAILED_EVENT_TYPE,
                    payload={"code": code, "message": message},
                )
            ],
        )
        self._refresh_run_summaries(run)
        self.session.commit()
        self.session.refresh(run)

    def _clear_terminal_error(self, artifact: RuntimeRunArtifact) -> None:
        artifact.terminal_error_code = None
        artifact.terminal_error_message = None

    def _resolve_approval_action(
        self,
        *,
        approval_id: int,
        next_status: str,
        actor: str,
        reason: str,
        resume_callback: Callable[[int], RuntimeRunRead] | None = None,
    ) -> RuntimeApprovalActionRead:
        approval = self.approval_repository.get(approval_id)
        if approval is None:
            raise not_found_error("Runtime approval")
        if approval.status != "PENDING":
            raise business_rule_error(
                "runtime_approval_not_pending",
                f"Approval {approval_id} is already {approval.status}",
            )
        run = self._get_run_or_raise(approval.run_id)
        if run.status != "WAITING_APPROVAL":
            raise business_rule_error(
                "runtime_approval_run_not_waiting",
                f"Run {run.id} is not waiting for approval",
            )

        approval.status = next_status
        approval.actor = actor
        approval.reason = reason
        approval.resolved_at = utcnow()
        self.session.flush()
        self._append_trace_events(
            approval.run_id,
            [
                ExecutionAdapterTraceEvent(
                    event_type=_APPROVAL_RESOLVED_EVENT_TYPE,
                    step_key=approval.step_key,
                    capability_key=approval.capability_key,
                    approval_id=approval.id,
                    payload={
                        "approvalId": approval.id,
                        "status": approval.status,
                        "actor": actor,
                        "reason": reason,
                    },
                )
            ],
        )

        if next_status == "DENIED":
            run.status = "FAILED"
            run.output_hash = None
            artifact = self._get_artifact_or_raise(run.id)
            artifact.final_output = None
            artifact.terminal_error_code = "approval_denied"
            artifact.terminal_error_message = (
                f"Approval denied for capability {approval.capability_key}"
            )
            self._append_trace_events(
                run.id,
                [
                    ExecutionAdapterTraceEvent(
                        event_type=_RUN_FAILED_EVENT_TYPE,
                        payload={
                            "code": "approval_denied",
                            "message": artifact.terminal_error_message,
                        },
                    )
                ],
            )
            self._refresh_run_summaries(run)
            self.session.commit()
            self.session.refresh(run)
            self.session.refresh(approval)
            return RuntimeApprovalActionRead.model_validate(
                {
                    "approval_id": approval.id,
                    "status": approval.status,
                    "run_id": run.id,
                    "resolved_at": approval.resolved_at,
                    "run_status": run.status,
                }
            )

        self._refresh_run_summaries(run)
        self.session.commit()
        self.session.refresh(run)
        self.session.refresh(approval)

        pending_after_resolution = self.approval_repository.list_pending_for_run(run.id)
        resumed_run = self.get_run(run.id)
        if not pending_after_resolution:
            if resume_callback is not None:
                resumed_run = resume_callback(run.id)
            else:
                resumed_run = self.resume_run(
                    run.id,
                    self._build_runtime_execution_adapter(run.execution_kind),
                )
        return RuntimeApprovalActionRead.model_validate(
            {
                "approval_id": approval.id,
                "status": approval.status,
                "run_id": run.id,
                "resolved_at": approval.resolved_at,
                "run_status": resumed_run.status,
            }
        )

    def _refresh_run_summaries(self, run: RuntimeRun) -> None:
        trace_events = self.trace_event_repository.list_for_run(run.id)
        approvals = self.approval_repository.list_for_run(run.id)
        run.trace_summary = TraceSummary(
            event_count=len(trace_events),
            tool_call_count=sum(
                1 for event in trace_events if event.event_type == _TOOL_EVENT_TYPE
            ),
            warning_count=sum(
                1 for event in trace_events if event.event_type == _WARNING_EVENT_TYPE
            ),
            last_event_at=trace_events[-1].created_at if trace_events else None,
        ).model_dump(by_alias=True, mode="json")
        run.approval_summary = ApprovalSummary(
            total_count=len(approvals),
            pending_count=sum(1 for approval in approvals if approval.status == "PENDING"),
            approved_count=sum(1 for approval in approvals if approval.status == "APPROVED"),
            denied_count=sum(1 for approval in approvals if approval.status == "DENIED"),
            expired_count=sum(1 for approval in approvals if approval.status == "EXPIRED"),
        ).model_dump(by_alias=True, mode="json")
        self.session.flush()

    def _append_trace_events(
        self,
        run_id: int,
        events: Sequence[ExecutionAdapterTraceEvent],
    ) -> None:
        if not events:
            return
        latest = self.trace_event_repository.get_latest_for_run(run_id)
        next_index = 0 if latest is None else latest.event_index + 1
        for offset, event in enumerate(events):
            self.trace_event_repository.add(
                RuntimeTraceEvent(
                    run_id=run_id,
                    event_index=next_index + offset,
                    event_type=event.event_type,
                    step_key=event.step_key,
                    capability_key=event.capability_key,
                    approval_id=event.approval_id,
                    payload=dict(event.payload),
                )
            )
        self.session.flush()

    def _build_execution_adapter_for_create(
        self,
        payload: RuntimeRunCreate,
    ) -> ExecutionAdapter:
        return self._build_runtime_execution_adapter(payload.execution_kind)

    def _build_runtime_execution_adapter(
        self,
        execution_kind: str,
    ) -> ExecutionAdapter:
        if execution_kind == RuntimeExecutionKind.WORKFLOW:
            return GenericWorkflowExecutionAdapter(self.session)
        return SingleAgentExecutionAdapter(self.session)

    def _resolve_snapshot_from_create(self, payload: RuntimeRunCreate) -> FrozenExecutionSnapshot:
        if payload.execution_kind == RuntimeExecutionKind.WORKFLOW:
            return self._resolve_workflow_snapshot(payload)
        return self._resolve_single_agent_snapshot(payload)

    @staticmethod
    def _validate_public_create_payload(payload: RuntimeRunCreate) -> None:
        if payload.caller_type != RuntimeCallerType.API:
            raise business_rule_error(
                "runtime_public_caller_type_not_allowed",
                (
                    "Public runtime create only supports callerType=api; "
                    "use the dedicated Studio or Tryout surfaces for non-api runs."
                ),
            )

    def _resolve_workflow_snapshot(self, payload: RuntimeRunCreate) -> FrozenExecutionSnapshot:
        if payload.workflow_spec_key is None:
            raise business_rule_error(
                "runtime_workflow_required",
                "Workflow execution requires workflow_spec_key",
            )
        workflow = self.workflow_repository.resolve_version(
            payload.workflow_spec_key,
            payload.workflow_spec_version,
        )
        if workflow is None:
            raise business_rule_error(
                "runtime_workflow_not_found",
                f"Workflow spec {payload.workflow_spec_key!r} was not found",
            )
        if payload.caller_type == RuntimeCallerType.API and workflow.status != "ACTIVE":
            raise business_rule_error(
                "runtime_public_workflow_not_active",
                "Public runtime create only supports active workflow specs.",
            )

        workflow_default_refs = self._workflow_default_capability_refs(workflow)
        approval_overrides = cast(Sequence[dict[str, Any]], workflow.approval_policy_overrides)
        resolved_workflow_agent_refs: list[WorkflowAgentRef] = []
        resolved_persona_refs_by_identity: dict[tuple[str, int | None], PersonaProfileRef] = {}
        resolved_capabilities_by_identity: dict[tuple[str, int], ResolvedCapabilityRead] = {}
        resolved_bundle_versions: dict[str, ResolvedBundleVersionRead] = {}
        resolved_tool_versions: dict[str, ResolvedToolVersionRead] = {}
        resolved_connector_versions: dict[str, ResolvedConnectorVersionRead] = {}

        for step in self._extract_workflow_steps(workflow.graph_definition):
            step_key = self._extract_required_string(step, "step_key", "stepKey")
            agent_key = self._extract_required_string(step, "agent_spec_key", "agentSpecKey")
            agent_version = self._extract_optional_int(
                step, "agent_spec_version", "agentSpecVersion"
            )
            agent = self.agent_repository.resolve_version(agent_key, agent_version)
            if agent is None:
                raise business_rule_error(
                    "runtime_step_agent_not_found",
                    f"Workflow step {step_key!r} references unknown agent {agent_key!r}",
                )

            raw_step_personas = [
                *self._persona_refs_from_agent(agent),
                *self._with_default_persona_source(payload.persona_profile_refs, "run_request"),
                *self._persona_refs_from_step(step),
            ]
            resolved_step_personas = self._resolve_persona_refs(raw_step_personas)
            self._extend_resolved_persona_map(
                resolved_persona_refs_by_identity,
                resolved_step_personas,
            )

            raw_step_capabilities = [
                *workflow_default_refs,
                *self._capability_refs_from_agent(agent),
                *self._capability_refs_from_personas(resolved_step_personas),
                *self._capability_refs_from_step(step),
            ]
            resolved_step_capabilities = self._resolve_capability_refs(
                raw_step_capabilities,
                step_key=step_key,
                approval_policy_overrides=approval_overrides,
                allowed_bundle_keys=tuple(workflow.allowed_capability_bundle_keys),
                resolved_capabilities_by_identity=resolved_capabilities_by_identity,
                resolved_bundle_versions=resolved_bundle_versions,
                resolved_tool_versions=resolved_tool_versions,
                resolved_connector_versions=resolved_connector_versions,
            )

            resolved_workflow_agent_refs.append(
                WorkflowAgentRef(
                    step_key=step_key,
                    agent_spec_key=agent.key,
                    agent_spec_version=agent.version,
                    persona_profile_refs=resolved_step_personas,
                    capability_refs=resolved_step_capabilities,
                )
            )

        return FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key=workflow.key,
            workflow_spec_version=workflow.version,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs=dict(payload.inputs),
            resolved_workflow_agent_refs=tuple(resolved_workflow_agent_refs),
            resolved_persona_profile_refs=tuple(resolved_persona_refs_by_identity.values()),
            resolved_capabilities=tuple(
                self._sort_resolved_capabilities(resolved_capabilities_by_identity.values())
            ),
            resolved_bundle_versions=tuple(
                sorted(resolved_bundle_versions.values(), key=lambda item: item.bundle_key)
            ),
            resolved_tool_versions=tuple(
                sorted(resolved_tool_versions.values(), key=lambda item: item.tool_id)
            ),
            resolved_connector_versions=tuple(
                sorted(resolved_connector_versions.values(), key=lambda item: item.connector_id)
            ),
        )

    def _resolve_single_agent_snapshot(self, payload: RuntimeRunCreate) -> FrozenExecutionSnapshot:
        if payload.agent_spec_key is None:
            raise business_rule_error(
                "runtime_agent_required",
                "Single-agent execution requires agent_spec_key",
            )
        agent = self.agent_repository.resolve_version(
            payload.agent_spec_key,
            payload.agent_spec_version,
        )
        if agent is None:
            raise business_rule_error(
                "runtime_agent_not_found",
                f"Agent spec {payload.agent_spec_key!r} was not found",
            )

        raw_persona_refs = [
            *self._persona_refs_from_agent(agent),
            *self._with_default_persona_source(payload.persona_profile_refs, "run_request"),
        ]
        resolved_persona_refs = self._resolve_persona_refs(raw_persona_refs)
        resolved_capabilities_by_identity: dict[tuple[str, int], ResolvedCapabilityRead] = {}
        resolved_bundle_versions: dict[str, ResolvedBundleVersionRead] = {}
        resolved_tool_versions: dict[str, ResolvedToolVersionRead] = {}
        resolved_connector_versions: dict[str, ResolvedConnectorVersionRead] = {}
        self._resolve_capability_refs(
            [
                *self._capability_refs_from_agent(agent),
                *self._capability_refs_from_personas(resolved_persona_refs),
            ],
            step_key=None,
            approval_policy_overrides=(),
            allowed_bundle_keys=(),
            resolved_capabilities_by_identity=resolved_capabilities_by_identity,
            resolved_bundle_versions=resolved_bundle_versions,
            resolved_tool_versions=resolved_tool_versions,
            resolved_connector_versions=resolved_connector_versions,
        )

        return FrozenExecutionSnapshot(
            execution_kind="single_agent",
            workflow_spec_key=None,
            workflow_spec_version=None,
            agent_spec_key=agent.key,
            agent_spec_version=agent.version,
            inputs=dict(payload.inputs),
            resolved_workflow_agent_refs=(),
            resolved_persona_profile_refs=tuple(resolved_persona_refs),
            resolved_capabilities=tuple(
                self._sort_resolved_capabilities(resolved_capabilities_by_identity.values())
            ),
            resolved_bundle_versions=tuple(
                sorted(resolved_bundle_versions.values(), key=lambda item: item.bundle_key)
            ),
            resolved_tool_versions=tuple(
                sorted(resolved_tool_versions.values(), key=lambda item: item.tool_id)
            ),
            resolved_connector_versions=tuple(
                sorted(resolved_connector_versions.values(), key=lambda item: item.connector_id)
            ),
        )

    def _load_frozen_snapshot(self, run_id: int) -> FrozenExecutionSnapshot:
        run = self._get_run_or_raise(run_id)
        artifact = self._get_artifact_or_raise(run_id)
        created_event = self.trace_event_repository.get_for_run_index(run_id, 0)
        if created_event is None or created_event.event_type != _RUN_CREATED_EVENT_TYPE:
            raise business_rule_error(
                "runtime_snapshot_missing_run_created",
                f"Run {run_id} is missing its frozen RUN_CREATED trace event",
            )
        raw_inputs = created_event.payload.get("inputs", {})
        if not isinstance(raw_inputs, dict):
            raise business_rule_error(
                "runtime_snapshot_missing_inputs",
                f"Run {run_id} is missing frozen inputs",
            )
        inputs = {str(key): str(value) for key, value in raw_inputs.items()}

        return FrozenExecutionSnapshot(
            execution_kind=cast(Any, run.execution_kind),
            workflow_spec_key=run.workflow_spec_key,
            workflow_spec_version=run.workflow_spec_version,
            agent_spec_key=run.agent_spec_key,
            agent_spec_version=run.agent_spec_version,
            inputs=inputs,
            resolved_workflow_agent_refs=tuple(
                WorkflowAgentRef.model_validate(item)
                for item in (artifact.resolved_workflow_agent_refs or [])
            ),
            resolved_persona_profile_refs=tuple(
                PersonaProfileRef.model_validate(item)
                for item in artifact.resolved_persona_profile_refs
            ),
            resolved_capabilities=tuple(
                ResolvedCapabilityRead.model_validate(item)
                for item in artifact.resolved_capabilities
            ),
            resolved_bundle_versions=tuple(
                ResolvedBundleVersionRead.model_validate(item)
                for item in artifact.resolved_bundle_versions
            ),
            resolved_tool_versions=tuple(
                ResolvedToolVersionRead.model_validate(item)
                for item in artifact.resolved_tool_versions
            ),
            resolved_connector_versions=tuple(
                ResolvedConnectorVersionRead.model_validate(item)
                for item in artifact.resolved_connector_versions
            ),
        )

    def _persona_refs_from_agent(self, agent: AgentSpec) -> list[PersonaProfileRef]:
        return [
            PersonaProfileRef(
                persona_profile_key=key,
                selection_source="agent_default",
            )
            for key in agent.default_persona_profile_keys
        ]

    def _with_default_persona_source(
        self,
        refs: Sequence[PersonaProfileRef],
        default_source: str,
    ) -> list[PersonaProfileRef]:
        return [
            ref.model_copy(update={"selection_source": ref.selection_source or default_source})
            for ref in refs
        ]

    def _persona_refs_from_step(self, step: dict[str, Any]) -> list[PersonaProfileRef]:
        raw_refs = step.get("persona_profile_refs") or step.get("personaProfileRefs") or []
        if not isinstance(raw_refs, list):
            return []
        return [
            PersonaProfileRef.model_validate(raw_ref).model_copy(
                update={
                    "selection_source": (
                        PersonaProfileRef.model_validate(raw_ref).selection_source or "step_config"
                    )
                }
            )
            for raw_ref in raw_refs
        ]

    def _resolve_persona_refs(
        self,
        raw_refs: Sequence[PersonaProfileRef],
    ) -> list[PersonaProfileRef]:
        resolved_refs: list[PersonaProfileRef] = []
        seen: set[tuple[str, int]] = set()
        for raw_ref in raw_refs:
            profile = self.persona_repository.resolve_version(
                raw_ref.persona_profile_key,
                raw_ref.persona_profile_version,
            )
            if profile is None:
                raise business_rule_error(
                    "runtime_persona_not_found",
                    f"Persona profile {raw_ref.persona_profile_key!r} was not found",
                )
            resolved_ref = self._build_resolved_persona_ref(
                profile,
                selection_source=raw_ref.selection_source or "runtime_resolution",
            )
            identity = (
                resolved_ref.persona_profile_key,
                cast(int, resolved_ref.persona_profile_version),
            )
            if identity in seen:
                continue
            seen.add(identity)
            resolved_refs.append(resolved_ref)
        return resolved_refs

    def _build_resolved_persona_ref(
        self,
        profile: PersonaProfile,
        *,
        selection_source: str,
    ) -> PersonaProfileRef:
        parent_ref: PersonaProfileRef | None = None
        if profile.parent_profile_key is not None and profile.parent_profile_version is not None:
            parent = self.persona_repository.get_by_key_version(
                profile.parent_profile_key,
                profile.parent_profile_version,
            )
            if parent is None:
                raise business_rule_error(
                    "runtime_persona_parent_not_found",
                    f"Parent persona profile {profile.parent_profile_key!r} was not found",
                )
            parent_ref = self._build_resolved_persona_ref(
                parent,
                selection_source="parent_inheritance",
            )
        return PersonaProfileRef(
            persona_profile_key=profile.key,
            persona_profile_version=profile.version,
            canonical_target_id=profile.canonical_target_id,
            persona_kind=PersonaProfileKind(profile.kind),
            origin=SpecOrigin(profile.origin),
            selection_source=selection_source,
            parent_persona_profile_ref=parent_ref,
            legacy_source_version=profile.legacy_source_version,
        )

    def _extend_resolved_persona_map(
        self,
        target: dict[tuple[str, int | None], PersonaProfileRef],
        resolved_refs: Iterable[PersonaProfileRef],
    ) -> None:
        for ref in resolved_refs:
            target.setdefault((ref.persona_profile_key, ref.persona_profile_version), ref)

    def _workflow_default_capability_refs(self, workflow: WorkflowSpec) -> list[CapabilityRef]:
        refs: list[CapabilityRef] = []
        refs.extend(
            CapabilityRef(capability_key=tool_id, selection_source="workflow_default_tool")
            for tool_id in workflow.default_tool_ids
        )
        refs.extend(
            CapabilityRef(
                capability_key=connector_id,
                selection_source="workflow_default_connector",
            )
            for connector_id in workflow.connector_ids
        )
        return refs

    def _capability_refs_from_agent(self, agent: AgentSpec) -> list[CapabilityRef]:
        return [
            CapabilityRef(capability_key=bundle_key, selection_source="agent_default")
            for bundle_key in agent.default_capability_bundle_keys
        ]

    def _capability_refs_from_personas(
        self,
        persona_refs: Sequence[PersonaProfileRef],
    ) -> list[CapabilityRef]:
        refs: list[CapabilityRef] = []
        for persona_ref in persona_refs:
            profile = self.persona_repository.get_by_key_version(
                persona_ref.persona_profile_key,
                cast(int, persona_ref.persona_profile_version),
            )
            if profile is None:
                raise business_rule_error(
                    "runtime_persona_not_found",
                    f"Persona profile {persona_ref.persona_profile_key!r} was not found",
                )
            refs.extend(
                CapabilityRef(
                    capability_key=bundle_key,
                    selection_source=f"persona_default:{profile.key}",
                )
                for bundle_key in profile.default_capability_bundle_keys
            )
        return refs

    def _capability_refs_from_step(self, step: dict[str, Any]) -> list[CapabilityRef]:
        raw_refs = step.get("capability_refs") or step.get("capabilityRefs") or []
        if not isinstance(raw_refs, list):
            return []
        capability_refs: list[CapabilityRef] = []
        for raw_ref in raw_refs:
            resolved_ref = CapabilityRef.model_validate(raw_ref)
            capability_refs.append(
                resolved_ref.model_copy(
                    update={
                        "selection_source": resolved_ref.selection_source or "step_config",
                    }
                )
            )
        return capability_refs

    def _resolve_capability_refs(
        self,
        raw_refs: Sequence[CapabilityRef],
        *,
        step_key: str | None,
        approval_policy_overrides: Sequence[dict[str, Any]],
        allowed_bundle_keys: Sequence[str],
        resolved_capabilities_by_identity: dict[tuple[str, int], ResolvedCapabilityRead],
        resolved_bundle_versions: dict[str, ResolvedBundleVersionRead],
        resolved_tool_versions: dict[str, ResolvedToolVersionRead],
        resolved_connector_versions: dict[str, ResolvedConnectorVersionRead],
    ) -> list[CapabilityRef]:
        resolved_refs: list[CapabilityRef] = []
        seen: set[tuple[str, int]] = set()
        for raw_ref in raw_refs:
            self._expand_capability_ref(
                raw_ref,
                step_key=step_key,
                approval_policy_overrides=approval_policy_overrides,
                allowed_bundle_keys=allowed_bundle_keys,
                resolved_refs=resolved_refs,
                seen=seen,
                resolved_capabilities_by_identity=resolved_capabilities_by_identity,
                resolved_bundle_versions=resolved_bundle_versions,
                resolved_tool_versions=resolved_tool_versions,
                resolved_connector_versions=resolved_connector_versions,
            )
        return resolved_refs

    def _expand_capability_ref(
        self,
        raw_ref: CapabilityRef,
        *,
        step_key: str | None,
        approval_policy_overrides: Sequence[dict[str, Any]],
        allowed_bundle_keys: Sequence[str],
        resolved_refs: list[CapabilityRef],
        seen: set[tuple[str, int]],
        resolved_capabilities_by_identity: dict[tuple[str, int], ResolvedCapabilityRead],
        resolved_bundle_versions: dict[str, ResolvedBundleVersionRead],
        resolved_tool_versions: dict[str, ResolvedToolVersionRead],
        resolved_connector_versions: dict[str, ResolvedConnectorVersionRead],
    ) -> None:
        capability = self.capability_repository.resolve_version(
            raw_ref.capability_key,
            raw_ref.capability_version,
        )
        if capability is None:
            raise business_rule_error(
                "runtime_capability_not_found",
                f"Capability {raw_ref.capability_key!r} was not found",
            )
        if capability.type == "bundle":
            if allowed_bundle_keys and capability.key not in set(allowed_bundle_keys):
                raise business_rule_error(
                    "runtime_disallowed_capability_bundle",
                    f"Capability bundle {capability.key!r} is not allowed for this workflow",
                )
            resolved_bundle_versions.setdefault(
                capability.key,
                ResolvedBundleVersionRead(bundle_key=capability.key, revision=capability.version),
            )
            bundle_members = capability.bundle_members or []
            for bundle_member in bundle_members:
                member_key = self._extract_required_string(
                    bundle_member,
                    "key",
                    "capability_key",
                    "capabilityKey",
                )
                member_version = self._extract_optional_int(
                    bundle_member,
                    "version",
                    "capability_version",
                    "capabilityVersion",
                )
                member_type = self._extract_required_string(
                    bundle_member,
                    "type",
                    "member_type",
                    "memberType",
                )
                if member_type == "bundle":
                    raise business_rule_error(
                        "runtime_nested_bundle_not_supported",
                        (
                            f"Capability bundle {capability.key!r} cannot contain "
                            "nested bundle members"
                        ),
                    )
                self._expand_capability_ref(
                    CapabilityRef(
                        capability_key=member_key,
                        capability_version=member_version,
                        selection_source=raw_ref.selection_source or f"bundle:{capability.key}",
                    ),
                    step_key=step_key,
                    approval_policy_overrides=approval_policy_overrides,
                    allowed_bundle_keys=allowed_bundle_keys,
                    resolved_refs=resolved_refs,
                    seen=seen,
                    resolved_capabilities_by_identity=resolved_capabilities_by_identity,
                    resolved_bundle_versions=resolved_bundle_versions,
                    resolved_tool_versions=resolved_tool_versions,
                    resolved_connector_versions=resolved_connector_versions,
                )
            return

        effective_approval_mode = self._resolve_effective_approval_mode(
            base_mode=capability.approval_mode,
            step_key=step_key,
            capability_key=capability.key,
            approval_policy_overrides=approval_policy_overrides,
        )
        effective_config = dict(raw_ref.effective_config or {})
        identity = (capability.key, capability.version)
        if identity not in seen:
            resolved_refs.append(
                CapabilityRef(
                    capability_key=capability.key,
                    capability_version=capability.version,
                    capability_type=CapabilityType(capability.type),
                    selection_source=raw_ref.selection_source,
                    effective_approval_mode=ApprovalMode(effective_approval_mode),
                    effective_config=effective_config,
                )
            )
            seen.add(identity)

        resolved_capabilities_by_identity.setdefault(
            identity,
            ResolvedCapabilityRead(
                capability_key=capability.key,
                capability_version=capability.version,
                capability_type=CapabilityType(capability.type),
                approval_mode=ApprovalMode(effective_approval_mode),
                display_name=capability.display_name,
                transport=capability.transport,
                lifecycle=capability.lifecycle,
                effective_config=effective_config,
            ),
        )
        if capability.type == "tool":
            resolved_tool_versions.setdefault(
                capability.key,
                ResolvedToolVersionRead(tool_id=capability.key, revision=capability.version),
            )
        elif capability.type == "connector":
            resolved_connector_versions.setdefault(
                capability.key,
                ResolvedConnectorVersionRead(
                    connector_id=capability.key,
                    revision=capability.version,
                ),
            )

    def _resolve_effective_approval_mode(
        self,
        *,
        base_mode: str,
        step_key: str | None,
        capability_key: str,
        approval_policy_overrides: Sequence[dict[str, Any]],
    ) -> str:
        if step_key is None:
            return base_mode
        generic_override: str | None = None
        exact_override: str | None = None
        for override in approval_policy_overrides:
            override_step_key = self._extract_optional_string(override, "step_key", "stepKey")
            if override_step_key != step_key:
                continue
            override_capability_key = self._extract_optional_string(
                override,
                "capability_key",
                "capabilityKey",
            )
            override_mode = self._extract_optional_string(
                override,
                "approval_mode",
                "approvalMode",
            )
            if override_mode is None:
                continue
            if override_capability_key is None:
                generic_override = override_mode
                continue
            if override_capability_key == capability_key:
                exact_override = override_mode
        selected_mode = exact_override or generic_override or base_mode
        if selected_mode not in {_APPROVAL_NOT_REQUIRED, _APPROVAL_REQUIRED}:
            raise business_rule_error(
                "runtime_invalid_approval_mode",
                f"Unsupported approval mode {selected_mode!r} for capability {capability_key!r}",
            )
        if base_mode == _APPROVAL_REQUIRED and selected_mode == _APPROVAL_NOT_REQUIRED:
            raise business_rule_error(
                "runtime_invalid_approval_override",
                (
                    f"Approval override for capability {capability_key!r} on step {step_key!r} "
                    "cannot relax required approval"
                ),
            )
        return selected_mode

    def _extract_workflow_steps(self, graph_definition: dict[str, Any]) -> list[dict[str, Any]]:
        raw_steps = graph_definition.get("steps")
        if isinstance(raw_steps, list) and raw_steps:
            return [step for step in raw_steps if isinstance(step, dict)]

        kind = self._extract_optional_string(graph_definition, "kind")
        agent_order = graph_definition.get("agent_order") or graph_definition.get("agentOrder")
        if kind == "seeded_langgraph_topology" and isinstance(agent_order, list) and agent_order:
            steps: list[dict[str, Any]] = []
            for agent_key in agent_order:
                normalized_agent_key = str(agent_key).strip()
                if not normalized_agent_key:
                    continue
                steps.append(
                    {
                        "stepKey": normalized_agent_key,
                        "agentSpecKey": normalized_agent_key,
                    }
                )
            if steps:
                return steps

        raise business_rule_error(
            "runtime_invalid_workflow_graph_definition",
            "Workflow graph definition does not contain executable steps",
        )

    def _hash_frozen_input(self, snapshot: FrozenExecutionSnapshot) -> str:
        payload = {
            "executionKind": snapshot.execution_kind,
            "workflowSpecKey": snapshot.workflow_spec_key,
            "workflowSpecVersion": snapshot.workflow_spec_version,
            "agentSpecKey": snapshot.agent_spec_key,
            "agentSpecVersion": snapshot.agent_spec_version,
            "inputs": dict(snapshot.inputs),
            "resolvedWorkflowAgentRefs": self._dump_models(snapshot.resolved_workflow_agent_refs),
            "resolvedPersonaProfileRefs": self._dump_models(
                snapshot.resolved_persona_profile_refs,
            ),
            "resolvedCapabilities": self._dump_models(snapshot.resolved_capabilities),
            "resolvedBundleVersions": self._dump_models(snapshot.resolved_bundle_versions),
            "resolvedToolVersions": self._dump_models(snapshot.resolved_tool_versions),
            "resolvedConnectorVersions": self._dump_models(snapshot.resolved_connector_versions),
        }
        return self._hash_payload(payload)

    def _hash_output_payload(self, payload: Any) -> str | None:
        if payload is None:
            return None
        return self._hash_payload(payload)

    def _hash_payload(self, payload: Any) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _next_attempt_number(
        self,
        *,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None,
    ) -> int:
        latest = self.run_repository.get_latest_attempt(
            caller_type=caller_type,
            caller_id=caller_id,
            caller_scope_key=caller_scope_key,
        )
        if latest is None:
            return 1
        return latest.attempt_number + 1

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

    @staticmethod
    def _sort_resolved_capabilities(
        capabilities: Iterable[ResolvedCapabilityRead],
    ) -> list[ResolvedCapabilityRead]:
        return sorted(
            capabilities,
            key=lambda capability: (capability.capability_key, capability.capability_version),
        )

    @staticmethod
    def _dump_models(models: Iterable[Any]) -> list[dict[str, Any]]:
        return [model.model_dump(by_alias=True, exclude_none=True) for model in models]

    @staticmethod
    def _extract_required_string(source: dict[str, Any], *keys: str) -> str:
        value = AgentRuntimeService._extract_optional_string(source, *keys)
        if value is None:
            joined = ", ".join(keys)
            raise business_rule_error(
                "runtime_missing_required_field",
                f"Expected one of {joined} to be present",
            )
        return value

    @staticmethod
    def _extract_optional_string(source: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if value is None:
                return None
            normalized = str(value).strip()
            if normalized:
                return normalized
        return None

    @staticmethod
    def _extract_optional_int(source: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if value is None:
                return None
            return int(value)
        return None
