from __future__ import annotations

from datetime import timedelta
from typing import TypeVar

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import utcnow
from app.schemas.runtime import (
    RuntimeArtifactRead,
    RuntimeCallerType,
    RuntimeExecutionKind,
    RuntimeRunCreate,
    RuntimeRunCreated,
    RuntimeRunRead,
)
from app.schemas.tryout import TryoutExecute, TryoutPersistRead, TryoutRead
from app.services.agent_runtime_service import AgentRuntimeService, RuntimeRunShellOptions

_TRYOUT_EPHEMERAL_TTL = timedelta(hours=24)
_TRYOUT_PERSISTABLE_STATUSES = {
    "QUEUED",
    "WAITING_APPROVAL",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
}
_TryoutReadModel = TypeVar("_TryoutReadModel", TryoutRead, TryoutPersistRead)


class TryoutService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.runtime_service = AgentRuntimeService(session)

    def create_tryout(self, payload: TryoutExecute) -> RuntimeRunCreated:
        created = self.runtime_service.execute_run(
            self._build_runtime_payload(payload),
            shell_options=RuntimeRunShellOptions(
                retention_class="ephemeral",
                expires_at=utcnow() + _TRYOUT_EPHEMERAL_TTL,
            ),
        )
        if payload.persist_run:
            persisted = self.persist_tryout(created.run_id)
            return RuntimeRunCreated(
                run_id=persisted.run_id,
                status=persisted.status,
                expires_at=persisted.expires_at,
            )
        return RuntimeRunCreated(
            run_id=created.run_id,
            status=created.status,
            expires_at=created.expires_at,
        )

    def get_tryout(self, run_id: int) -> TryoutRead:
        run = self.runtime_service.get_run(run_id)
        self._ensure_tryout_run(run)
        artifact = self.runtime_service.get_artifact(run_id)
        return self._build_tryout_read(TryoutRead, run=run, artifact=artifact)

    def persist_tryout(self, run_id: int) -> TryoutPersistRead:
        run = self.runtime_service.get_run(run_id)
        self._ensure_tryout_run(run)
        if run.status not in _TRYOUT_PERSISTABLE_STATUSES:
            raise business_rule_error(
                "tryout_persist_not_allowed",
                f"Tryout {run_id} cannot be persisted from status {run.status}",
            )
        persisted = self.runtime_service.persist_run_in_place(run_id)
        artifact = self.runtime_service.get_artifact(run_id)
        return self._build_tryout_read(TryoutPersistRead, run=persisted, artifact=artifact)

    @staticmethod
    def _build_runtime_payload(payload: TryoutExecute) -> RuntimeRunCreate:
        execution_kind = (
            RuntimeExecutionKind.WORKFLOW
            if payload.workflow_spec_key is not None
            else RuntimeExecutionKind.SINGLE_AGENT
        )
        return RuntimeRunCreate(
            caller_type=RuntimeCallerType.TRYOUT,
            caller_id=None,
            caller_scope_key=None,
            caller_identity_key=None,
            execution_kind=execution_kind,
            workflow_spec_key=payload.workflow_spec_key,
            workflow_spec_version=payload.workflow_spec_version,
            agent_spec_key=payload.agent_spec_key,
            agent_spec_version=payload.agent_spec_version,
            inputs=payload.inputs,
            persona_profile_refs=payload.persona_profile_refs,
            persist_run=False,
        )

    @staticmethod
    def _ensure_tryout_run(run: RuntimeRunRead) -> None:
        if run.caller_type != RuntimeCallerType.TRYOUT:
            raise not_found_error("Tryout")

    @staticmethod
    def _build_tryout_read(
        model: type[_TryoutReadModel],
        *,
        run: RuntimeRunRead,
        artifact: RuntimeArtifactRead,
    ) -> _TryoutReadModel:
        return model.model_validate(
            {
                "run_id": run.run_id,
                "status": run.status,
                "final_output": artifact.final_output,
                "report_markdown": artifact.report_markdown,
                "trace_summary": run.trace_summary,
                "approval_summary": run.approval_summary,
                "expires_at": run.expires_at,
                "terminal_error_code": artifact.terminal_error_code,
                "terminal_error_message": artifact.terminal_error_message,
            }
        )


__all__ = ["TryoutService"]
