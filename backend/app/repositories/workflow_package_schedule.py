from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.formatting import utcnow
from app.models.run import Run
from app.models.workflow_package import WorkflowPackage
from app.models.workflow_package_schedule import (
    WorkflowPackageSchedule,
    WorkflowPackageScheduleFire,
)
from app.repositories.base import BaseRepository

_ACTIVE_RUN_STATUSES = ("queued", "running")
_TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled")
_FIRE_UNIQUE_CONSTRAINT = "uq_workflow_package_schedule_fires_schedule_fire_key"


class WorkflowPackageScheduleRepository(BaseRepository[WorkflowPackageSchedule]):
    model = WorkflowPackageSchedule

    def list_schedules(
        self,
        *,
        package_id: int | None = None,
        package_key: str | None = None,
        workflow_key: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkflowPackageSchedule]:
        statement = select(self.model)
        if package_key is not None:
            statement = statement.join(
                WorkflowPackage,
                self.model.package_id == WorkflowPackage.id,
            )
        statement = self._apply_schedule_filters(
            statement,
            package_id=package_id,
            package_key=package_key,
            workflow_key=workflow_key,
            status=status,
        )
        statement = statement.order_by(
            self.model.next_fire_at.asc().nulls_last(),
            self.model.id.asc(),
        )
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def count_schedules(
        self,
        *,
        package_id: int | None = None,
        package_key: str | None = None,
        workflow_key: str | None = None,
        status: str | None = None,
    ) -> int:
        statement = select(func.count(self.model.id))
        if package_key is not None:
            statement = statement.join(
                WorkflowPackage,
                self.model.package_id == WorkflowPackage.id,
            )
        statement = self._apply_schedule_filters(
            statement,
            package_id=package_id,
            package_key=package_key,
            workflow_key=workflow_key,
            status=status,
        )
        return int(self.session.scalar(statement) or 0)

    def list_due(
        self,
        *,
        now: datetime,
        limit: int,
        lock_rows: bool = False,
    ) -> list[WorkflowPackageSchedule]:
        statement = (
            select(self.model)
            .where(
                self.model.status == "enabled",
                self.model.next_fire_at.is_not(None),
                self.model.next_fire_at <= now,
            )
            .order_by(self.model.next_fire_at.asc(), self.model.id.asc())
        )
        if lock_rows:
            statement = statement.with_for_update(skip_locked=True)
        statement = statement.limit(limit)
        return self._list(statement)

    def list_due_for_update(self, *, now: datetime, limit: int) -> list[WorkflowPackageSchedule]:
        return self.list_due(now=now, limit=limit, lock_rows=True)

    def get_for_update(self, schedule_id: int) -> WorkflowPackageSchedule | None:
        statement = select(self.model).where(self.model.id == schedule_id).with_for_update()
        return self._get_by_statement(statement)

    def create_schedule(
        self,
        *,
        package_id: int,
        workflow_key: str,
        name: str,
        timezone: str,
        recurrence: dict[str, Any],
        description: str | None = None,
        status: str = "enabled",
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        next_fire_at: datetime | None = None,
        overlap_policy: str = "skip",
        misfire_policy: str = "catchUpOne",
        misfire_grace_seconds: int = 86400,
        input_template: dict[str, Any] | None = None,
        template_vars: dict[str, Any] | None = None,
    ) -> WorkflowPackageSchedule:
        schedule = self.model(
            package_id=package_id,
            workflow_key=workflow_key,
            name=name,
            description=description,
            status=status,
            timezone=timezone,
            recurrence=recurrence,
            starts_at=starts_at,
            ends_at=ends_at,
            next_fire_at=next_fire_at,
            overlap_policy=overlap_policy,
            misfire_policy=misfire_policy,
            misfire_grace_seconds=misfire_grace_seconds,
            input_template=input_template or {},
            template_vars=template_vars or {},
        )
        return self.add(schedule)

    def update_schedule(
        self,
        schedule: WorkflowPackageSchedule,
        **fields: object,
    ) -> WorkflowPackageSchedule:
        for field_name, value in fields.items():
            setattr(schedule, field_name, value)
        return self.add(schedule)

    def _apply_schedule_filters(
        self,
        statement: Any,
        *,
        package_id: int | None,
        package_key: str | None,
        workflow_key: str | None,
        status: str | None,
    ) -> Any:
        if package_id is not None:
            statement = statement.where(self.model.package_id == package_id)
        if package_key is not None:
            statement = statement.where(WorkflowPackage.key == package_key)
        if workflow_key is not None:
            statement = statement.where(self.model.workflow_key == workflow_key)
        if status is not None:
            statement = statement.where(self.model.status == status)
        return statement


class WorkflowPackageScheduleFireRepository(BaseRepository[WorkflowPackageScheduleFire]):
    model = WorkflowPackageScheduleFire

    def list_ids_for_schedule(self, schedule_id: int) -> list[int]:
        statement = (
            select(self.model.id)
            .where(self.model.schedule_id == schedule_id)
            .order_by(self.model.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_for_schedule(
        self,
        schedule_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkflowPackageScheduleFire]:
        statement = (
            select(self.model)
            .where(self.model.schedule_id == schedule_id)
            .order_by(
                self.model.scheduled_for.desc(),
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
        )
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def count_for_schedule(self, schedule_id: int) -> int:
        statement = select(func.count(self.model.id)).where(self.model.schedule_id == schedule_id)
        return int(self.session.scalar(statement) or 0)

    def get_by_schedule_fire_key(
        self,
        *,
        schedule_id: int,
        fire_key: str,
    ) -> WorkflowPackageScheduleFire | None:
        statement = select(self.model).where(
            self.model.schedule_id == schedule_id,
            self.model.fire_key == fire_key,
        )
        return self._get_by_statement(statement)

    def get_latest_for_schedule(self, schedule_id: int) -> WorkflowPackageScheduleFire | None:
        statement = (
            select(self.model)
            .where(self.model.schedule_id == schedule_id)
            .order_by(
                self.model.scheduled_for.desc(),
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def insert_idempotent(
        self,
        *,
        schedule_id: int,
        fire_key: str,
        scheduled_for: datetime,
        reason: str = "scheduled",
        status: str = "pending",
        scheduled_local_date: str | None = None,
        scheduled_local_time: str | None = None,
        scheduled_local_datetime: str | None = None,
        materialized_at: datetime | None = None,
        rendered_parameters: dict[str, Any] | None = None,
        skip_reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowPackageScheduleFire:
        values = {
            "schedule_id": schedule_id,
            "fire_key": fire_key,
            "reason": reason,
            "status": status,
            "scheduled_for": scheduled_for,
            "scheduled_local_date": scheduled_local_date,
            "scheduled_local_time": scheduled_local_time,
            "scheduled_local_datetime": scheduled_local_datetime,
            "materialized_at": materialized_at,
            "rendered_parameters": rendered_parameters or {},
            "skip_reason": skip_reason,
            "error_code": error_code,
            "error_message": error_message,
        }
        statement = (
            pg_insert(self.model)
            .values(**values)
            .on_conflict_do_nothing(constraint=_FIRE_UNIQUE_CONSTRAINT)
            .returning(self.model.id)
        )
        inserted_id = self.session.execute(statement).scalar_one_or_none()
        if inserted_id is not None:
            inserted = self.session.get(self.model, inserted_id)
            if inserted is not None:
                return inserted
        existing = self.get_by_schedule_fire_key(schedule_id=schedule_id, fire_key=fire_key)
        if existing is None:
            raise RuntimeError("Schedule fire idempotent insert did not return a row")
        return existing

    def update_fire(
        self,
        fire: WorkflowPackageScheduleFire,
        **fields: object,
    ) -> WorkflowPackageScheduleFire:
        for field_name, value in fields.items():
            setattr(fire, field_name, value)
        return self.add(fire)

    def mark_queued(
        self,
        fire: WorkflowPackageScheduleFire,
        *,
        materialized_at: datetime | None = None,
        rendered_parameters: dict[str, Any] | None = None,
    ) -> WorkflowPackageScheduleFire:
        fire.status = "queued"
        fire.materialized_at = materialized_at or fire.materialized_at or utcnow()
        if rendered_parameters is not None:
            fire.rendered_parameters = rendered_parameters
        fire.skip_reason = None
        fire.error_code = None
        fire.error_message = None
        return self.add(fire)

    def mark_skipped(
        self,
        fire: WorkflowPackageScheduleFire,
        *,
        skip_reason: str,
        materialized_at: datetime | None = None,
    ) -> WorkflowPackageScheduleFire:
        fire.status = "skipped"
        fire.skip_reason = skip_reason
        fire.materialized_at = materialized_at or fire.materialized_at or utcnow()
        return self.add(fire)

    def mark_failed(
        self,
        fire: WorkflowPackageScheduleFire,
        *,
        error_code: str,
        error_message: str,
        materialized_at: datetime | None = None,
    ) -> WorkflowPackageScheduleFire:
        fire.status = "failed"
        fire.error_code = error_code
        fire.error_message = error_message
        fire.materialized_at = materialized_at or fire.materialized_at or utcnow()
        return self.add(fire)

    def list_runs_for_fire_ids(self, fire_ids: Sequence[int]) -> list[Run]:
        resolved_ids = list(dict.fromkeys(fire_ids))
        if not resolved_ids:
            return []
        statement = (
            select(Run)
            .where(Run.schedule_fire_id.in_(resolved_ids))
            .order_by(Run.schedule_fire_id.asc(), Run.id.asc())
        )
        return list(self.session.scalars(statement))

    def get_run_for_fire(self, fire_id: int) -> Run | None:
        statement = select(Run).where(Run.schedule_fire_id == fire_id).limit(1)
        return self.session.scalar(statement)

    def get_latest_run_for_schedule(self, schedule_id: int) -> Run | None:
        statement = (
            select(Run)
            .where(Run.schedule_id == schedule_id)
            .order_by(
                Run.scheduled_for.desc().nulls_last(),
                Run.queued_at.desc(),
                Run.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def get_latest_terminal_run_for_schedule(self, schedule_id: int) -> Run | None:
        statement = (
            select(Run)
            .where(
                Run.schedule_id == schedule_id,
                Run.status.in_(_TERMINAL_RUN_STATUSES),
            )
            .order_by(
                Run.scheduled_for.desc().nulls_last(),
                Run.finished_at.desc().nulls_last(),
                Run.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def has_active_run_for_schedule(self, schedule_id: int) -> bool:
        statement = (
            select(Run.id)
            .where(
                Run.schedule_id == schedule_id,
                Run.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .limit(1)
        )
        return self.session.scalar(statement) is not None


__all__ = [
    "WorkflowPackageScheduleFireRepository",
    "WorkflowPackageScheduleRepository",
]
