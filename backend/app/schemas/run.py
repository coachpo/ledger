from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone


class RunStatus(str, Enum):  # noqa: UP042
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunTargetKind(str, Enum):  # noqa: UP042
    AGENT = "agent"
    WORKFLOW = "workflow"


def _coerce_legacy_target_identity(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    data = dict(value)
    legacy_keys = (
        "workflowId",
        "workflowKey",
        "workflowVersion",
        "workflow_id",
        "workflow_key",
        "workflow_version",
    )
    has_legacy_identity = any(legacy_key in data for legacy_key in legacy_keys)
    legacy_pairs = (
        ("workflowId", "targetId"),
        ("workflowKey", "targetKey"),
        ("workflowVersion", "targetVersion"),
        ("workflow_id", "target_id"),
        ("workflow_key", "target_key"),
        ("workflow_version", "target_version"),
    )
    for legacy_key, target_key in legacy_pairs:
        if target_key not in data and legacy_key in data:
            data[target_key] = data[legacy_key]
        data.pop(legacy_key, None)

    has_target_kind = "targetKind" in data or "target_kind" in data
    if not has_target_kind and has_legacy_identity:
        data["targetKind"] = RunTargetKind.WORKFLOW.value
    return data


class RunAgentErrorRead(CamelModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class RunStepAgentRead(CamelModel):
    slot: str
    agent_id: int
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int
    output_schema_version: int = Field(ge=1)
    resolved_input: dict[str, Any] = Field(default_factory=dict)
    output: Any | None = None
    error: RunAgentErrorRead | None = None
    status: RunStatus
    tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    duration_ms: int | None = Field(default=None, ge=0)
    trace_span_id: str | None = None


class RunCreatedRead(CamelModel):
    id: int
    status: RunStatus
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    target_version: int = Field(ge=1)
    trace_id: str | None = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RunListItemRead(CamelModel):
    id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    target_version: int = Field(ge=1)
    status: RunStatus
    total_tokens: int = Field(ge=0)
    total_cost_usd: Decimal = Field(ge=Decimal("0"))
    trace_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunListRead(CamelModel):
    items: list[RunListItemRead]


class RunRead(CamelModel):
    id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    target_version: int = Field(ge=1)
    input: dict[str, Any]
    per_step_outputs: dict[str, list[RunStepAgentRead]]
    final_output: Any | None = None
    status: RunStatus
    total_tokens: int = Field(ge=0)
    total_cost_usd: Decimal = Field(ge=Decimal("0"))
    trace_id: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @field_validator("started_at", "finished_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


__all__ = [
    "RunAgentErrorRead",
    "RunCreatedRead",
    "RunListItemRead",
    "RunListRead",
    "RunRead",
    "RunStatus",
    "RunStepAgentRead",
    "RunTargetKind",
]
