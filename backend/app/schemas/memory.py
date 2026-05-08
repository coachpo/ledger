from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Final, Literal, Self, cast

from fastapi import status
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.core.errors import ApiError
from app.core.formatting import normalize_symbol
from app.schemas.common import CamelModel, ensure_timezone

MEMORY_ID_PREFIX: Final = "mem_"
_MEMORY_ID_RE: Final = re.compile(r"^mem_(?P<report_id>[1-9][0-9]*)$")

INVALID_MEMORY_ID_CODE: Final = "invalid_memory_id"
MEMORY_NOT_FOUND_CODE: Final = "memory_not_found"

MemoryProjection = Literal[
    "model-visible",
    "api-visible",
    "ui-visible",
    "report-route-visible",
]

MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS: Final[frozenset[str]] = frozenset(
    {"auditLinks", "reportId", "reportSlug", "reportName", "url", "downloadUrl"}
)

MEMORY_PROJECTION_MATRIX: Final[dict[MemoryProjection, tuple[str, ...]]] = {
    "model-visible": (
        "memoryId",
        "status",
        "action",
        "createdAt",
        "provenance",
        "warnings",
        "text",
        "outcome",
        "reflections",
    ),
    "api-visible": ("memoryId", "status", "provenance", "auditLinks"),
    "ui-visible": ("memoryId", "status", "summary", "provenance", "auditLinks"),
    "report-route-visible": ("auditLinks",),
}


def format_report_backed_memory_id(report_id: int) -> str:
    if report_id < 1:
        raise invalid_memory_id_error()
    return f"{MEMORY_ID_PREFIX}{report_id}"


def parse_report_backed_memory_id(memory_id: str) -> int:
    match = _MEMORY_ID_RE.fullmatch(memory_id.strip())
    if match is None:
        raise invalid_memory_id_error()
    return int(match.group("report_id"))


def invalid_memory_id_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=INVALID_MEMORY_ID_CODE,
        message="Invalid memory id",
    )


def memory_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=MEMORY_NOT_FOUND_CODE,
        message="Memory not found",
    )


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip() or None


def _normalize_ticker(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Ticker must be a string")
    normalized = normalize_symbol(value)
    if not normalized:
        raise ValueError("Ticker is required")
    return normalized


class MemoryLifecycleStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class MemoryId(CamelModel):
    value: str

    @classmethod
    def from_report_id(cls, report_id: int) -> MemoryId:
        return cls(value=format_report_backed_memory_id(report_id))

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("memoryId must be a string")
        normalized = value.strip()
        _ = parse_report_backed_memory_id(normalized)
        return normalized

    def report_id_for_report_backed_store(self) -> int:
        return parse_report_backed_memory_id(self.value)


class MemoryDecision(CamelModel):
    action: Literal["buy", "hold", "sell"]
    rationale: str = Field(min_length=1)
    risk_summary: str = Field(min_length=1)
    execution_plan: str = Field(min_length=1)

    @field_validator("rationale", "risk_summary", "execution_plan", mode="before")
    @classmethod
    def validate_decision_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Decision text")


class MemoryOutcome(CamelModel):
    resolved_status: Literal["resolved", "expired"]
    resolved_at: datetime
    raw_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    alpha: Decimal | None = None

    @field_validator("resolved_at")
    @classmethod
    def validate_resolved_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_resolution_fields(self) -> Self:
        if self.resolved_status == "resolved" and (self.raw_return is None or self.alpha is None):
            raise ValueError("rawReturn and alpha are required for resolved memory")
        return self


class MemoryReflection(CamelModel):
    reflection: str = Field(min_length=1)
    reflected_at: datetime
    source: str | None = None

    @field_validator("reflection", mode="before")
    @classmethod
    def validate_reflection(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Reflection")

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Reflection source")

    @field_validator("reflected_at")
    @classmethod
    def validate_reflected_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryProvenance(CamelModel):
    run_id: int = Field(ge=1)
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int = Field(ge=1)
    agent_name: str | None = None
    workflow_key: str | None = Field(default=None, max_length=120)
    workflow_version: int | None = Field(default=None, ge=1)
    step_id: str | None = Field(default=None, max_length=120)
    slot: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=255)
    created_by_type: Literal["agent"] = "agent"

    @field_validator("agent_key", mode="before")
    @classmethod
    def validate_agent_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="agentKey")

    @field_validator("agent_name", "workflow_key", "step_id", "slot", "trace_id", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Provenance field")


class MemoryAuditReportLink(CamelModel):
    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    download_url: str = Field(min_length=1)

    @field_validator("slug", "name", "url", "download_url", mode="before")
    @classmethod
    def validate_link_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Report audit link field")


class MemoryAuditLinks(CamelModel):
    report: MemoryAuditReportLink | None = None


class _MemoryProjectionMixin(CamelModel):
    @model_serializer(mode="wrap")
    def serialize_without_empty_audit_links(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = cast(dict[str, object], handler(self))
        if payload.get("auditLinks") is None:
            _ = payload.pop("auditLinks", None)
        if payload.get("audit_links") is None:
            _ = payload.pop("audit_links", None)
        return payload

    def model_visible_dump(self) -> dict[str, object]:
        return cast(
            dict[str, object],
            self.model_dump(
                mode="json",
                by_alias=True,
                exclude={"audit_links"},
                exclude_none=True,
            ),
        )

    def dump_for_projection(self, projection: MemoryProjection) -> dict[str, object]:
        if projection == "model-visible":
            return self.model_visible_dump()
        return cast(
            dict[str, object],
            self.model_dump(mode="json", by_alias=True, exclude_none=True),
        )


class MemoryEntryRead(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1)
    status: MemoryLifecycleStatus
    ticker: str = Field(min_length=1, max_length=32)
    decision: MemoryDecision
    provenance: MemoryProvenance
    created_at: datetime
    portfolio_slug: str | None = None
    horizon_days: int | None = Field(default=None, ge=1)
    confidence: str | None = None
    decision_summary: str | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=32)
    outcome: MemoryOutcome | None = None
    reflections: list[MemoryReflection] = Field(default_factory=list)
    audit_links: MemoryAuditLinks | None = None
    updated_at: datetime | None = None

    @field_validator("memory_id", mode="before")
    @classmethod
    def validate_memory_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("memoryId must be a string")
        normalized = value.strip()
        _ = parse_report_backed_memory_id(normalized)
        return normalized

    @field_validator("ticker", "benchmark_symbol", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_ticker(value)

    @field_validator("portfolio_slug", "confidence", "decision_summary", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Memory entry field")

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.status == MemoryLifecycleStatus.PENDING:
            if self.outcome is not None:
                raise ValueError("Pending memory cannot include resolved outcome fields")
            if self.reflections:
                raise ValueError("Pending memory cannot include reflections")
            return self
        if self.outcome is None:
            raise ValueError("outcome is required once memory is no longer pending")
        if self.outcome.resolved_status != self.status.value:
            raise ValueError("outcome.resolvedStatus must match memory status")
        return self


class MemoryWriteRequest(CamelModel):
    ticker: str = Field(min_length=1, max_length=32)
    decision: MemoryDecision
    provenance: MemoryProvenance
    portfolio_slug: str | None = None
    horizon_days: int | None = Field(default=None, ge=1)
    confidence: str | None = None
    decision_summary: str | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=32)

    @field_validator("ticker", "benchmark_symbol", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_ticker(value)

    @field_validator("portfolio_slug", "confidence", "decision_summary", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Memory write request field")


class MemoryWriteResult(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1)
    status: MemoryLifecycleStatus
    action: Literal["created", "existing"]
    created_at: datetime
    provenance: MemoryProvenance
    audit_links: MemoryAuditLinks | None = None
    warnings: list[dict[str, object]] = Field(default_factory=list)

    @field_validator("memory_id", mode="before")
    @classmethod
    def validate_memory_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("memoryId must be a string")
        normalized = value.strip()
        _ = parse_report_backed_memory_id(normalized)
        return normalized

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryQuery(CamelModel):
    ticker: str | None = Field(default=None, max_length=32)
    portfolio_slug: str | None = None
    agent_key: str | None = Field(default=None, max_length=120)
    workflow_key: str | None = Field(default=None, max_length=120)
    status: MemoryLifecycleStatus | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1)
    offset: int = Field(default=0, ge=0)
    max_characters: int | None = Field(default=None, ge=1)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_ticker(value)

    @field_validator("portfolio_slug", "agent_key", "workflow_key", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Memory query field")

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: object) -> object:
        if value is None:
            return []
        return value


class MemoryPromptSnippet(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    provenance: MemoryProvenance
    outcome: MemoryOutcome
    reflections: list[MemoryReflection] = Field(default_factory=list)

    @field_validator("memory_id", mode="before")
    @classmethod
    def validate_memory_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("memoryId must be a string")
        normalized = value.strip()
        _ = parse_report_backed_memory_id(normalized)
        return normalized

    @field_validator("text", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Prompt snippet text")


class MemoryArtifactRead(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1)
    status: MemoryLifecycleStatus
    summary: str = Field(min_length=1)
    provenance: MemoryProvenance
    created_at: datetime
    audit_links: MemoryAuditLinks | None = None
    source_graph_metadata: dict[str, object] | None = None

    @field_validator("memory_id", mode="before")
    @classmethod
    def validate_memory_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("memoryId must be a string")
        normalized = value.strip()
        _ = parse_report_backed_memory_id(normalized)
        return normalized

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory artifact summary")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


__all__ = [
    "INVALID_MEMORY_ID_CODE",
    "MEMORY_ID_PREFIX",
    "MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS",
    "MEMORY_NOT_FOUND_CODE",
    "MEMORY_PROJECTION_MATRIX",
    "MemoryArtifactRead",
    "MemoryAuditLinks",
    "MemoryAuditReportLink",
    "MemoryDecision",
    "MemoryEntryRead",
    "MemoryId",
    "MemoryLifecycleStatus",
    "MemoryOutcome",
    "MemoryPromptSnippet",
    "MemoryProjection",
    "MemoryProvenance",
    "MemoryQuery",
    "MemoryReflection",
    "MemoryWriteRequest",
    "MemoryWriteResult",
    "format_report_backed_memory_id",
    "invalid_memory_id_error",
    "memory_not_found_error",
    "parse_report_backed_memory_id",
]
