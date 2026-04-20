from __future__ import annotations

from sqlalchemy import select

from app.models.run import Run
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[Run]):
    model = Run

    def list_all(
        self,
        *,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Run]:
        statement = select(self.model)
        if workflow_id is not None:
            statement = statement.where(self.model.workflow_id == workflow_id)
        if workflow_key is not None:
            statement = statement.where(self.model.workflow_key == workflow_key)
        if workflow_version is not None:
            statement = statement.where(self.model.workflow_version == workflow_version)
        if status is not None:
            statement = statement.where(self.model.status == status)

        statement = statement.order_by(
            self.model.started_at.desc(),
            self.model.created_at.desc(),
            self.model.id.desc(),
        )
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def get_detail(self, run_id: int) -> Run | None:
        statement = select(self.model).where(self.model.id == run_id)
        return self._get_by_statement(statement)

    def list_for_workflow(
        self,
        *,
        workflow_key: str,
        workflow_version: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Run]:
        return self.list_all(
            workflow_key=workflow_key,
            workflow_version=workflow_version,
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_latest_for_workflow(
        self,
        *,
        workflow_key: str,
        workflow_version: int | None = None,
        status: str | None = None,
    ) -> Run | None:
        statement = select(self.model).where(self.model.workflow_key == workflow_key)
        if workflow_version is not None:
            statement = statement.where(self.model.workflow_version == workflow_version)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(
            self.model.started_at.desc(),
            self.model.created_at.desc(),
            self.model.id.desc(),
        )
        return self.session.scalar(statement.limit(1))
