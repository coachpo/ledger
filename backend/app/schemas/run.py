from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, ensure_timezone


class RunStatus(str, Enum):  # noqa: UP042
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
    workflow_id: int
    workflow_key: str
    workflow_version: int = Field(ge=1)
    trace_id: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RunListItemRead(CamelModel):
    id: int
    workflow_id: int
    workflow_key: str
    workflow_version: int = Field(ge=1)
    status: RunStatus
    total_tokens: int = Field(ge=0)
    total_cost_usd: Decimal = Field(ge=Decimal("0"))
    trace_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

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
    workflow_id: int
    workflow_key: str
    workflow_version: int = Field(ge=1)
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
]
