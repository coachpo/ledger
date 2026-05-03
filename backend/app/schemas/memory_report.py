from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

AGENT_MEMORY_REVIEW_TYPE: Final = "agent_memory"
AGENT_MEMORY_VERSION_GROUP: Final = "agent_memory/v1"

type AgentMemoryAction = Literal["buy", "hold", "sell"]
type AgentMemoryResolutionStatus = Literal["pending", "resolved", "expired"]
type AgentMemoryServiceResolutionStatus = Literal["resolved", "expired"]

AGENT_MEMORY_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "analysis.reviewType",
    "analysis.versionGroup",
    "analysis.ticker",
    "analysis.decision",
    "analysis.runId",
    "analysis.agentKey",
    "analysis.agentVersion",
)

AGENT_MEMORY_OPTIONAL_FIELDS: Final[tuple[str, ...]] = (
    "analysis.portfolioSlug",
    "analysis.horizonDays",
    "analysis.confidence",
    "analysis.decisionSummary",
    "analysis.benchmarkSymbol",
    "analysis.agentName",
    "analysis.workflowKey",
    "analysis.workflowVersion",
    "analysis.stepId",
    "analysis.slot",
    "analysis.traceId",
    "analysis.benchmarkReturn",
    "tags",
)

AGENT_MEMORY_IMMUTABLE_FIELDS: Final[tuple[str, ...]] = (
    "analysis.reviewType",
    "analysis.versionGroup",
    "analysis.ticker",
    "analysis.portfolioSlug",
    "analysis.horizonDays",
    "analysis.confidence",
    "analysis.decisionSummary",
    "analysis.benchmarkSymbol",
    "analysis.decision",
    "analysis.runId",
    "analysis.agentKey",
    "analysis.agentVersion",
    "analysis.agentName",
    "analysis.workflowKey",
    "analysis.workflowVersion",
    "analysis.stepId",
    "analysis.slot",
    "analysis.traceId",
)

AGENT_MEMORY_SERVICE_MUTABLE_FIELDS: Final[tuple[str, ...]] = (
    "analysis.resolvedStatus",
    "analysis.resolvedAt",
    "analysis.rawReturn",
    "analysis.benchmarkReturn",
    "analysis.alpha",
    "analysis.reflections",
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
    normalized = value.strip()
    return normalized or None


def _normalize_ticker(value: object) -> str:
    return _normalize_required_text(value, field_name="Ticker").upper()


class AgentMemoryDecisionText(CamelModel):
    action: AgentMemoryAction
    rationale: str = Field(min_length=1)
    risk_summary: str = Field(min_length=1)
    execution_plan: str = Field(min_length=1)

    @field_validator("rationale", "risk_summary", "execution_plan", mode="before")
    @classmethod
    def validate_decision_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Decision text")


class AgentMemoryModelInput(CamelModel):
    ticker: str = Field(min_length=1, max_length=32)
    decision: AgentMemoryDecisionText
    portfolio_slug: str | None = None
    horizon_days: int | None = Field(default=None, ge=1)
    confidence: str | None = None
    decision_summary: str | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=32)

    @field_validator("ticker", mode="before")
    @classmethod
    def validate_ticker(cls, value: object) -> str:
        return _normalize_ticker(value)

    @field_validator("portfolio_slug", "confidence", "decision_summary", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Agent memory input field")

    @field_validator("benchmark_symbol", mode="before")
    @classmethod
    def normalize_benchmark_symbol(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_ticker(value)


class AgentMemoryReportCreateMetadata(CamelModel):
    analysis: AgentMemoryModelInput


class AgentMemoryTrustedCreateContext(CamelModel):
    run_id: int = Field(ge=1)
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int = Field(ge=1)
    agent_name: str | None = None
    workflow_key: str | None = Field(default=None, max_length=120)
    workflow_version: int | None = Field(default=None, ge=1)
    step_id: str | None = Field(default=None, max_length=120)
    slot: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=255)

    @field_validator(
        "agent_key",
        "agent_name",
        "workflow_key",
        "step_id",
        "slot",
        "trace_id",
        mode="before",
    )
    @classmethod
    def normalize_context_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Trusted context field")


class AgentMemoryReflectionAppend(CamelModel):
    reflection: str = Field(min_length=1)
    reflected_at: datetime

    @field_validator("reflection", mode="before")
    @classmethod
    def validate_reflection(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Reflection")

    @field_validator("reflected_at")
    @classmethod
    def validate_reflected_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class AgentMemoryReflection(AgentMemoryReflectionAppend):
    pass


class AgentMemoryReportAnalysis(CamelModel):
    review_type: Literal["agent_memory"] = "agent_memory"
    version_group: Literal["agent_memory/v1"] = "agent_memory/v1"
    ticker: str = Field(min_length=1, max_length=32)
    decision: AgentMemoryDecisionText
    run_id: int = Field(ge=1)
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int = Field(ge=1)
    portfolio_slug: str | None = None
    horizon_days: int | None = Field(default=None, ge=1)
    confidence: str | None = None
    decision_summary: str | None = None
    benchmark_symbol: str | None = Field(default=None, max_length=32)
    agent_name: str | None = None
    workflow_key: str | None = Field(default=None, max_length=120)
    workflow_version: int | None = Field(default=None, ge=1)
    step_id: str | None = Field(default=None, max_length=120)
    slot: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=255)
    resolved_status: AgentMemoryResolutionStatus = "pending"
    resolved_at: datetime | None = None
    raw_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    alpha: Decimal | None = None
    reflections: list[AgentMemoryReflection] = Field(default_factory=list)

    @classmethod
    def pending(
        cls,
        *,
        model_input: AgentMemoryModelInput,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> AgentMemoryReportAnalysis:
        return cls(
            ticker=model_input.ticker,
            decision=model_input.decision,
            run_id=trusted_context.run_id,
            agent_key=trusted_context.agent_key,
            agent_version=trusted_context.agent_version,
            portfolio_slug=model_input.portfolio_slug,
            horizon_days=model_input.horizon_days,
            confidence=model_input.confidence,
            decision_summary=model_input.decision_summary,
            benchmark_symbol=model_input.benchmark_symbol,
            agent_name=trusted_context.agent_name,
            workflow_key=trusted_context.workflow_key,
            workflow_version=trusted_context.workflow_version,
            step_id=trusted_context.step_id,
            slot=trusted_context.slot,
            trace_id=trusted_context.trace_id,
        )

    @field_validator("ticker", "benchmark_symbol", mode="before")
    @classmethod
    def validate_ticker(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_ticker(value)

    @field_validator(
        "portfolio_slug",
        "confidence",
        "decision_summary",
        "agent_key",
        "agent_name",
        "workflow_key",
        "step_id",
        "slot",
        "trace_id",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Agent memory analysis field")

    @field_validator("resolved_at")
    @classmethod
    def validate_resolved_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        outcome_values = (
            self.resolved_at,
            self.raw_return,
            self.benchmark_return,
            self.alpha,
        )
        if self.resolved_status == "pending":
            if any(outcome_value is not None for outcome_value in outcome_values):
                raise ValueError("Pending memory cannot include resolved outcome fields")
            if self.reflections:
                raise ValueError("Pending memory cannot include reflections")
            return self

        if self.resolved_at is None:
            raise ValueError("resolvedAt is required once memory is no longer pending")

        if self.resolved_status == "resolved" and (self.raw_return is None or self.alpha is None):
            raise ValueError("rawReturn and alpha are required for resolved memory")

        return self


class AgentMemoryReportMetadata(CamelModel):
    analysis: AgentMemoryReportAnalysis
    tags: list[str] = Field(default_factory=lambda: [AGENT_MEMORY_REVIEW_TYPE])

    @classmethod
    def pending(
        cls,
        *,
        model_input: AgentMemoryModelInput,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> AgentMemoryReportMetadata:
        return cls(
            analysis=AgentMemoryReportAnalysis.pending(
                model_input=model_input,
                trusted_context=trusted_context,
            )
        )

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized_tags: list[str] = []
        for tag in value:
            normalized_tag = tag.strip()
            if normalized_tag:
                normalized_tags.append(normalized_tag)
        return normalized_tags


class AgentMemoryResolutionUpdate(CamelModel):
    resolved_status: AgentMemoryServiceResolutionStatus
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


class AgentMemoryServiceUpdate(CamelModel):
    resolution: AgentMemoryResolutionUpdate | None = None
    reflections: list[AgentMemoryReflectionAppend] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_update_payload(self) -> Self:
        if self.resolution is None and not self.reflections:
            raise ValueError("At least one service-owned memory update must be provided")
        return self


__all__ = [
    "AGENT_MEMORY_IMMUTABLE_FIELDS",
    "AGENT_MEMORY_OPTIONAL_FIELDS",
    "AGENT_MEMORY_REQUIRED_FIELDS",
    "AGENT_MEMORY_REVIEW_TYPE",
    "AGENT_MEMORY_SERVICE_MUTABLE_FIELDS",
    "AGENT_MEMORY_VERSION_GROUP",
    "AgentMemoryDecisionText",
    "AgentMemoryModelInput",
    "AgentMemoryReflection",
    "AgentMemoryReflectionAppend",
    "AgentMemoryReportAnalysis",
    "AgentMemoryReportCreateMetadata",
    "AgentMemoryReportMetadata",
    "AgentMemoryResolutionUpdate",
    "AgentMemoryServiceUpdate",
    "AgentMemoryTrustedCreateContext",
]
