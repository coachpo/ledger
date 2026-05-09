from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.formatting import utcnow
from app.models.run import Run
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackageVersion
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
        workflow_package_id: int | None = None,
        workflow_package_key: str | None = None,
        package_workflow_key: str | None = None,
        model_connection_key: str | None = None,
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
        if workflow_package_id is not None:
            statement = statement.where(self.model.workflow_package_id == workflow_package_id)
        if workflow_package_key is not None:
            statement = statement.where(self.model.workflow_package_key == workflow_package_key)
        if package_workflow_key is not None:
            statement = statement.where(
                self.model.workflow_package_workflow_key == package_workflow_key
            )
        if model_connection_key is not None:
            statement = statement.join(
                WorkflowPackageVersion,
                self.model.workflow_package_version_id == WorkflowPackageVersion.id,
            ).where(
                WorkflowPackageVersion.compiled_plan["agents"].contains(
                    [{"modelConnection": model_connection_key}]
                )
            )

        statement = statement.order_by(
            self.model.queued_at.desc(),
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
        statement = (
            select(self.model)
            .where(self.model.id == run_id)
            .options(selectinload(self.model.steps).selectinload(RunStep.invocations))
        )
        return self._get_by_statement(statement)

    def list_ids_for_target_owner(
        self,
        *,
        target_kind: str,
        target_id: int,
        workflow_package_id: int | None = None,
    ) -> list[int]:
        statement = select(self.model.id).where(
            self._target_owner_filter(
                target_kind=target_kind,
                target_id=target_id,
                workflow_package_id=workflow_package_id,
            )
        )
        return list(self.session.scalars(statement))

    def list_for_target_owner(
        self,
        *,
        target_kind: str,
        target_id: int,
        workflow_package_id: int | None = None,
    ) -> list[Run]:
        statement = select(self.model).where(
            self._target_owner_filter(
                target_kind=target_kind,
                target_id=target_id,
                workflow_package_id=workflow_package_id,
            )
        )
        return self._list(statement)

    def _target_owner_filter(
        self,
        *,
        target_kind: str,
        target_id: int,
        workflow_package_id: int | None,
    ) -> ColumnElement[bool]:
        owner_filters: list[ColumnElement[bool]] = [
            (self.model.target_kind == target_kind) & (self.model.target_id == target_id)
        ]
        for column_name in self._target_owner_fk_column_names(target_kind):
            target_fk_column = self.model.__table__.c.get(column_name)
            if target_fk_column is not None:
                owner_filters.append(target_fk_column == target_id)
        if target_kind == "workflowPackage":
            package_id = workflow_package_id if workflow_package_id is not None else target_id
            owner_filters.append(self.model.workflow_package_id == package_id)
        return or_(*owner_filters)

    @staticmethod
    def _target_owner_fk_column_names(target_kind: str) -> tuple[str, ...]:
        if target_kind == "workflowPackage":
            return ("target_workflow_package_id", "workflow_package_id")
        return (f"target_{target_kind}_id", f"{target_kind}_id")

    def claim_next_queued(self, run_id: int | None = None) -> Run | None:
        statement = select(self.model).where(self.model.status == "queued")
        if run_id is not None:
            statement = statement.where(self.model.id == run_id)
        statement = (
            statement.order_by(self.model.queued_at.asc(), self.model.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        run = self.session.scalar(statement)
        if run is None:
            return None
        run.status = "running"
        run.started_at = utcnow()
        run.error = None
        run.finished_at = None
        return self.add(run)

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
            self.model.queued_at.desc(),
            self.model.started_at.desc(),
            self.model.created_at.desc(),
            self.model.id.desc(),
        )
        return self.session.scalar(statement.limit(1))
