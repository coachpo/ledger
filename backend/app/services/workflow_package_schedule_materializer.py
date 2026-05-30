# pyright: reportExplicitAny=false
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.core.formatting import to_utc, utcnow
from app.db.engine import get_session_factory
from app.models.workflow_package_schedule import (
    WorkflowPackageSchedule,
    WorkflowPackageScheduleFire,
)
from app.schemas.schedule import FireReason, FireStatus, MisfirePolicy, OverlapPolicy
from app.services.run_service import RunService
from app.services.workflow_package_schedule_inputs import ScheduledInputLastRunContext
from app.services.workflow_package_schedule_service import (
    DueWorkflowPackageSchedule,
    ScheduleFireMetadata,
    WorkflowPackageScheduleService,
)

logger = logging.getLogger(__name__)

_MISFIRE_SKIP_REASON = "schedule_misfire_skipped"
_OVERLAP_SKIP_REASON = "schedule_overlap_active"


@dataclass(frozen=True)
class ScheduleOccurrence:
    scheduled_for: datetime
    previous_scheduled_for: datetime | None
    next_fire_at: datetime | None
    fire_key: str
    scheduled_local_date: str
    scheduled_local_time: str
    scheduled_local_datetime: str


@dataclass(frozen=True)
class ScheduleMaterializationResult:
    processed_count: int = 0
    queued_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0

    @property
    def changed_count(self) -> int:
        return self.queued_count + self.skipped_count + self.failed_count


@dataclass(frozen=True)
class _ScheduleMaterializationDecision:
    occurrence: ScheduleOccurrence
    skip_reason: str | None = None


class WorkflowPackageScheduleMaterializer:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        *,
        batch_size: int = 25,
    ) -> None:
        self.session_factory: sessionmaker[Session] = session_factory or get_session_factory()
        self.batch_size: int = batch_size

    def materialize_due(self, *, now: datetime | None = None) -> ScheduleMaterializationResult:
        materialized_at = to_utc(now or utcnow())
        with self.session_factory() as session:
            schedule_service = WorkflowPackageScheduleService(session)
            due_schedules = schedule_service.list_due_schedules(
                now=materialized_at,
                limit=self.batch_size,
                lock_rows=True,
            )
        result = ScheduleMaterializationResult()
        for due_schedule in due_schedules:
            schedule_result = self._materialize_schedule(
                due_schedule,
                materialized_at=materialized_at,
            )
            result = ScheduleMaterializationResult(
                processed_count=result.processed_count + schedule_result.processed_count,
                queued_count=result.queued_count + schedule_result.queued_count,
                skipped_count=result.skipped_count + schedule_result.skipped_count,
                failed_count=result.failed_count + schedule_result.failed_count,
            )
        return result

    def _materialize_schedule(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        *,
        materialized_at: datetime,
    ) -> ScheduleMaterializationResult:
        try:
            with self.session_factory() as session:
                schedule_service = WorkflowPackageScheduleService(session)
                locked_schedule = schedule_service.schedule_repository.get_for_update(
                    due_schedule.id
                )
                if locked_schedule is None or locked_schedule.next_fire_at is None:
                    session.rollback()
                    return ScheduleMaterializationResult()
                if (
                    locked_schedule.status != "enabled"
                    or locked_schedule.next_fire_at > materialized_at
                ):
                    session.rollback()
                    return ScheduleMaterializationResult()

                locked_due = schedule_service._to_due_schedule(locked_schedule)
                decision = self._materialization_decision(locked_due, now=materialized_at)
                metadata = self._fire_metadata(locked_due, decision.occurrence)
                fire = self._insert_fire(
                    schedule_service,
                    metadata,
                    materialized_at=materialized_at,
                )
                existing_run = schedule_service.fire_repository.get_run_for_fire(fire.id)
                if existing_run is not None or fire.status == FireStatus.QUEUED.value:
                    self._advance_schedule(
                        schedule_service,
                        locked_schedule,
                        decision.occurrence.next_fire_at,
                    )
                    session.commit()
                    return ScheduleMaterializationResult(processed_count=1)
                if fire.status in {FireStatus.SKIPPED.value, FireStatus.FAILED.value}:
                    self._advance_schedule(
                        schedule_service,
                        locked_schedule,
                        decision.occurrence.next_fire_at,
                    )
                    session.commit()
                    return ScheduleMaterializationResult(processed_count=1)

                if decision.skip_reason is not None:
                    schedule_service.fire_repository.mark_skipped(
                        fire,
                        skip_reason=decision.skip_reason,
                        materialized_at=materialized_at,
                    )
                    self._advance_schedule(
                        schedule_service,
                        locked_schedule,
                        decision.occurrence.next_fire_at,
                    )
                    session.commit()
                    return ScheduleMaterializationResult(processed_count=1, skipped_count=1)
                if self._should_skip_for_overlap(schedule_service, locked_due):
                    schedule_service.fire_repository.mark_skipped(
                        fire,
                        skip_reason=_OVERLAP_SKIP_REASON,
                        materialized_at=materialized_at,
                    )
                    self._advance_schedule(
                        schedule_service,
                        locked_schedule,
                        decision.occurrence.next_fire_at,
                    )
                    session.commit()
                    return ScheduleMaterializationResult(processed_count=1, skipped_count=1)

                last_run = self._latest_terminal_run_context(schedule_service, locked_due.id)
                rendered_parameters = schedule_service.render_due_schedule_input_or_raise(
                    locked_due,
                    metadata,
                    fire_id=fire.id,
                    materialized_at=materialized_at,
                    window_start=decision.occurrence.previous_scheduled_for,
                    window_end=decision.occurrence.scheduled_for,
                    last_run=last_run,
                )
                run = RunService(
                    session,
                    self.session_factory,
                ).create_scheduled_workflow_package_run(
                    package_id=locked_due.package_id,
                    workflow_key=locked_due.workflow_key,
                    parameters=rendered_parameters,
                    schedule_id=locked_due.id,
                    schedule_fire_id=fire.id,
                    scheduled_for=decision.occurrence.scheduled_for,
                    schedule_reason=metadata.reason,
                    commit=False,
                )
                schedule_service.fire_repository.mark_queued(
                    fire,
                    materialized_at=materialized_at,
                    rendered_parameters=rendered_parameters,
                )
                self._advance_schedule(
                    schedule_service,
                    locked_schedule,
                    decision.occurrence.next_fire_at,
                )
                session.commit()
                logger.info(
                    "Materialized schedule %d fire %s into run %d",
                    locked_due.id,
                    metadata.fire_key,
                    run.id,
                )
                return ScheduleMaterializationResult(processed_count=1, queued_count=1)
        except ApiError as exc:
            return self._record_materialization_failure(
                due_schedule,
                materialized_at=materialized_at,
                error_code=exc.code,
                error_message=exc.message,
            )
        except Exception:
            logger.exception("Failed to materialize schedule %d", due_schedule.id)
            return self._record_materialization_failure(
                due_schedule,
                materialized_at=materialized_at,
                error_code="schedule_materialization_failed",
                error_message="Schedule materialization failed",
            )

    def _record_materialization_failure(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        *,
        materialized_at: datetime,
        error_code: str,
        error_message: str,
    ) -> ScheduleMaterializationResult:
        with self.session_factory() as session:
            schedule_service = WorkflowPackageScheduleService(session)
            locked_schedule = schedule_service.schedule_repository.get_for_update(due_schedule.id)
            if locked_schedule is None or locked_schedule.next_fire_at is None:
                session.rollback()
                return ScheduleMaterializationResult()
            locked_due = schedule_service._to_due_schedule(locked_schedule)
            decision = self._materialization_decision(locked_due, now=materialized_at)
            fire = self._insert_fire(
                schedule_service,
                self._fire_metadata(locked_due, decision.occurrence),
                materialized_at=materialized_at,
                status=FireStatus.FAILED,
                error_code=error_code,
                error_message=error_message,
            )
            if fire.status != FireStatus.FAILED.value:
                schedule_service.fire_repository.mark_failed(
                    fire,
                    error_code=error_code,
                    error_message=error_message,
                    materialized_at=materialized_at,
                )
            self._advance_schedule(
                schedule_service,
                locked_schedule,
                decision.occurrence.next_fire_at,
            )
            session.commit()
        return ScheduleMaterializationResult(processed_count=1, failed_count=1)

    def _materialization_decision(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        *,
        now: datetime,
    ) -> _ScheduleMaterializationDecision:
        missed = self._due_occurrences(due_schedule, now=now)
        if not missed:
            occurrence = self._occurrence_for(due_schedule, due_schedule.next_fire_at)
            return _ScheduleMaterializationDecision(occurrence=occurrence)
        if due_schedule.misfire_policy == MisfirePolicy.SKIP:
            return _ScheduleMaterializationDecision(
                occurrence=missed[-1],
                skip_reason=_MISFIRE_SKIP_REASON,
            )
        grace_start = now - timedelta(seconds=due_schedule.misfire_grace_seconds)
        eligible = [item for item in missed if item.scheduled_for >= grace_start]
        if not eligible:
            return _ScheduleMaterializationDecision(
                occurrence=missed[-1],
                skip_reason=_MISFIRE_SKIP_REASON,
            )
        return _ScheduleMaterializationDecision(occurrence=eligible[-1])

    def _due_occurrences(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        *,
        now: datetime,
    ) -> list[ScheduleOccurrence]:
        occurrences: list[ScheduleOccurrence] = []
        current = self._occurrence_for(due_schedule, due_schedule.next_fire_at)
        while current.scheduled_for <= now:
            occurrences.append(current)
            if current.next_fire_at is None:
                break
            current = self._occurrence_for(due_schedule, current.next_fire_at)
        return occurrences

    def _occurrence_for(
        self,
        due_schedule: DueWorkflowPackageSchedule,
        scheduled_for: datetime,
    ) -> ScheduleOccurrence:
        context = WorkflowPackageScheduleService.occurrence_context_for_recurrence(
            due_schedule.recurrence,
            timezone_name=due_schedule.timezone,
            scheduled_for=scheduled_for,
            ends_at=due_schedule.ends_at,
        )
        return ScheduleOccurrence(
            scheduled_for=context.scheduled_for,
            previous_scheduled_for=context.previous_scheduled_for,
            next_fire_at=context.next_fire_at,
            fire_key=self._fire_key(context.scheduled_for),
            scheduled_local_date=context.scheduled_local_date,
            scheduled_local_time=context.scheduled_local_time,
            scheduled_local_datetime=context.scheduled_local_datetime,
        )

    def _insert_fire(
        self,
        schedule_service: WorkflowPackageScheduleService,
        metadata: ScheduleFireMetadata,
        *,
        materialized_at: datetime,
        status: FireStatus = FireStatus.PENDING,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowPackageScheduleFire:
        return schedule_service.fire_repository.insert_idempotent(
            schedule_id=metadata.schedule_id,
            fire_key=metadata.fire_key,
            reason=metadata.reason.value,
            status=status.value,
            scheduled_for=metadata.scheduled_for,
            scheduled_local_date=metadata.scheduled_local_date,
            scheduled_local_time=metadata.scheduled_local_time,
            scheduled_local_datetime=metadata.scheduled_local_datetime,
            materialized_at=materialized_at,
            error_code=error_code,
            error_message=error_message,
        )

    @staticmethod
    def _fire_metadata(
        due_schedule: DueWorkflowPackageSchedule,
        occurrence: ScheduleOccurrence,
    ) -> ScheduleFireMetadata:
        return ScheduleFireMetadata(
            schedule_id=due_schedule.id,
            fire_key=occurrence.fire_key,
            reason=FireReason.SCHEDULED,
            scheduled_for=occurrence.scheduled_for,
            scheduled_local_date=occurrence.scheduled_local_date,
            scheduled_local_time=occurrence.scheduled_local_time,
            scheduled_local_datetime=occurrence.scheduled_local_datetime,
        )

    @staticmethod
    def _fire_key(scheduled_for: datetime) -> str:
        return to_utc(scheduled_for).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _advance_schedule(
        schedule_service: WorkflowPackageScheduleService,
        schedule: WorkflowPackageSchedule,
        next_fire_at: datetime | None,
    ) -> None:
        schedule_service.schedule_repository.update_schedule(
            schedule,
            next_fire_at=next_fire_at,
        )
        schedule_service.session.flush()

    @staticmethod
    def _should_skip_for_overlap(
        schedule_service: WorkflowPackageScheduleService,
        due_schedule: DueWorkflowPackageSchedule,
    ) -> bool:
        if due_schedule.overlap_policy == OverlapPolicy.QUEUE:
            return False
        return schedule_service.fire_repository.has_active_run_for_schedule(due_schedule.id)

    @staticmethod
    def _latest_terminal_run_context(
        schedule_service: WorkflowPackageScheduleService,
        schedule_id: int,
    ) -> ScheduledInputLastRunContext | None:
        latest_run = schedule_service.fire_repository.get_latest_terminal_run_for_schedule(
            schedule_id
        )
        if latest_run is None:
            return None
        return ScheduledInputLastRunContext(
            id=latest_run.id,
            status=latest_run.status,
            completed_at=latest_run.finished_at,
        )


__all__ = [
    "ScheduleMaterializationResult",
    "ScheduleOccurrence",
    "WorkflowPackageScheduleMaterializer",
]
