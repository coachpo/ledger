from __future__ import annotations

from sqlalchemy import select

from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.repositories.base import BaseRepository


class RuntimeApprovalRepository(BaseRepository[RuntimeApproval]):
    model = RuntimeApproval

    def list_all(
        self,
        *,
        run_id: int | None = None,
        caller_type: str | None = None,
        caller_id: int | None = None,
        workflow_spec_key: str | None = None,
        capability_key: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RuntimeApproval]:
        statement = select(self.model)
        if caller_type is not None or caller_id is not None or workflow_spec_key is not None:
            statement = statement.join(RuntimeRun, RuntimeRun.id == self.model.run_id)
        if run_id is not None:
            statement = statement.where(self.model.run_id == run_id)
        if caller_type is not None:
            statement = statement.where(RuntimeRun.caller_type == caller_type)
        if caller_id is not None:
            statement = statement.where(RuntimeRun.caller_id == caller_id)
        if workflow_spec_key is not None:
            statement = statement.where(RuntimeRun.workflow_spec_key == workflow_spec_key)
        if capability_key is not None:
            statement = statement.where(self.model.capability_key == capability_key)
        if status is not None:
            statement = statement.where(self.model.status == status)

        statement = statement.order_by(self.model.created_at.desc(), self.model.id.desc())
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def list_for_run(self, run_id: int) -> list[RuntimeApproval]:
        return self.list_all(run_id=run_id)

    def list_pending_for_run(self, run_id: int) -> list[RuntimeApproval]:
        return self.list_all(run_id=run_id, status="PENDING")
