# pyright: reportExplicitAny=false
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, ensure_timezone

_LOCAL_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleStatus(str, Enum):  # noqa: UP042
    ENABLED = "enabled"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ScheduleWriteStatus(str, Enum):  # noqa: UP042
    ENABLED = "enabled"
    PAUSED = "paused"


class FireStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    QUEUED = "queued"
    SKIPPED = "skipped"
    FAILED = "failed"


class FireReason(str, Enum):  # noqa: UP042
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class OverlapPolicy(str, Enum):  # noqa: UP042
    SKIP = "skip"
    QUEUE = "queue"


class MisfirePolicy(str, Enum):  # noqa: UP042
    SKIP = "skip"
    CATCH_UP_ONE = "catchUpOne"


class RecurrenceType(str, Enum):  # noqa: UP042
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class IntervalUnit(str, Enum):  # noqa: UP042
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class DayOfWeek(str, Enum):  # noqa: UP042
    MONDAY = "mon"
    TUESDAY = "tue"
    WEDNESDAY = "wed"
    THURSDAY = "thu"
    FRIDAY = "fri"
    SATURDAY = "sat"
    SUNDAY = "sun"


ScheduleFireStatus = FireStatus
ScheduleFireReason = FireReason
ScheduleOverlapPolicy = OverlapPolicy
ScheduleMisfirePolicy = MisfirePolicy
ScheduleRecurrenceType = RecurrenceType
ScheduleIntervalUnit = IntervalUnit


def _validate_local_time(value: str) -> str:
    if _LOCAL_TIME_RE.fullmatch(value) is None:
        raise ValueError("Local time must use HH:MM 24-hour format")
    return value


def _json_object(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    items = cast(dict[object, object], value)
    return {str(key): item for key, item in items.items()}


def _optional_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


def _validate_timezone_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Timezone is required")
    try:
        _ = ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone must be a valid IANA timezone") from exc
    return normalized


class IntervalRecurrence(CamelModel):
    type: Literal["interval"] = "interval"
    every: int = Field(ge=1)
    unit: IntervalUnit


class DailyRecurrence(CamelModel):
    type: Literal["daily"] = "daily"
    at_local_time: str

    @field_validator("at_local_time")
    @classmethod
    def validate_at_local_time(cls, value: str) -> str:
        return _validate_local_time(value)


class WeeklyRecurrence(CamelModel):
    type: Literal["weekly"] = "weekly"
    days_of_week: list[DayOfWeek] = Field(min_length=1, max_length=7)
    at_local_time: str

    @field_validator("at_local_time")
    @classmethod
    def validate_at_local_time(cls, value: str) -> str:
        return _validate_local_time(value)

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, value: list[DayOfWeek]) -> list[DayOfWeek]:
        if len(set(value)) != len(value):
            raise ValueError("daysOfWeek values must be unique")
        return value


class MonthlyRecurrence(CamelModel):
    type: Literal["monthly"] = "monthly"
    days_of_month: list[int] = Field(min_length=1, max_length=31)
    at_local_time: str

    @field_validator("at_local_time")
    @classmethod
    def validate_at_local_time(cls, value: str) -> str:
        return _validate_local_time(value)

    @field_validator("days_of_month")
    @classmethod
    def validate_days_of_month(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 31 for day in value):
            raise ValueError("daysOfMonth values must be between 1 and 31")
        if len(set(value)) != len(value):
            raise ValueError("daysOfMonth values must be unique")
        return value


type ScheduleRecurrence = Annotated[
    IntervalRecurrence | DailyRecurrence | WeeklyRecurrence | MonthlyRecurrence,
    Field(discriminator="type"),
]


class ScheduleCreate(CamelModel):
    package_id: int
    workflow_key: str
    name: str
    description: str | None = None
    status: ScheduleWriteStatus = ScheduleWriteStatus.ENABLED
    timezone: str
    recurrence: ScheduleRecurrence
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    overlap_policy: OverlapPolicy = OverlapPolicy.SKIP
    misfire_policy: MisfirePolicy = MisfirePolicy.CATCH_UP_ONE
    misfire_grace_seconds: int = Field(default=86400, ge=0)
    input_template: dict[str, Any] = Field(default_factory=dict)
    template_vars: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workflow_key", "name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)

    @field_validator("input_template", "template_vars", mode="before")
    @classmethod
    def validate_json_objects(cls, value: object) -> dict[str, Any]:
        return _json_object(value, field_name="Schedule JSON field")


class ScheduleUpdate(CamelModel):
    name: str | None = None
    description: str | None = None
    status: ScheduleWriteStatus | None = None
    timezone: str | None = None
    recurrence: ScheduleRecurrence | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    overlap_policy: OverlapPolicy | None = None
    misfire_policy: MisfirePolicy | None = None
    misfire_grace_seconds: int | None = Field(default=None, ge=0)
    input_template: dict[str, Any] | None = None
    template_vars: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Field cannot be null")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Field cannot be null")
        return _validate_timezone_name(value)

    @field_validator(
        "status",
        "recurrence",
        "overlap_policy",
        "misfire_policy",
        "misfire_grace_seconds",
        mode="before",
    )
    @classmethod
    def reject_non_nullable_nulls(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)

    @field_validator("input_template", "template_vars", mode="before")
    @classmethod
    def validate_optional_json_objects(cls, value: object) -> dict[str, Any] | None:
        if value is None:
            raise ValueError("Field cannot be null")
        return _json_object(value, field_name="Schedule JSON field")


class ScheduleRead(CamelModel):
    id: int
    package_id: int
    package_key: str
    workflow_key: str
    name: str
    description: str | None = None
    status: ScheduleStatus
    timezone: str
    recurrence: ScheduleRecurrence
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    next_fire_at: datetime | None = None
    overlap_policy: OverlapPolicy
    misfire_policy: MisfirePolicy
    misfire_grace_seconds: int
    latest_fire_id: int | None = None
    latest_run_id: int | None = None
    latest_status: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "starts_at",
        "ends_at",
        "next_fire_at",
        "archived_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)


class ScheduleListRead(CamelModel):
    items: list[ScheduleRead]
    total_count: int
    limit: int
    offset: int


class ScheduleFireRead(CamelModel):
    id: int
    schedule_id: int
    fire_key: str
    reason: FireReason
    status: FireStatus
    scheduled_for: datetime
    scheduled_local_date: str | None = None
    scheduled_local_time: str | None = None
    scheduled_local_datetime: str | None = Field(default=None, alias="scheduledLocalDateTime")
    materialized_at: datetime | None = None
    run_id: int | None = None
    rendered_parameters: dict[str, Any] = Field(default_factory=dict)
    skip_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime

    @field_validator("scheduled_for", "materialized_at", "created_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)


class ScheduleFireListRead(CamelModel):
    items: list[ScheduleFireRead]
    total_count: int
    limit: int
    offset: int


class SchedulePreviewUnsavedRequest(CamelModel):
    package_id: int
    workflow_key: str
    timezone: str
    recurrence: ScheduleRecurrence
    scheduled_for: datetime
    template_vars: dict[str, Any] = Field(default_factory=dict)
    input_template: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workflow_key")
    @classmethod
    def validate_workflow_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return _validate_timezone_name(value)

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @field_validator("input_template", "template_vars", mode="before")
    @classmethod
    def validate_json_objects(cls, value: object) -> dict[str, Any]:
        return _json_object(value, field_name="Schedule preview JSON field")


class SchedulePreviewRequest(CamelModel):
    scheduled_for: datetime | None = None

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)


class ScheduleValidationError(CamelModel):
    field: str
    issue: str


class SchedulePreviewRead(CamelModel):
    schedule_id: int | None = None
    scheduled_for: datetime | None = None
    template_context: dict[str, Any] = Field(default_factory=dict)
    rendered_parameters: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[ScheduleValidationError] = Field(default_factory=list)
    ready: bool

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, value: datetime | None) -> datetime | None:
        return _optional_timestamp(value)


class ScheduleRunNowRequest(CamelModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    scheduled_for: datetime

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idempotencyKey is required")
        return normalized

    @field_validator("scheduled_for")
    @classmethod
    def validate_scheduled_for(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class ScheduleRunNowRunRead(CamelModel):
    id: int
    status: str
    workflow_package_id: int
    workflow_package_key: str
    workflow_key: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class ScheduleRunNowRead(CamelModel):
    schedule_id: int
    fire: ScheduleFireRead
    run: ScheduleRunNowRunRead


__all__ = [
    "DailyRecurrence",
    "DayOfWeek",
    "FireReason",
    "FireStatus",
    "IntervalRecurrence",
    "IntervalUnit",
    "MisfirePolicy",
    "MonthlyRecurrence",
    "OverlapPolicy",
    "RecurrenceType",
    "ScheduleCreate",
    "ScheduleFireListRead",
    "ScheduleFireRead",
    "ScheduleFireReason",
    "ScheduleFireStatus",
    "ScheduleIntervalUnit",
    "ScheduleListRead",
    "ScheduleMisfirePolicy",
    "ScheduleOverlapPolicy",
    "SchedulePreviewRead",
    "SchedulePreviewRequest",
    "SchedulePreviewUnsavedRequest",
    "ScheduleRead",
    "ScheduleRecurrence",
    "ScheduleRecurrenceType",
    "ScheduleRunNowRead",
    "ScheduleRunNowRequest",
    "ScheduleRunNowRunRead",
    "ScheduleStatus",
    "ScheduleUpdate",
    "ScheduleValidationError",
    "ScheduleWriteStatus",
    "WeeklyRecurrence",
]
