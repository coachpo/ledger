from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, Self

from pydantic import Field, field_validator, model_validator
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import normalize_symbol
from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from app.schemas.memory import MemoryLifecycleStatus, MemoryProvenance, MemoryWriteResult
from app.services.quote_provider import QuoteProvider

if TYPE_CHECKING:
    from app.services.social_sentiment_provider import SocialSentimentSourceAdapter


class RuntimeToolError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.details: list[dict[str, object]] = list(details or [])


@dataclass(frozen=True)
class RuntimeToolContext:
    session_factory: sessionmaker[Session]
    capability_references: Sequence[dict[str, object]]
    quote_provider: QuoteProvider | None = None
    social_sentiment_adapters: Sequence[SocialSentimentSourceAdapter] | None = None
    run_id: int | None = None
    agent_key: str | None = None
    agent_version: int | None = None
    agent_name: str | None = None
    workflow_key: str | None = None
    workflow_version: int | None = None
    step_id: str | None = None
    slot: str | None = None
    trace_id: str | None = None


class RuntimeToolParser(Protocol):
    def __call__(self, arguments_json: str) -> dict[str, object]: ...


class RuntimeToolExecutor(Protocol):
    def __call__(
        self,
        context: RuntimeToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class RuntimeToolSpec:
    key: str
    openai_function_name: str
    display_name: str
    description: str
    parameters_schema: dict[str, object]
    guidance: str
    sort_order: int
    denied_code: str
    denied_message: str
    parser: RuntimeToolParser
    executor: RuntimeToolExecutor
    owner_extension_key: str | None = None


MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY = "ledger.market_data.quote_lookup"
MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY = "ledger.market_data.history_lookup"
MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY = "ledger.market_data.ohlcv_lookup"
INDICATORS_LOOKUP_TOOL_KEY = "ledger.indicators.lookup"
FUNDAMENTALS_LOOKUP_TOOL_KEY = "ledger.fundamentals.lookup"
NEWS_LOOKUP_TOOL_KEY = "ledger.news.lookup"
SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY = "ledger.social_sentiment.lookup"
INSIDER_DATA_LOOKUP_TOOL_KEY = "ledger.insider_data.lookup"
REPORT_MEMORY_WRITE_TOOL_KEY = "ledger.reports.write"

NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS = (
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_TOOL_KEY,
)

_NATIVE_TOOL_KEY_RE = re.compile(r"^ledger\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
_NORMALIZED_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_WARNING_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


def _validate_chronological_datetimes(rows: Sequence[datetime]) -> None:
    previous: datetime | None = None
    for current in rows:
        if previous is not None and current < previous:
            raise ValueError("Rows must be chronological")
        previous = current


def _normalize_identifier(value: str, *, field_name: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    if _NORMALIZED_IDENTIFIER_RE.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must be a lowercase identifier")
    return normalized


def _normalize_symbols(values: Sequence[str]) -> list[str]:
    symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in values:
        symbol = normalize_symbol(raw_symbol)
        if not symbol or symbol in seen_symbols:
            continue
        symbols.append(symbol)
        seen_symbols.add(symbol)
    return symbols


class RuntimeNativeToolResult(CamelModel):
    tool_key: str = Field(min_length=1, max_length=200)

    @field_validator("tool_key")
    @classmethod
    def validate_tool_key(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _NATIVE_TOOL_KEY_RE.fullmatch(normalized) is None:
            raise ValueError(
                "Native runtime tool keys must start with ledger. "
                + "and use lowercase dotted identifiers"
            )
        if normalized not in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS:
            raise ValueError("Native runtime tool key is not registered as a financial tool result")
        return normalized


class RuntimeToolWarning(CamelModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, str] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _WARNING_CODE_RE.fullmatch(normalized) is None:
            raise ValueError("Warning code must be a lowercase identifier")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Warning message is required")
        return normalized


class RuntimeQuoteLookupResult(CamelModel):
    tool_key: Literal["ledger.market_data.quote_lookup"] = "ledger.market_data.quote_lookup"
    quotes: list[MarketQuoteRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeOhlcvRow(CamelModel):
    at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = Field(default=None, ge=0)
    adjusted_close: Decimal | None = None

    @field_validator("at")
    @classmethod
    def validate_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeOhlcvSeries(CamelModel):
    symbol: str
    currency: str | None = None
    provider: str
    rows: list[RuntimeOhlcvRow]

    @model_validator(mode="after")
    def validate_rows(self) -> Self:
        _validate_chronological_datetimes([row.at for row in self.rows])
        if any(row.high < row.low for row in self.rows):
            raise ValueError("OHLCV high must be greater than or equal to low")
        return self


class RuntimeHistoryLookupResult(CamelModel):
    tool_key: Literal["ledger.market_data.history_lookup"] = "ledger.market_data.history_lookup"
    range: str
    interval: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    series: list[MarketHistorySeriesRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("startDate must be before or equal to endDate")
        return self


class RuntimeOhlcvLookupResult(CamelModel):
    tool_key: Literal["ledger.market_data.ohlcv_lookup"] = "ledger.market_data.ohlcv_lookup"
    start_date: datetime
    end_date: datetime
    series: list[RuntimeOhlcvSeries]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("startDate must be before or equal to endDate")
        return self


class RuntimeIndicatorValue(CamelModel):
    name: str
    value: Decimal | None
    null_reason: Literal["warmup", "insufficient_history", "provider_gap"] | None = None

    @model_validator(mode="after")
    def validate_null_reason(self) -> Self:
        if self.value is None and self.null_reason is None:
            raise ValueError("nullReason is required when value is null")
        if self.value is not None and self.null_reason is not None:
            raise ValueError("nullReason must be null when value is present")
        return self


class RuntimeIndicatorRow(CamelModel):
    at: datetime
    values: list[RuntimeIndicatorValue]

    @field_validator("at")
    @classmethod
    def validate_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeIndicatorLookupResult(CamelModel):
    tool_key: Literal["ledger.indicators.lookup"] = "ledger.indicators.lookup"
    symbol: str
    provider: str
    current_date: datetime
    start_date: datetime
    end_date: datetime
    rows: list[RuntimeIndicatorRow]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("current_date", "start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_chronological_rows(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("startDate must be before or equal to endDate")
        if self.end_date > self.current_date:
            raise ValueError("endDate cannot be after currentDate")
        _validate_chronological_datetimes([row.at for row in self.rows])
        for row in self.rows:
            if row.at < self.start_date or row.at > self.end_date:
                raise ValueError("Indicator rows must be within startDate and endDate")
        return self


class RuntimeFundamentalMetric(CamelModel):
    name: str
    value: Decimal | str | None
    currency: str | None = None
    period: str | None = None
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeFinancialStatementLine(CamelModel):
    name: str
    value: Decimal | None
    currency: str | None = None


class RuntimeFinancialStatement(CamelModel):
    statement_type: Literal["income_statement", "balance_sheet", "cash_flow"]
    period: Literal["annual", "quarterly", "trailing_twelve_months"]
    period_end: datetime
    lines: list[RuntimeFinancialStatementLine]

    @field_validator("period_end")
    @classmethod
    def validate_period_end(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeFundamentalsLookupResult(CamelModel):
    tool_key: Literal["ledger.fundamentals.lookup"] = "ledger.fundamentals.lookup"
    symbol: str
    provider: str
    as_of: datetime
    metrics: list[RuntimeFundamentalMetric] = Field(default_factory=list)
    statements: list[RuntimeFinancialStatement] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeNewsItem(CamelModel):
    title: str
    url: str | None = None
    source: str
    published_at: datetime
    summary: str | None = None
    symbols: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeNewsLookupResult(CamelModel):
    tool_key: Literal["ledger.news.lookup"] = "ledger.news.lookup"
    query: str | None = None
    symbols: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    items: list[RuntimeNewsItem]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeSocialSentimentMetric(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    value: Decimal | str | None
    unit: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=120)
    as_of: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_identifier(value, field_name="Metric name")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_identifier(value, field_name="Metric source")

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeSocialSentimentSourceBlock(CamelModel):
    source: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=300)
    summary: str | None = None
    url: str | None = None
    as_of: datetime | None = None
    symbols: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None
    metrics: list[RuntimeSocialSentimentMetric] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return _normalize_identifier(value, field_name="Source")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Provider is required")
        return normalized

    @field_validator("title", "summary", "url")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        return _normalize_symbols(value)


class RuntimeSocialSentimentLookupResult(CamelModel):
    tool_key: Literal["ledger.social_sentiment.lookup"] = "ledger.social_sentiment.lookup"
    symbol: str
    sources: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    source_blocks: list[RuntimeSocialSentimentSourceBlock] = Field(default_factory=list)
    metrics: list[RuntimeSocialSentimentMetric] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = normalize_symbol(value)
        if not normalized:
            raise ValueError("Social sentiment symbol is required")
        return normalized

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        sources: list[str] = []
        seen_sources: set[str] = set()
        for raw_source in value:
            source = _normalize_identifier(raw_source, field_name="Source")
            if source in seen_sources:
                continue
            sources.append(source)
            seen_sources.add(source)
        return sources

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("startDate must be before or equal to endDate")
        return self


class RuntimeInsiderTransaction(CamelModel):
    insider_name: str
    role: str | None = None
    transaction_type: str
    shares: Decimal | None = None
    price: Decimal | None = None
    value: Decimal | None = None
    filed_at: datetime | None = None
    transaction_date: datetime

    @field_validator("filed_at", "transaction_date")
    @classmethod
    def validate_dates(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeInsiderDataLookupResult(CamelModel):
    tool_key: Literal["ledger.insider_data.lookup"] = "ledger.insider_data.lookup"
    symbol: str
    provider: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    transactions: list[RuntimeInsiderTransaction]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_bounds(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeReportMemoryWriteResult(CamelModel):
    tool_key: Literal["ledger.reports.write"] = "ledger.reports.write"
    memory_id: str = Field(min_length=1)
    status: MemoryLifecycleStatus
    action: Literal["created", "existing"]
    created_at: datetime
    provenance: MemoryProvenance
    warnings: list[dict[str, object]] = Field(default_factory=list)

    @classmethod
    def from_memory_write_result(cls, result: MemoryWriteResult) -> Self:
        return cls(
            memory_id=result.memory_id,
            status=result.status,
            action=result.action,
            created_at=result.created_at,
            provenance=result.provenance,
            warnings=result.warnings,
        )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


__all__ = [
    "FUNDAMENTALS_LOOKUP_TOOL_KEY",
    "INDICATORS_LOOKUP_TOOL_KEY",
    "INSIDER_DATA_LOOKUP_TOOL_KEY",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY",
    "MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY",
    "NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS",
    "NEWS_LOOKUP_TOOL_KEY",
    "SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY",
    "REPORT_MEMORY_WRITE_TOOL_KEY",
    "RuntimeFinancialStatement",
    "RuntimeFinancialStatementLine",
    "RuntimeFundamentalMetric",
    "RuntimeFundamentalsLookupResult",
    "RuntimeHistoryLookupResult",
    "RuntimeIndicatorLookupResult",
    "RuntimeIndicatorRow",
    "RuntimeIndicatorValue",
    "RuntimeInsiderDataLookupResult",
    "RuntimeInsiderTransaction",
    "RuntimeNativeToolResult",
    "RuntimeNewsItem",
    "RuntimeNewsLookupResult",
    "RuntimeSocialSentimentLookupResult",
    "RuntimeSocialSentimentMetric",
    "RuntimeSocialSentimentSourceBlock",
    "RuntimeOhlcvLookupResult",
    "RuntimeOhlcvRow",
    "RuntimeOhlcvSeries",
    "RuntimeQuoteLookupResult",
    "RuntimeReportMemoryWriteResult",
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolExecutor",
    "RuntimeToolParser",
    "RuntimeToolSpec",
    "RuntimeToolWarning",
]
