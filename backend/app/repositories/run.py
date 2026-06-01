from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.formatting import utcnow
from app.models.agent_memory import RunMemoryEvent
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
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
                RunWorkflowPackageSnapshot,
                self.model.id == RunWorkflowPackageSnapshot.run_id,
            ).where(
                or_(
                    RunWorkflowPackageSnapshot.compiled_plan["agents"].contains(
                        [{"modelConnection": model_connection_key}]
                    ),
                    RunWorkflowPackageSnapshot.resolved_model_connections.contains(
                        [{"key": model_connection_key}]
                    ),
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

    def invocation_status_counts_by_run_id(
        self,
        run_ids: Iterable[int],
    ) -> dict[int, dict[str, int]]:
        resolved_run_ids = list(dict.fromkeys(run_ids))
        if not resolved_run_ids:
            return {}

        counts_by_run_id: dict[int, dict[str, int]] = {run_id: {} for run_id in resolved_run_ids}
        for invocation_model in (RunAgentInvocation, RunOperationInvocation):
            statement = (
                select(
                    invocation_model.run_id,
                    invocation_model.status,
                    func.count().label("status_count"),
                )
                .where(invocation_model.run_id.in_(resolved_run_ids))
                .group_by(invocation_model.run_id, invocation_model.status)
            )
            for run_id, status, status_count in self.session.execute(statement):
                run_counts = counts_by_run_id.setdefault(int(run_id), {})
                status_key = str(status)
                run_counts[status_key] = run_counts.get(status_key, 0) + int(status_count)
        return counts_by_run_id

    def get_detail(self, run_id: int) -> Run | None:
        statement = (
            select(self.model)
            .where(self.model.id == run_id)
            .options(
                selectinload(self.model.fork),
                selectinload(self.model.steps).selectinload(RunStep.invocations),
                selectinload(self.model.steps).selectinload(RunStep.operation_invocations),
            )
        )
        return self._get_by_statement(statement)

    def list_memory_events_for_run(self, run_id: int) -> list[RunMemoryEvent]:
        statement = (
            select(RunMemoryEvent)
            .where(RunMemoryEvent.run_id == run_id)
            .order_by(RunMemoryEvent.created_at.asc(), RunMemoryEvent.id.asc())
        )
        return list(self.session.scalars(statement))

    def serial_queue_blocker_run_ids_by_run_id(
        self,
        run_ids: Iterable[int],
    ) -> dict[int, int]:
        resolved_run_ids = list(dict.fromkeys(run_ids))
        if not resolved_run_ids:
            return {}

        queued_run = aliased(self.model)
        serial_blocker = aliased(self.model)
        older_queued_blocker = and_(
            serial_blocker.status == "queued",
            or_(
                serial_blocker.queued_at < queued_run.queued_at,
                and_(
                    serial_blocker.queued_at == queued_run.queued_at,
                    serial_blocker.id < queued_run.id,
                ),
            ),
        )
        statement = (
            select(queued_run.id, serial_blocker.id)
            .join(
                serial_blocker,
                and_(
                    serial_blocker.execution_scope_key == queued_run.execution_scope_key,
                    serial_blocker.concurrency_policy == "serial",
                    or_(serial_blocker.status == "running", older_queued_blocker),
                ),
            )
            .where(
                queued_run.id.in_(resolved_run_ids),
                queued_run.status == "queued",
                queued_run.concurrency_policy == "serial",
                queued_run.execution_scope_key.is_not(None),
            )
            .order_by(
                queued_run.id.asc(),
                case((serial_blocker.status == "running", 0), else_=1),
                serial_blocker.queued_at.asc(),
                serial_blocker.id.asc(),
            )
        )
        blockers_by_run_id: dict[int, int] = {}
        for run_id, blocker_run_id in self.session.execute(statement):
            resolved_run_id = int(run_id)
            if resolved_run_id not in blockers_by_run_id:
                blockers_by_run_id[resolved_run_id] = int(blocker_run_id)
        return blockers_by_run_id

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

    def list_directly_owned_by_schedule(
        self,
        *,
        schedule_id: int,
        fire_ids: Iterable[int],
    ) -> list[Run]:
        resolved_fire_ids = list(dict.fromkeys(fire_ids))
        ownership_filters: list[ColumnElement[bool]] = [self.model.schedule_id == schedule_id]
        if resolved_fire_ids:
            ownership_filters.append(self.model.schedule_fire_id.in_(resolved_fire_ids))
        statement = select(self.model).where(or_(*ownership_filters)).order_by(self.model.id.asc())
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
        for _ in range(2):
            run = self._claim_next_queued_once(run_id=run_id)
            if run is None:
                return None
            try:
                self.session.flush()
            except IntegrityError:
                self.session.rollback()
                if run_id is not None:
                    return None
                continue
            return run
        return None

    def _claim_next_queued_once(self, run_id: int | None = None) -> Run | None:
        running_run = aliased(self.model)
        older_queued_run = aliased(self.model)
        running_scope_exists = (
            select(running_run.id)
            .where(
                running_run.status == "running",
                running_run.concurrency_policy == "serial",
                running_run.execution_scope_key == self.model.execution_scope_key,
            )
            .exists()
        )
        older_queued_scope_exists = (
            select(older_queued_run.id)
            .where(
                older_queued_run.status == "queued",
                older_queued_run.concurrency_policy == "serial",
                older_queued_run.execution_scope_key == self.model.execution_scope_key,
                or_(
                    older_queued_run.queued_at < self.model.queued_at,
                    and_(
                        older_queued_run.queued_at == self.model.queued_at,
                        older_queued_run.id < self.model.id,
                    ),
                ),
            )
            .exists()
        )
        serial_scope_is_eligible = or_(
            self.model.concurrency_policy != "serial",
            self.model.execution_scope_key.is_(None),
            ~running_scope_exists,
        )
        serial_queue_head_is_eligible = or_(
            self.model.concurrency_policy != "serial",
            self.model.execution_scope_key.is_(None),
            ~older_queued_scope_exists,
        )
        statement = select(self.model).where(
            self.model.status == "queued",
            self.model.lease_owner.is_(None),
            serial_scope_is_eligible,
            serial_queue_head_is_eligible,
        )
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
        run.error = None
        run.finished_at = None
        run.last_claimed_at = utcnow()
        run.attempt_count = int(run.attempt_count or 0) + 1
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
