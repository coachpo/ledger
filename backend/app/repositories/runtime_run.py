from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from app.models.runtime_run import RuntimeRun
from app.repositories.base import BaseRepository

_ACTIVE_RUN_STATUSES = ("QUEUED", "RUNNING", "WAITING_APPROVAL")


class RuntimeRunRepository(BaseRepository[RuntimeRun]):
    model = RuntimeRun

    def list_all(
        self,
        *,
        caller_type: str | None = None,
        caller_id: int | None = None,
        caller_scope_key: str | None = None,
        caller_identity_key: str | None = None,
        workflow_spec_key: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RuntimeRun]:
        statement = select(self.model)
        if caller_type is not None:
            statement = statement.where(self.model.caller_type == caller_type)
        if caller_id is not None:
            statement = statement.where(self.model.caller_id == caller_id)
        if caller_scope_key is not None:
            statement = statement.where(self.model.caller_scope_key == caller_scope_key)
        if caller_identity_key is not None:
            statement = statement.where(self.model.caller_identity_key == caller_identity_key)
        if workflow_spec_key is not None:
            statement = statement.where(self.model.workflow_spec_key == workflow_spec_key)
        if status is not None:
            statement = statement.where(self.model.status == status)

        statement = statement.order_by(self.model.created_at.desc(), self.model.id.desc())
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def list_for_caller(
        self,
        *,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None = None,
    ) -> list[RuntimeRun]:
        statement = select(self.model).where(self.model.caller_type == caller_type)
        if caller_id is None:
            statement = statement.where(self.model.caller_id.is_(None))
        else:
            statement = statement.where(self.model.caller_id == caller_id)
        if caller_scope_key is None:
            statement = statement.where(self.model.caller_scope_key.is_(None))
        else:
            statement = statement.where(self.model.caller_scope_key == caller_scope_key)
        statement = statement.order_by(
            self.model.attempt_number.desc(), self.model.created_at.desc()
        )
        return self._list(statement)

    def list_tryouts(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RuntimeRun]:
        return self.list_all(
            caller_type="tryout",
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_for_caller_attempt(
        self,
        *,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None,
        attempt_number: int,
    ) -> RuntimeRun | None:
        statement = select(self.model).where(
            self.model.caller_type == caller_type,
            self.model.attempt_number == attempt_number,
        )
        if caller_id is None:
            statement = statement.where(self.model.caller_id.is_(None))
        else:
            statement = statement.where(self.model.caller_id == caller_id)
        if caller_scope_key is None:
            statement = statement.where(self.model.caller_scope_key.is_(None))
        else:
            statement = statement.where(self.model.caller_scope_key == caller_scope_key)
        return self._get_by_statement(statement)

    def get_latest_attempt(
        self,
        *,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None,
    ) -> RuntimeRun | None:
        statement = select(self.model).where(self.model.caller_type == caller_type)
        if caller_id is None:
            statement = statement.where(self.model.caller_id.is_(None))
        else:
            statement = statement.where(self.model.caller_id == caller_id)
        if caller_scope_key is None:
            statement = statement.where(self.model.caller_scope_key.is_(None))
        else:
            statement = statement.where(self.model.caller_scope_key == caller_scope_key)
        statement = statement.order_by(
            self.model.attempt_number.desc(), self.model.created_at.desc()
        )
        return self.session.scalar(statement.limit(1))

    def get_active_for_caller(
        self,
        *,
        caller_type: str,
        caller_id: int | None,
        caller_scope_key: str | None,
    ) -> RuntimeRun | None:
        statement = select(self.model).where(
            self.model.caller_type == caller_type,
            self.model.status.in_(_ACTIVE_RUN_STATUSES),
        )
        if caller_id is None:
            statement = statement.where(self.model.caller_id.is_(None))
        else:
            statement = statement.where(self.model.caller_id == caller_id)
        if caller_scope_key is None:
            statement = statement.where(self.model.caller_scope_key.is_(None))
        else:
            statement = statement.where(self.model.caller_scope_key == caller_scope_key)
        statement = statement.order_by(
            self.model.attempt_number.desc(), self.model.created_at.desc()
        )
        return self.session.scalar(statement.limit(1))

    def list_by_ids(self, run_ids: Iterable[int]) -> list[RuntimeRun]:
        ids = sorted(set(run_ids))
        if not ids:
            return []
        statement = select(self.model).where(self.model.id.in_(ids))
        return self._list(statement)

    def list_active_for_caller_identity(
        self,
        *,
        caller_type: str,
        caller_identity_key: str,
    ) -> list[RuntimeRun]:
        statement = (
            select(self.model)
            .where(
                self.model.caller_type == caller_type,
                self.model.caller_identity_key == caller_identity_key,
                self.model.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)
