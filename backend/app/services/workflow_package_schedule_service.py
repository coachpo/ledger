# pyright: reportExplicitAny=false
from __future__ import annotations

import calendar
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Final, cast
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, not_found_error, validation_error
from app.core.formatting import to_utc, utcnow
from app.db.engine import get_session_factory
from app.models.run import Run
from app.models.workflow_package import WorkflowPackage
from app.models.workflow_package_schedule import (
    WorkflowPackageSchedule,
    WorkflowPackageScheduleFire,
)
from app.repositories.workflow_package import WorkflowPackageRepository
from app.repositories.workflow_package_schedule import (
    WorkflowPackageScheduleFireRepository,
    WorkflowPackageScheduleRepository,
)
from app.schemas.schedule import (
    FireReason,
    FireStatus,
    MisfirePolicy,
    OverlapPolicy,
    ScheduleCreate,
    ScheduleFireListRead,
    ScheduleFireRead,
    ScheduleListRead,
    SchedulePreviewRead,
    SchedulePreviewRequest,
    SchedulePreviewUnsavedRequest,
    ScheduleRead,
    ScheduleRecurrence,
    ScheduleRunNowRead,
    ScheduleRunNowRequest,
    ScheduleRunNowRunRead,
    ScheduleStatus,
    ScheduleUpdate,
    ScheduleValidationError,
)
from app.services.execution_providers import ExecutionProviderBundle
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.workflow_package_schedule_inputs import (
    SCHEDULE_RENDER_VALIDATION_FAILED,
    ScheduledInputLastRunContext,
    ScheduledInputRenderPreview,
    build_scheduled_input_template_context,
    render_and_validate_scheduled_input_template,
    require_scheduled_input_render_ready,
)

if TYPE_CHECKING:
    from app.services.run_service import RunService

_UNSET: Final = object()


@dataclass(frozen=True)
class DueWorkflowPackageSchedule:
    id: int
    package_id: int
    package_key: str
    workflow_key: str
    name: str
    timezone: str
    recurrence: dict[str, Any]
    next_fire_at: datetime
    overlap_policy: OverlapPolicy
    misfire_policy: MisfirePolicy
    misfire_grace_seconds: int
    input_template: dict[str, Any]
    template_vars: dict[str, Any]
    ends_at: datetime | None


@dataclass(frozen=True)
class ScheduleLatestMetadata:
    fire_id: int | None
    run_id: int | None
    status: str | None


@dataclass(frozen=True)
class ScheduleFireMetadata:
    schedule_id: int
    fire_key: str
    reason: FireReason
    scheduled_for: datetime
    scheduled_local_date: str | None = None
    scheduled_local_time: str | None = None
    scheduled_local_datetime: str | None = None


@dataclass(frozen=True)
class ScheduleQueuedRunResult:
    fire: WorkflowPackageScheduleFire
    run: Run
    created_run: bool


@dataclass(frozen=True)
class ScheduleOccurrenceContext:
    scheduled_for: datetime
    previous_scheduled_for: datetime | None
    next_fire_at: datetime | None
    scheduled_local_date: str
    scheduled_local_time: str
    scheduled_local_datetime: str


RunServiceFactory = Callable[..., "RunService"]


def default_run_service_factory(
    session: Session,
    session_factory: sessionmaker[Session],
    *,
    provider_bundle: ExecutionProviderBundle | None = None,
) -> RunService:
    import importlib

    run_service_class = importlib.import_module("app.services.run_service").__dict__["RunService"]
    return cast(
        "RunService",
        run_service_class(
            session,
            session_factory,
            provider_bundle=provider_bundle,
        ),
    )


def _workflow_input_schema(
    package: WorkflowPackage,
    workflow_key: str,
) -> dict[str, Any] | None:
    workflows = package.compiled_plan.get("workflows")
    if not isinstance(workflows, Sequence):
        return None
    for workflow in workflows:
        if not isinstance(workflow, Mapping):
            continue
        if str(workflow.get("key") or "") != workflow_key:
            continue
        input_schema = workflow.get("inputSchema")
        if isinstance(input_schema, dict):
            return cast(dict[str, Any], deepcopy(input_schema))
        return {}
    return None


class WorkflowPackageScheduleService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        *,
        provider_bundle: ExecutionProviderBundle | None = None,
        run_service: RunService | None = None,
        run_service_factory: RunServiceFactory = default_run_service_factory,
    ) -> None:
        self.session: Session = session
        self.session_factory: sessionmaker[Session] = session_factory or get_session_factory()
        self.provider_bundle: ExecutionProviderBundle | None = provider_bundle
        self.run_service: RunService | None = run_service
        self.run_service_factory: RunServiceFactory = run_service_factory
        self.schedule_repository: WorkflowPackageScheduleRepository = (
            WorkflowPackageScheduleRepository(session)
        )
        self.fire_repository: WorkflowPackageScheduleFireRepository = (
            WorkflowPackageScheduleFireRepository(session)
        )
        self.workflow_package_repository: WorkflowPackageRepository = WorkflowPackageRepository(
            session
        )
        self.schema_compiler: OutputSchemaCompiler = OutputSchemaCompiler()

    def _run_service(self) -> RunService:
        if self.run_service is not None:
            return self.run_service
        return self.run_service_factory(
            self.session,
            self.session_factory,
            provider_bundle=self.provider_bundle,
        )

    def _fresh_schedule_service(self, session: Session) -> WorkflowPackageScheduleService:
        return type(self)(
            session,
            self.session_factory,
            provider_bundle=self.provider_bundle,
            run_service_factory=self.run_service_factory,
        )

    def list_schedules(
        self,
        *,
        package_id: int | None = None,
        package_key: str | None = None,
        workflow_key: str | None = None,
        status: ScheduleStatus | str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ScheduleListRead:
        resolved_status = _enum_value(status) if status is not None else None
        schedules = self.schedule_repository.list_schedules(
            package_id=package_id,
            package_key=package_key,
            workflow_key=workflow_key,
            status=resolved_status,
            limit=limit,
            offset=offset,
        )
        total_count = self.schedule_repository.count_schedules(
            package_id=package_id,
            package_key=package_key,
            workflow_key=workflow_key,
            status=resolved_status,
        )
        return ScheduleListRead.model_validate(
            {
                "items": [self._to_schedule_read(schedule) for schedule in schedules],
                "totalCount": total_count,
                "limit": limit,
                "offset": offset,
            }
        )

    def get_schedule(self, schedule_id: int) -> ScheduleRead:
        return self._to_schedule_read(self._get_schedule_model(schedule_id))

    def create_schedule(
        self,
        payload: ScheduleCreate,
        *,
        next_fire_at: datetime | None | object = _UNSET,
    ) -> ScheduleRead:
        try:
            package = self._get_package_model(payload.package_id)
            self._validate_package_workflow_key(package, payload.workflow_key)
            resolved_next_fire_at = (
                self._initial_next_fire_at(payload)
                if next_fire_at is _UNSET
                else cast(datetime | None, next_fire_at)
            )
            schedule = self.schedule_repository.create_schedule(
                package_id=payload.package_id,
                workflow_key=payload.workflow_key,
                name=payload.name,
                description=payload.description,
                status=_enum_value(payload.status),
                timezone=payload.timezone,
                recurrence=_recurrence_payload(payload.recurrence),
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                next_fire_at=resolved_next_fire_at,
                overlap_policy=_enum_value(payload.overlap_policy),
                misfire_policy=_enum_value(payload.misfire_policy),
                misfire_grace_seconds=payload.misfire_grace_seconds,
                input_template=deepcopy(payload.input_template),
                template_vars=deepcopy(payload.template_vars),
            )
            self.session.commit()
            self.session.refresh(schedule)
            return self._to_schedule_read(schedule, package=package)
        except Exception:
            self.session.rollback()
            raise

    def update_schedule(
        self,
        schedule_id: int,
        payload: ScheduleUpdate,
        *,
        next_fire_at: datetime | None | object = _UNSET,
    ) -> ScheduleRead:
        try:
            schedule = self._get_schedule_model_for_update(schedule_id)
            fields = self._update_fields(payload)
            if "workflow_key" in fields:
                package = self._get_package_model(schedule.package_id)
                self._validate_package_workflow_key(package, str(fields["workflow_key"]))
            if next_fire_at is not _UNSET:
                fields["next_fire_at"] = next_fire_at
            elif self._requires_next_fire_recompute(payload):
                fields["next_fire_at"] = self._next_fire_at_for_update(schedule, fields)
            updated = self.schedule_repository.update_schedule(schedule, **fields)
            self.session.commit()
            self.session.refresh(updated)
            return self._to_schedule_read(updated)
        except Exception:
            self.session.rollback()
            raise

    def delete_schedule(self, schedule_id: int, *, commit: bool = True) -> None:
        if not commit:
            self._delete_schedule_rows(schedule_id)
            return
        try:
            self._delete_schedule_rows(schedule_id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def list_due_schedules(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
        lock_rows: bool = False,
    ) -> list[DueWorkflowPackageSchedule]:
        due_at = now or utcnow()
        schedules = self.schedule_repository.list_due(
            now=due_at,
            limit=limit,
            lock_rows=lock_rows,
        )
        return [self.to_due_schedule(schedule) for schedule in schedules]

    def list_fire_history(
        self,
        schedule_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ScheduleFireListRead:
        _ = self._get_schedule_model(schedule_id)
        fires = self.fire_repository.list_for_schedule(schedule_id, limit=limit, offset=offset)
        runs_by_fire_id = self._runs_by_fire_id([fire.id for fire in fires])
        return ScheduleFireListRead.model_validate(
            {
                "items": [
                    self._to_fire_read(fire, run=runs_by_fire_id.get(fire.id)) for fire in fires
                ],
                "totalCount": self.fire_repository.count_for_schedule(schedule_id),
                "limit": limit,
                "offset": offset,
            }
        )

    def preview_unsaved_schedule(
        self,
        payload: SchedulePreviewUnsavedRequest,
    ) -> SchedulePreviewRead:
        package = self._get_package_model(payload.package_id)
        scheduled_for = to_utc(payload.scheduled_for)
        metadata = self._preview_fire_metadata(
            schedule_id=0,
            fire_key=self._scheduled_fire_key(scheduled_for),
            reason=FireReason.SCHEDULED,
            scheduled_for=scheduled_for,
            timezone_name=payload.timezone,
        )
        preview = self.preview_schedule_input_render(
            package_id=payload.package_id,
            package_key=package.key,
            workflow_key=payload.workflow_key,
            schedule_id=None,
            schedule_name="Unsaved schedule",
            timezone=payload.timezone,
            input_template=payload.input_template,
            template_vars=payload.template_vars,
            fire_metadata=metadata,
            window_start=self._window_start_for_recurrence(
                payload.recurrence,
                scheduled_for,
                timezone_name=payload.timezone,
            ),
            window_end=scheduled_for,
        )
        return self._to_preview_read(None, scheduled_for, preview)

    def preview_schedule(
        self,
        schedule_id: int,
        payload: SchedulePreviewRequest | None = None,
    ) -> SchedulePreviewRead:
        request = payload or SchedulePreviewRequest()
        schedule = self._get_schedule_model(schedule_id)
        scheduled_for = (
            to_utc(request.scheduled_for) if request.scheduled_for else schedule.next_fire_at
        )
        if scheduled_for is None:
            return self._empty_preview(
                schedule_id=schedule.id,
                field="scheduledFor",
                issue="Schedule has no next fire time to preview",
            )
        package = self._get_package_model(schedule.package_id)
        metadata = self._preview_fire_metadata(
            schedule_id=schedule.id,
            fire_key=self._scheduled_fire_key(scheduled_for),
            reason=FireReason.SCHEDULED,
            scheduled_for=scheduled_for,
            timezone_name=schedule.timezone,
        )
        preview = self.preview_schedule_input_render(
            package_id=schedule.package_id,
            package_key=package.key,
            workflow_key=schedule.workflow_key,
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            timezone=schedule.timezone,
            input_template=deepcopy(schedule.input_template),
            template_vars=deepcopy(schedule.template_vars),
            fire_metadata=metadata,
            window_start=self._window_start_for_recurrence(
                schedule.recurrence,
                scheduled_for,
                timezone_name=schedule.timezone,
            ),
            window_end=scheduled_for,
            last_run=self._latest_terminal_run_context(schedule.id),
        )
        return self._to_preview_read(schedule.id, scheduled_for, preview)

    def run_schedule_now(
        self,
        schedule_id: int,
        payload: ScheduleRunNowRequest,
    ) -> ScheduleRunNowRead:
        materialized_at = utcnow()
        scheduled_for = to_utc(payload.scheduled_for)
        metadata: ScheduleFireMetadata | None = None
        try:
            schedule = self._get_schedule_model_for_update(schedule_id)
            package = self._get_package_model(schedule.package_id)
            metadata = self._preview_fire_metadata(
                schedule_id=schedule.id,
                fire_key=self._manual_fire_key(scheduled_for, payload.idempotency_key),
                reason=FireReason.MANUAL,
                scheduled_for=scheduled_for,
                timezone_name=schedule.timezone,
            )
            queued = self.queue_schedule_fire_run(
                schedule=schedule,
                package=package,
                metadata=metadata,
                materialized_at=materialized_at,
                window_start=self._window_start_for_recurrence(
                    schedule.recurrence,
                    scheduled_for,
                    timezone_name=schedule.timezone,
                ),
                window_end=scheduled_for,
                last_run=self._latest_terminal_run_context(schedule.id),
            )
            self.session.commit()
            self.session.refresh(queued.fire)
            self.session.refresh(queued.run)
            return self._to_run_now_read(schedule, package, queued.fire, queued.run)
        except ApiError as exc:
            self.session.rollback()
            if metadata is not None:
                self._record_fire_failure_after_rollback(
                    metadata,
                    materialized_at=materialized_at,
                    error_code=exc.code,
                    error_message=exc.message,
                )
            raise
        except Exception:
            self.session.rollback()
            if metadata is not None:
                self._record_fire_failure_after_rollback(
                    metadata,
                    materialized_at=materialized_at,
                    error_code="schedule_run_now_failed",
                    error_message="Schedule run-now failed",
                )
            raise

    def queue_schedule_fire_run(
        self,
        *,
        schedule: WorkflowPackageSchedule,
        metadata: ScheduleFireMetadata,
        materialized_at: datetime,
        window_start: datetime | None,
        window_end: datetime | None,
        last_run: ScheduledInputLastRunContext | None = None,
        package: WorkflowPackage | None = None,
        fire: WorkflowPackageScheduleFire | None = None,
    ) -> ScheduleQueuedRunResult:
        queued_fire = fire or self.fire_repository.insert_idempotent(
            schedule_id=metadata.schedule_id,
            fire_key=metadata.fire_key,
            reason=metadata.reason.value,
            status=FireStatus.PENDING.value,
            scheduled_for=metadata.scheduled_for,
            scheduled_local_date=metadata.scheduled_local_date,
            scheduled_local_time=metadata.scheduled_local_time,
            scheduled_local_datetime=metadata.scheduled_local_datetime,
            materialized_at=materialized_at,
        )
        existing_run = self.fire_repository.get_run_for_fire(queued_fire.id)
        if existing_run is not None:
            return ScheduleQueuedRunResult(
                fire=queued_fire,
                run=existing_run,
                created_run=False,
            )
        resolved_package = package or self._get_package_model(schedule.package_id)
        preview = self.preview_schedule_input_render(
            package_id=schedule.package_id,
            package_key=resolved_package.key,
            workflow_key=schedule.workflow_key,
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            timezone=schedule.timezone,
            input_template=deepcopy(schedule.input_template),
            template_vars=deepcopy(schedule.template_vars),
            fire_metadata=metadata,
            fire_id=queued_fire.id,
            materialized_at=materialized_at,
            window_start=window_start,
            window_end=window_end,
            last_run=last_run,
        )
        rendered_parameters = require_scheduled_input_render_ready(preview)
        created_run = self._run_service().create_scheduled_workflow_package_run(
            package_id=schedule.package_id,
            workflow_key=schedule.workflow_key,
            parameters=rendered_parameters,
            schedule_id=schedule.id,
            schedule_fire_id=queued_fire.id,
            scheduled_for=metadata.scheduled_for,
            schedule_reason=metadata.reason,
            commit=False,
        )
        run = self.session.get(Run, created_run.id)
        if run is None:
            raise RuntimeError("Scheduled run creation did not return a persisted run")
        queued_fire = self.fire_repository.mark_queued(
            queued_fire,
            materialized_at=materialized_at,
            rendered_parameters=rendered_parameters,
        )
        return ScheduleQueuedRunResult(fire=queued_fire, run=run, created_run=True)

    def create_or_get_fire(
        self,
        metadata: ScheduleFireMetadata,
        *,
        status: FireStatus | str = FireStatus.PENDING,
        materialized_at: datetime | None = None,
        rendered_parameters: dict[str, Any] | None = None,
        skip_reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ScheduleFireRead:
        try:
            _ = self._get_schedule_model(metadata.schedule_id)
            fire = self.fire_repository.insert_idempotent(
                schedule_id=metadata.schedule_id,
                fire_key=metadata.fire_key,
                reason=_enum_value(metadata.reason),
                status=_enum_value(status),
                scheduled_for=metadata.scheduled_for,
                scheduled_local_date=metadata.scheduled_local_date,
                scheduled_local_time=metadata.scheduled_local_time,
                scheduled_local_datetime=metadata.scheduled_local_datetime,
                materialized_at=materialized_at,
                rendered_parameters=deepcopy(rendered_parameters or {}),
                skip_reason=skip_reason,
                error_code=error_code,
                error_message=error_message,
            )
            self.session.commit()
            self.session.refresh(fire)
            return self._to_fire_read(fire)
        except Exception:
            self.session.rollback()
            raise

    def mark_fire_queued(
        self,
        fire_id: int,
        *,
        materialized_at: datetime | None = None,
        rendered_parameters: dict[str, Any] | None = None,
    ) -> ScheduleFireRead:
        try:
            fire = self._get_fire_model(fire_id)
            queued = self.fire_repository.mark_queued(
                fire,
                materialized_at=materialized_at,
                rendered_parameters=(
                    deepcopy(rendered_parameters) if rendered_parameters is not None else None
                ),
            )
            self.session.commit()
            self.session.refresh(queued)
            return self._to_fire_read(queued)
        except Exception:
            self.session.rollback()
            raise

    def mark_fire_skipped(
        self,
        fire_id: int,
        *,
        skip_reason: str,
        materialized_at: datetime | None = None,
    ) -> ScheduleFireRead:
        try:
            fire = self._get_fire_model(fire_id)
            skipped = self.fire_repository.mark_skipped(
                fire,
                skip_reason=skip_reason,
                materialized_at=materialized_at,
            )
            self.session.commit()
            self.session.refresh(skipped)
            return self._to_fire_read(skipped)
        except Exception:
            self.session.rollback()
            raise

    def mark_fire_failed(
        self,
        fire_id: int,
        *,
        error_code: str,
        error_message: str,
        materialized_at: datetime | None = None,
    ) -> ScheduleFireRead:
        try:
            fire = self._get_fire_model(fire_id)
            failed = self.fire_repository.mark_failed(
                fire,
                error_code=error_code,
                error_message=error_message,
                materialized_at=materialized_at,
            )
            self.session.commit()
            self.session.refresh(failed)
            return self._to_fire_read(failed)
        except Exception:
            self.session.rollback()
            raise

    def _record_fire_failure_after_rollback(
        self,
        metadata: ScheduleFireMetadata,
        *,
        materialized_at: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        with self.session_factory() as session:
            schedule_service = self._fresh_schedule_service(session)
            schedule = schedule_service.schedule_repository.get_for_update(metadata.schedule_id)
            if schedule is None:
                session.rollback()
                return
            _ = schedule_service.insert_or_mark_fire_failed(
                metadata,
                materialized_at=materialized_at,
                error_code=error_code,
                error_message=error_message,
            )
            session.commit()

    def insert_or_mark_fire_failed(
        self,
        metadata: ScheduleFireMetadata,
        *,
        materialized_at: datetime,
        error_code: str,
        error_message: str,
    ) -> WorkflowPackageScheduleFire:
        fire = self.fire_repository.insert_idempotent(
            schedule_id=metadata.schedule_id,
            fire_key=metadata.fire_key,
            reason=metadata.reason.value,
            status=FireStatus.FAILED.value,
            scheduled_for=metadata.scheduled_for,
            scheduled_local_date=metadata.scheduled_local_date,
            scheduled_local_time=metadata.scheduled_local_time,
            scheduled_local_datetime=metadata.scheduled_local_datetime,
            materialized_at=materialized_at,
            error_code=error_code,
            error_message=error_message,
        )
        if fire.status == FireStatus.FAILED.value:
            return fire
        return self.fire_repository.mark_failed(
            fire,
            error_code=error_code,
            error_message=error_message,
            materialized_at=materialized_at,
        )

    def preview_due_schedule_input_render(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        fire_metadata: ScheduleFireMetadata,
        *,
        fire_id: int | None = None,
        materialized_at: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        last_run: ScheduledInputLastRunContext | None = None,
    ) -> ScheduledInputRenderPreview:
        return self.preview_schedule_input_render(
            package_id=due_schedule.package_id,
            package_key=due_schedule.package_key,
            workflow_key=due_schedule.workflow_key,
            schedule_id=due_schedule.id,
            schedule_name=due_schedule.name,
            timezone=due_schedule.timezone,
            input_template=due_schedule.input_template,
            template_vars=due_schedule.template_vars,
            fire_metadata=fire_metadata,
            fire_id=fire_id,
            materialized_at=materialized_at,
            window_start=window_start,
            window_end=window_end,
            last_run=last_run,
        )

    def render_due_schedule_input_or_raise(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        fire_metadata: ScheduleFireMetadata,
        *,
        fire_id: int | None = None,
        materialized_at: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        last_run: ScheduledInputLastRunContext | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_due_schedule_input_render(
            due_schedule,
            fire_metadata,
            fire_id=fire_id,
            materialized_at=materialized_at,
            window_start=window_start,
            window_end=window_end,
            last_run=last_run,
        )
        return require_scheduled_input_render_ready(preview)

    def preview_schedule_input_render(
        self,
        *,
        package_id: int,
        workflow_key: str,
        schedule_id: int | None,
        schedule_name: str,
        timezone: str,
        input_template: dict[str, Any],
        template_vars: dict[str, Any],
        fire_metadata: ScheduleFireMetadata,
        package_key: str | None = None,
        fire_id: int | None = None,
        materialized_at: datetime | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        last_run: ScheduledInputLastRunContext | None = None,
    ) -> ScheduledInputRenderPreview:
        package = self._get_package_model(package_id)
        template_context = build_scheduled_input_template_context(
            schedule_id=schedule_id,
            schedule_name=schedule_name,
            schedule_timezone=timezone,
            package_key=package_key or package.key,
            workflow_key=workflow_key,
            fire_id=fire_id,
            fire_reason=_enum_value(fire_metadata.reason),
            scheduled_for=fire_metadata.scheduled_for,
            scheduled_local_date=fire_metadata.scheduled_local_date,
            scheduled_local_time=fire_metadata.scheduled_local_time,
            scheduled_local_datetime=fire_metadata.scheduled_local_datetime,
            materialized_at=materialized_at,
            window_start=window_start,
            window_end=window_end,
            last_run=last_run,
            template_vars=template_vars,
        )
        input_schema = _workflow_input_schema(package, workflow_key)
        if input_schema is None:
            return ScheduledInputRenderPreview(
                template_context=template_context,
                rendered_parameters={},
                validation_errors=[
                    {
                        "field": "workflowKey",
                        "issue": "Schedule workflow is no longer present in the current package",
                        "code": SCHEDULE_RENDER_VALIDATION_FAILED,
                    }
                ],
            )
        return render_and_validate_scheduled_input_template(
            input_template=input_template,
            template_context=template_context,
            input_schema=input_schema,
            schema_compiler=self.schema_compiler,
        )

    def _update_fields(self, payload: ScheduleUpdate) -> dict[str, object]:
        fields: dict[str, object] = {}
        if "workflow_key" in payload.model_fields_set:
            fields["workflow_key"] = payload.workflow_key
        if "name" in payload.model_fields_set:
            fields["name"] = payload.name
        if "description" in payload.model_fields_set:
            fields["description"] = payload.description
        if "status" in payload.model_fields_set and payload.status is not None:
            fields["status"] = _enum_value(payload.status)
        if "timezone" in payload.model_fields_set:
            fields["timezone"] = payload.timezone
        if "recurrence" in payload.model_fields_set and payload.recurrence is not None:
            fields["recurrence"] = _recurrence_payload(payload.recurrence)
        if "starts_at" in payload.model_fields_set:
            fields["starts_at"] = payload.starts_at
        if "ends_at" in payload.model_fields_set:
            fields["ends_at"] = payload.ends_at
        if "overlap_policy" in payload.model_fields_set and payload.overlap_policy is not None:
            fields["overlap_policy"] = _enum_value(payload.overlap_policy)
        if "misfire_policy" in payload.model_fields_set and payload.misfire_policy is not None:
            fields["misfire_policy"] = _enum_value(payload.misfire_policy)
        if "misfire_grace_seconds" in payload.model_fields_set:
            fields["misfire_grace_seconds"] = payload.misfire_grace_seconds
        if "input_template" in payload.model_fields_set and payload.input_template is not None:
            fields["input_template"] = deepcopy(payload.input_template)
        if "template_vars" in payload.model_fields_set and payload.template_vars is not None:
            fields["template_vars"] = deepcopy(payload.template_vars)
        return fields

    def _initial_next_fire_at(self, payload: ScheduleCreate) -> datetime | None:
        return self._next_fire_at_for_values(
            status=_enum_value(payload.status),
            recurrence=_recurrence_payload(payload.recurrence),
            timezone_name=payload.timezone,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            anchor_at=utcnow(),
        )

    @staticmethod
    def _requires_next_fire_recompute(payload: ScheduleUpdate) -> bool:
        return bool(
            {
                "status",
                "timezone",
                "recurrence",
                "starts_at",
                "ends_at",
            }.intersection(payload.model_fields_set)
        )

    def _next_fire_at_for_update(
        self,
        schedule: WorkflowPackageSchedule,
        fields: dict[str, object],
    ) -> datetime | None:
        raw_recurrence = fields.get("recurrence", schedule.recurrence)
        recurrence = cast(dict[str, Any], raw_recurrence)
        starts_at = cast(datetime | None, fields.get("starts_at", schedule.starts_at))
        ends_at = cast(datetime | None, fields.get("ends_at", schedule.ends_at))
        return self._next_fire_at_for_values(
            status=str(fields.get("status", schedule.status)),
            recurrence=recurrence,
            timezone_name=str(fields.get("timezone", schedule.timezone)),
            starts_at=starts_at,
            ends_at=ends_at,
            anchor_at=schedule.created_at,
        )

    def _next_fire_at_for_values(
        self,
        *,
        status: str,
        recurrence: dict[str, Any],
        timezone_name: str,
        starts_at: datetime | None,
        ends_at: datetime | None,
        anchor_at: datetime,
    ) -> datetime | None:
        _ = status
        now = utcnow()
        compare_at = to_utc(starts_at) if starts_at and to_utc(starts_at) > now else now
        candidate = self._next_occurrence_at_or_after(
            recurrence,
            timezone_name=timezone_name,
            compare_at=compare_at,
            anchor_at=to_utc(starts_at or anchor_at),
        )
        if candidate is None:
            return None
        if ends_at is not None and candidate > to_utc(ends_at):
            return None
        return candidate

    @classmethod
    def occurrence_context_for_recurrence(
        cls,
        recurrence: ScheduleRecurrence | dict[str, Any],
        *,
        timezone_name: str,
        scheduled_for: datetime,
        ends_at: datetime | None = None,
    ) -> ScheduleOccurrenceContext:
        recurrence_payload = cls._recurrence_payload_for_calculation(recurrence)
        scheduled_for_utc = to_utc(scheduled_for)
        local_date, local_time, local_datetime = cls._scheduled_local_fields(
            scheduled_for_utc,
            timezone_name,
        )
        return ScheduleOccurrenceContext(
            scheduled_for=scheduled_for_utc,
            previous_scheduled_for=cls._previous_occurrence_for_values(
                recurrence_payload,
                timezone_name=timezone_name,
                scheduled_for=scheduled_for_utc,
            ),
            next_fire_at=cls._next_occurrence_after(
                recurrence_payload,
                timezone_name=timezone_name,
                after=scheduled_for_utc,
                ends_at=ends_at,
            ),
            scheduled_local_date=local_date,
            scheduled_local_time=local_time,
            scheduled_local_datetime=local_datetime,
        )

    @staticmethod
    def _recurrence_payload_for_calculation(
        recurrence: ScheduleRecurrence | dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(recurrence, dict):
            return recurrence
        return _recurrence_payload(recurrence)

    @classmethod
    def _next_occurrence_at_or_after(
        cls,
        recurrence: dict[str, Any],
        *,
        timezone_name: str,
        compare_at: datetime,
        anchor_at: datetime,
    ) -> datetime | None:
        compare_at_utc = to_utc(compare_at)
        recurrence_type = str(recurrence.get("type") or "")
        if recurrence_type == "interval":
            return cls._next_interval_occurrence(recurrence, compare_at_utc, anchor_at)
        if recurrence_type == "daily":
            return cls._next_daily_occurrence(recurrence, compare_at_utc, timezone_name)
        if recurrence_type == "weekly":
            return cls._next_weekly_occurrence(recurrence, compare_at_utc, timezone_name)
        if recurrence_type == "monthly":
            return cls._next_monthly_occurrence(recurrence, compare_at_utc, timezone_name)
        return None

    @classmethod
    def _next_occurrence_after(
        cls,
        recurrence: dict[str, Any],
        *,
        timezone_name: str,
        after: datetime,
        ends_at: datetime | None = None,
    ) -> datetime | None:
        after_utc = to_utc(after)
        recurrence_type = str(recurrence.get("type") or "")
        candidate: datetime | None
        if recurrence_type == "interval":
            candidate = after_utc + cls._interval_delta(recurrence)
        elif recurrence_type == "daily":
            candidate = cls._next_daily_after(recurrence, after_utc, timezone_name)
        elif recurrence_type == "weekly":
            candidate = cls._next_weekly_after(recurrence, after_utc, timezone_name)
        elif recurrence_type == "monthly":
            candidate = cls._next_monthly_after(recurrence, after_utc, timezone_name)
        else:
            return None
        if candidate is None:
            return None
        if ends_at is not None and candidate > to_utc(ends_at):
            return None
        return candidate

    @classmethod
    def _previous_occurrence_for_values(
        cls,
        recurrence: dict[str, Any],
        *,
        timezone_name: str,
        scheduled_for: datetime,
    ) -> datetime | None:
        scheduled_for_utc = to_utc(scheduled_for)
        if str(recurrence.get("type") or "") == "interval":
            return scheduled_for_utc - cls._interval_delta(recurrence)
        anchor = scheduled_for_utc - timedelta(days=370)
        previous: datetime | None = None
        candidate = cls._next_occurrence_after(
            recurrence,
            timezone_name=timezone_name,
            after=anchor,
        )
        while candidate is not None and candidate < scheduled_for_utc:
            previous = candidate
            candidate = cls._next_occurrence_after(
                recurrence,
                timezone_name=timezone_name,
                after=candidate,
            )
        return previous

    @classmethod
    def _next_interval_occurrence(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        anchor_at: datetime,
    ) -> datetime:
        delta = cls._interval_delta(recurrence)
        compare_at_utc = to_utc(compare_at)
        first = to_utc(anchor_at) + delta
        if first >= compare_at_utc:
            return first
        steps = int((compare_at_utc - first) // delta) + 1
        return first + (delta * steps)

    @staticmethod
    def _interval_delta(recurrence: dict[str, Any]) -> timedelta:
        every = int(recurrence.get("every") or 1)
        unit = str(recurrence.get("unit") or "minutes")
        if unit == "hours":
            return timedelta(hours=every)
        if unit == "days":
            return timedelta(days=every)
        return timedelta(minutes=every)

    @classmethod
    def _next_daily_occurrence(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_daily_occurrence_matching(
            recurrence,
            compare_at,
            timezone_name,
            inclusive=True,
        )

    @classmethod
    def _next_daily_after(
        cls,
        recurrence: dict[str, Any],
        after: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_daily_occurrence_matching(
            recurrence,
            after,
            timezone_name,
            inclusive=False,
        )

    @classmethod
    def _next_daily_occurrence_matching(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
        *,
        inclusive: bool,
    ) -> datetime | None:
        compare_at_utc = to_utc(compare_at)
        local_compare = compare_at_utc.astimezone(ZoneInfo(timezone_name))
        at_local_time = str(recurrence.get("atLocalTime") or "00:00")
        for offset_days in range(0, 3700):
            candidate_date = local_compare.date() + timedelta(days=offset_days)
            candidate = cls._local_candidate(candidate_date, at_local_time, timezone_name)
            if cls._candidate_matches(candidate, compare_at_utc, inclusive=inclusive):
                return candidate
        return None

    @classmethod
    def _next_weekly_occurrence(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_weekly_occurrence_matching(
            recurrence,
            compare_at,
            timezone_name,
            inclusive=True,
        )

    @classmethod
    def _next_weekly_after(
        cls,
        recurrence: dict[str, Any],
        after: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_weekly_occurrence_matching(
            recurrence,
            after,
            timezone_name,
            inclusive=False,
        )

    @classmethod
    def _next_weekly_occurrence_matching(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
        *,
        inclusive: bool,
    ) -> datetime | None:
        raw_days = cast(object, recurrence.get("daysOfWeek", []))
        day_values: list[object] = (
            cast(list[object], raw_days) if isinstance(raw_days, list) else []
        )
        allowed = {cls._weekday_index(day) for day in day_values if isinstance(day, str)}
        if not allowed:
            return None
        compare_at_utc = to_utc(compare_at)
        local_compare = compare_at_utc.astimezone(ZoneInfo(timezone_name))
        at_local_time = str(recurrence.get("atLocalTime") or "00:00")
        for offset_days in range(0, 3700):
            candidate_date = local_compare.date() + timedelta(days=offset_days)
            if candidate_date.weekday() not in allowed:
                continue
            candidate = cls._local_candidate(candidate_date, at_local_time, timezone_name)
            if cls._candidate_matches(candidate, compare_at_utc, inclusive=inclusive):
                return candidate
        return None

    @classmethod
    def _next_monthly_occurrence(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_monthly_occurrence_matching(
            recurrence,
            compare_at,
            timezone_name,
            inclusive=True,
        )

    @classmethod
    def _next_monthly_after(
        cls,
        recurrence: dict[str, Any],
        after: datetime,
        timezone_name: str,
    ) -> datetime | None:
        return cls._next_monthly_occurrence_matching(
            recurrence,
            after,
            timezone_name,
            inclusive=False,
        )

    @classmethod
    def _next_monthly_occurrence_matching(
        cls,
        recurrence: dict[str, Any],
        compare_at: datetime,
        timezone_name: str,
        *,
        inclusive: bool,
    ) -> datetime | None:
        raw_days = cast(object, recurrence.get("daysOfMonth", []))
        day_values: list[object] = (
            cast(list[object], raw_days) if isinstance(raw_days, list) else []
        )
        allowed = sorted(day for day in day_values if isinstance(day, int))
        if not allowed:
            return None
        compare_at_utc = to_utc(compare_at)
        local_compare = compare_at_utc.astimezone(ZoneInfo(timezone_name))
        at_local_time = str(recurrence.get("atLocalTime") or "00:00")
        year = local_compare.year
        month = local_compare.month
        for _ in range(0, 240):
            last_day = calendar.monthrange(year, month)[1]
            for day in allowed:
                if day > last_day:
                    continue
                candidate = cls._local_candidate(
                    datetime(year, month, day).date(),
                    at_local_time,
                    timezone_name,
                )
                if cls._candidate_matches(candidate, compare_at_utc, inclusive=inclusive):
                    return candidate
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return None

    @staticmethod
    def _candidate_matches(candidate: datetime, compare_at: datetime, *, inclusive: bool) -> bool:
        if inclusive:
            return candidate >= compare_at
        return candidate > compare_at

    @staticmethod
    def _weekday_index(value: str) -> int:
        return {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }[value]

    @staticmethod
    def _local_candidate(
        local_date: date,
        at_local_time: str,
        timezone_name: str,
    ) -> datetime:
        hour, minute = [int(part) for part in at_local_time.split(":", maxsplit=1)]
        candidate = datetime.combine(local_date, datetime.min.time()).replace(
            hour=hour,
            minute=minute,
            tzinfo=ZoneInfo(timezone_name),
        )
        return candidate.astimezone(UTC)

    def _window_start_for_recurrence(
        self,
        recurrence: ScheduleRecurrence | dict[str, Any],
        scheduled_for: datetime,
        *,
        timezone_name: str,
    ) -> datetime | None:
        return self.occurrence_context_for_recurrence(
            recurrence,
            timezone_name=timezone_name,
            scheduled_for=scheduled_for,
        ).previous_scheduled_for

    def _preview_fire_metadata(
        self,
        *,
        schedule_id: int,
        fire_key: str,
        reason: FireReason,
        scheduled_for: datetime,
        timezone_name: str,
    ) -> ScheduleFireMetadata:
        local_date, local_time, local_datetime = self._scheduled_local_fields(
            scheduled_for,
            timezone_name,
        )
        return ScheduleFireMetadata(
            schedule_id=schedule_id,
            fire_key=fire_key,
            reason=reason,
            scheduled_for=scheduled_for,
            scheduled_local_date=local_date,
            scheduled_local_time=local_time,
            scheduled_local_datetime=local_datetime,
        )

    @staticmethod
    def _scheduled_local_fields(
        scheduled_for: datetime,
        timezone_name: str,
    ) -> tuple[str, str, str]:
        local = scheduled_for.astimezone(ZoneInfo(timezone_name))
        return (
            local.date().isoformat(),
            local.strftime("%H:%M"),
            local.replace(tzinfo=None).isoformat(timespec="minutes"),
        )

    @staticmethod
    def _scheduled_fire_key(scheduled_for: datetime) -> str:
        return to_utc(scheduled_for).isoformat().replace("+00:00", "Z")

    @classmethod
    def _manual_fire_key(cls, scheduled_for: datetime, idempotency_key: str) -> str:
        return f"manual:{cls._scheduled_fire_key(scheduled_for)}:{idempotency_key}"

    def _delete_schedule_rows(self, schedule_id: int) -> None:
        schedule = self._get_schedule_model_for_update(schedule_id)
        fire_ids = self.fire_repository.list_ids_for_schedule(schedule.id)
        self._run_service().detach_runs_for_deleted_schedule(
            schedule=schedule,
            fire_ids=fire_ids,
            commit=False,
        )
        self.session.flush()
        self.schedule_repository.delete(schedule)
        self.session.flush()

    def _to_preview_read(
        self,
        schedule_id: int | None,
        scheduled_for: datetime | None,
        preview: ScheduledInputRenderPreview,
    ) -> SchedulePreviewRead:
        return SchedulePreviewRead.model_validate(
            {
                "scheduleId": schedule_id,
                "scheduledFor": scheduled_for,
                "templateContext": deepcopy(preview.template_context),
                "renderedParameters": deepcopy(preview.rendered_parameters),
                "validationErrors": self._validation_errors(preview.validation_errors),
                "ready": preview.ready,
            }
        )

    def _empty_preview(
        self,
        *,
        schedule_id: int,
        field: str,
        issue: str,
    ) -> SchedulePreviewRead:
        return SchedulePreviewRead.model_validate(
            {
                "scheduleId": schedule_id,
                "scheduledFor": None,
                "templateContext": {},
                "renderedParameters": {},
                "validationErrors": [ScheduleValidationError(field=field, issue=issue)],
                "ready": False,
            }
        )

    @staticmethod
    def _validation_errors(errors: Sequence[dict[str, Any]]) -> list[ScheduleValidationError]:
        return [
            ScheduleValidationError(
                field=str(error.get("field") or "inputTemplate"),
                issue=str(error.get("issue") or "Invalid scheduled input template"),
            )
            for error in errors
        ]

    def _to_run_now_read(
        self,
        schedule: WorkflowPackageSchedule,
        package: WorkflowPackage,
        fire: WorkflowPackageScheduleFire,
        run: Run,
    ) -> ScheduleRunNowRead:
        return ScheduleRunNowRead.model_validate(
            {
                "scheduleId": schedule.id,
                "fire": self._to_fire_read(fire, run=run),
                "run": ScheduleRunNowRunRead.model_validate(
                    {
                        "id": run.id,
                        "status": run.status,
                        "workflowPackageId": package.id,
                        "workflowPackageKey": package.key,
                        "workflowKey": schedule.workflow_key,
                        "createdAt": run.created_at,
                    }
                ),
            }
        )

    def _latest_terminal_run_context(self, schedule_id: int) -> ScheduledInputLastRunContext | None:
        latest_run = self.fire_repository.get_latest_terminal_run_for_schedule(schedule_id)
        if latest_run is None:
            return None
        return ScheduledInputLastRunContext(
            id=latest_run.id,
            status=latest_run.status,
            completed_at=latest_run.finished_at,
        )

    def _to_schedule_read(
        self,
        schedule: WorkflowPackageSchedule,
        *,
        package: WorkflowPackage | None = None,
    ) -> ScheduleRead:
        resolved_package = package or self._get_package_model(schedule.package_id)
        latest = self._latest_metadata(schedule.id)
        return ScheduleRead.model_validate(
            {
                "id": schedule.id,
                "packageId": schedule.package_id,
                "packageKey": resolved_package.key,
                "workflowKey": schedule.workflow_key,
                "name": schedule.name,
                "description": schedule.description,
                "status": schedule.status,
                "timezone": schedule.timezone,
                "recurrence": deepcopy(schedule.recurrence),
                "startsAt": schedule.starts_at,
                "endsAt": schedule.ends_at,
                "nextFireAt": schedule.next_fire_at,
                "overlapPolicy": schedule.overlap_policy,
                "misfirePolicy": schedule.misfire_policy,
                "misfireGraceSeconds": schedule.misfire_grace_seconds,
                "latestFireId": latest.fire_id,
                "latestRunId": latest.run_id,
                "latestStatus": latest.status,
                "createdAt": schedule.created_at,
                "updatedAt": schedule.updated_at,
            }
        )

    def _to_fire_read(
        self,
        fire: WorkflowPackageScheduleFire,
        *,
        run: Run | None = None,
    ) -> ScheduleFireRead:
        linked_run = run if run is not None else self.fire_repository.get_run_for_fire(fire.id)
        return ScheduleFireRead.model_validate(
            {
                "id": fire.id,
                "scheduleId": fire.schedule_id,
                "fireKey": fire.fire_key,
                "reason": fire.reason,
                "status": fire.status,
                "scheduledFor": fire.scheduled_for,
                "scheduledLocalDate": fire.scheduled_local_date,
                "scheduledLocalTime": fire.scheduled_local_time,
                "scheduledLocalDateTime": fire.scheduled_local_datetime,
                "materializedAt": fire.materialized_at,
                "runId": linked_run.id if linked_run is not None else None,
                "renderedParameters": deepcopy(fire.rendered_parameters),
                "skipReason": fire.skip_reason,
                "errorCode": fire.error_code,
                "errorMessage": fire.error_message,
                "createdAt": fire.created_at,
            }
        )

    def to_due_schedule(self, schedule: WorkflowPackageSchedule) -> DueWorkflowPackageSchedule:
        package = self._get_package_model(schedule.package_id)
        if schedule.next_fire_at is None:
            raise ValueError("Due schedule must have next_fire_at populated")
        return DueWorkflowPackageSchedule(
            id=schedule.id,
            package_id=schedule.package_id,
            package_key=package.key,
            workflow_key=schedule.workflow_key,
            name=schedule.name,
            timezone=schedule.timezone,
            recurrence=deepcopy(schedule.recurrence),
            next_fire_at=schedule.next_fire_at,
            overlap_policy=OverlapPolicy(schedule.overlap_policy),
            misfire_policy=MisfirePolicy(schedule.misfire_policy),
            misfire_grace_seconds=schedule.misfire_grace_seconds,
            input_template=deepcopy(schedule.input_template),
            template_vars=deepcopy(schedule.template_vars),
            ends_at=schedule.ends_at,
        )

    def _latest_metadata(self, schedule_id: int) -> ScheduleLatestMetadata:
        latest_fire = self.fire_repository.get_latest_for_schedule(schedule_id)
        latest_run = self.fire_repository.get_latest_run_for_schedule(schedule_id)
        return ScheduleLatestMetadata(
            fire_id=latest_fire.id if latest_fire is not None else None,
            run_id=latest_run.id if latest_run is not None else None,
            status=self._latest_status(latest_fire=latest_fire, latest_run=latest_run),
        )

    @staticmethod
    def _latest_status(
        *,
        latest_fire: WorkflowPackageScheduleFire | None,
        latest_run: Run | None,
    ) -> str | None:
        if latest_run is not None:
            return latest_run.status
        if latest_fire is not None:
            return latest_fire.status
        return None

    def _runs_by_fire_id(self, fire_ids: Sequence[int]) -> dict[int, Run]:
        runs = self.fire_repository.list_runs_for_fire_ids(fire_ids)
        return {int(run.schedule_fire_id): run for run in runs if run.schedule_fire_id is not None}

    def _validate_package_workflow_key(
        self,
        package: WorkflowPackage,
        workflow_key: str,
    ) -> None:
        if workflow_key in self._package_workflow_keys(package):
            return
        raise validation_error(
            "Schedule validation failed",
            [
                {
                    "field": "workflowKey",
                    "issue": (
                        f"Workflow key {workflow_key!r} is not present in workflow package "
                        f"{package.key!r}"
                    ),
                }
            ],
        )

    @staticmethod
    def _package_workflow_keys(package: WorkflowPackage) -> set[str]:
        compiled_plan = cast(Mapping[str, object], package.compiled_plan)
        raw_workflows = compiled_plan.get("workflows")
        if not isinstance(raw_workflows, list):
            return set()
        workflows = cast(list[object], raw_workflows)
        workflow_keys: set[str] = set()
        for raw_workflow in workflows:
            if not isinstance(raw_workflow, dict):
                continue
            workflow = cast(Mapping[str, object], raw_workflow)
            raw_key = workflow.get("key")
            if raw_key is not None:
                workflow_keys.add(str(raw_key))
        return workflow_keys

    def _get_schedule_model(self, schedule_id: int) -> WorkflowPackageSchedule:
        schedule = self.schedule_repository.get(schedule_id)
        if schedule is None:
            raise not_found_error("Schedule")
        return schedule

    def _get_schedule_model_for_update(self, schedule_id: int) -> WorkflowPackageSchedule:
        schedule = self.schedule_repository.get_for_update(schedule_id)
        if schedule is None:
            raise not_found_error("Schedule")
        return schedule

    def _get_fire_model(self, fire_id: int) -> WorkflowPackageScheduleFire:
        fire = self.fire_repository.get(fire_id)
        if fire is None:
            raise not_found_error("Schedule fire")
        return fire

    def _get_package_model(self, package_id: int) -> WorkflowPackage:
        package = self.workflow_package_repository.get(package_id)
        if package is None:
            raise not_found_error("Workflow package")
        return package


def _enum_value(value: Enum | str) -> str:
    if isinstance(value, Enum):
        return str(cast(object, value.value))
    return str(value)


def _recurrence_payload(value: ScheduleRecurrence) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True)


__all__ = [
    "DueWorkflowPackageSchedule",
    "ScheduleFireMetadata",
    "ScheduleLatestMetadata",
    "ScheduleOccurrenceContext",
    "ScheduleQueuedRunResult",
    "WorkflowPackageScheduleService",
]
