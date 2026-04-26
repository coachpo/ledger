from __future__ import annotations

from sqlalchemy import select

from app.models.run import Run
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[Run]):
    model = Run

    def list_all(
        self,
        *,
        target_kind: str | None = None,
        target_id: int | None = None,
        target_key: str | None = None,
        target_version: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
    ) -> list[Run]:
        resolved_target_id = target_id if target_id is not None else workflow_id
        resolved_target_key = target_key if target_key is not None else workflow_key
        resolved_target_version = target_version if target_version is not None else workflow_version

        statement = select(self.model)
        if target_kind is not None:
            statement = statement.where(self.model.target_kind == target_kind)
        if resolved_target_id is not None:
            statement = statement.where(self.model.target_id == resolved_target_id)
        if resolved_target_key is not None:
            statement = statement.where(self.model.target_key == resolved_target_key)
        if resolved_target_version is not None:
            statement = statement.where(self.model.target_version == resolved_target_version)
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

    def list_for_target(
        self,
        *,
        target_kind: str,
        target_key: str,
        target_version: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Run]:
        return self.list_all(
            target_kind=target_kind,
            target_key=target_key,
            target_version=target_version,
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_latest_for_target(
        self,
        *,
        target_kind: str,
        target_key: str,
        target_version: int | None = None,
        status: str | None = None,
    ) -> Run | None:
        statement = select(self.model).where(self.model.target_kind == target_kind)
        statement = statement.where(self.model.target_key == target_key)
        if target_version is not None:
            statement = statement.where(self.model.target_version == target_version)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(
            self.model.started_at.desc(),
            self.model.created_at.desc(),
            self.model.id.desc(),
        )
        return self.session.scalar(statement.limit(1))
