# ruff: noqa: I001
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.agents.runtime_tools.types import RuntimeToolWarning
from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from app.schemas.memory import MemoryLifecycleStatus, MemoryProvenance, MemoryWriteResult
from app.services.market_data_snapshots import (
    MarketDataFinancialStatement as RuntimeFinancialStatement,
)
from app.services.market_data_snapshots import (
    MarketDataFinancialStatementLine as RuntimeFinancialStatementLine,
)
from app.services.market_data_snapshots import (
    MarketDataFundamentalMetric as RuntimeFundamentalMetric,
)
from app.services.market_data_snapshots import (
    MarketDataFundamentalsLookupResult,
    MarketDataIndicatorLookupResult,
)
from app.services.market_data_snapshots import MarketDataIndicatorRow as RuntimeIndicatorRow
from app.services.market_data_snapshots import MarketDataIndicatorValue as RuntimeIndicatorValue
from app.services.market_data_snapshots import MarketDataInsiderDataLookupResult
from app.services.market_data_snapshots import (
    MarketDataInsiderTransaction as RuntimeInsiderTransaction,
)
from app.services.market_data_snapshots import MarketDataNewsItem as RuntimeNewsItem
from app.services.market_data_snapshots import (
    MarketDataNewsLookupResult,
    MarketDataOhlcvLookupResult,
)
from app.services.market_data_snapshots import MarketDataOhlcvRow as RuntimeOhlcvRow
from app.services.market_data_snapshots import MarketDataOhlcvSeries as RuntimeOhlcvSeries
from app.services.social_sentiment_snapshots import SocialSentimentLookupResult
from app.services.social_sentiment_snapshots import (
    SocialSentimentMetric as RuntimeSocialSentimentMetric,
)
from app.services.social_sentiment_snapshots import (
    SocialSentimentSourceBlock as RuntimeSocialSentimentSourceBlock,
)

MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY = "signaldeck.market_data.quote_lookup"
MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY = "signaldeck.market_data.history_lookup"
MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY = "signaldeck.market_data.ohlcv_lookup"
INDICATORS_LOOKUP_TOOL_KEY = "signaldeck.indicators.lookup"
FUNDAMENTALS_LOOKUP_TOOL_KEY = "signaldeck.fundamentals.lookup"
NEWS_LOOKUP_TOOL_KEY = "signaldeck.news.lookup"
SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY = "signaldeck.social_sentiment.lookup"
INSIDER_DATA_LOOKUP_TOOL_KEY = "signaldeck.insider_data.lookup"
PREDICTION_MARKETS_LOOKUP_TOOL_KEY = "signaldeck.prediction_markets.lookup"
SEC_FILINGS_LOOKUP_TOOL_KEY = "signaldeck.sec_filings.lookup"
MARKET_SENTIMENT_LOOKUP_TOOL_KEY = "signaldeck.market_sentiment.lookup"
POSITION_LOOKUP_TOOL_KEY = "signaldeck.positions.lookup"
REPORT_LOOKUP_TOOL_KEY = "signaldeck.reports.lookup"
REPORT_MEMORY_WRITE_TOOL_KEY = "signaldeck.reports.write"

NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS = (
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
)

_NATIVE_TOOL_KEY_RE = re.compile(r"^signaldeck\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


class RuntimeNativeToolResult(CamelModel):
    tool_key: str = Field(min_length=1, max_length=200)

    @field_validator("tool_key")
    @classmethod
    def validate_tool_key(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _NATIVE_TOOL_KEY_RE.fullmatch(normalized) is None:
            raise ValueError(
                "Native runtime tool keys must start with signaldeck. "
                + "and use lowercase dotted identifiers"
            )
        if normalized not in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS:
            raise ValueError("Native runtime tool key is not registered as a financial tool result")
        return normalized


class RuntimeQuoteLookupResult(CamelModel):
    tool_key: Literal["signaldeck.market_data.quote_lookup"] = "signaldeck.market_data.quote_lookup"
    quotes: list[MarketQuoteRead]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeHistoryLookupResult(CamelModel):
    tool_key: Literal["signaldeck.market_data.history_lookup"] = (
        "signaldeck.market_data.history_lookup"
    )
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


class RuntimeOhlcvLookupResult(MarketDataOhlcvLookupResult):
    tool_key: Literal["signaldeck.market_data.ohlcv_lookup"] = "signaldeck.market_data.ohlcv_lookup"


class RuntimeIndicatorLookupResult(MarketDataIndicatorLookupResult):
    tool_key: Literal["signaldeck.indicators.lookup"] = "signaldeck.indicators.lookup"


class RuntimeFundamentalsLookupResult(MarketDataFundamentalsLookupResult):
    tool_key: Literal["signaldeck.fundamentals.lookup"] = "signaldeck.fundamentals.lookup"


class RuntimeNewsLookupResult(MarketDataNewsLookupResult):
    tool_key: Literal["signaldeck.news.lookup"] = "signaldeck.news.lookup"


class RuntimeSocialSentimentLookupResult(SocialSentimentLookupResult):
    tool_key: Literal["signaldeck.social_sentiment.lookup"] = "signaldeck.social_sentiment.lookup"


class RuntimeInsiderDataLookupResult(MarketDataInsiderDataLookupResult):
    tool_key: Literal["signaldeck.insider_data.lookup"] = "signaldeck.insider_data.lookup"


class RuntimePredictionMarketContract(CamelModel):
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    probability: Decimal | None = None
    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None


class RuntimePredictionMarketEvent(CamelModel):
    venue: Literal["polymarket", "kalshi"]
    event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)
    url: str | None = None
    end_date: datetime | None = None
    contracts: list[RuntimePredictionMarketContract]

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimePredictionMarketsLookupResult(CamelModel):
    tool_key: Literal["signaldeck.prediction_markets.lookup"] = (
        "signaldeck.prediction_markets.lookup"
    )
    query: str = Field(min_length=1)
    events: list[RuntimePredictionMarketEvent]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeSecFiling(CamelModel):
    accession_number: str = Field(min_length=1)
    form_type: str = Field(min_length=1)
    filing_date: date
    accepted_at: datetime | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None

    @field_validator("accepted_at")
    @classmethod
    def validate_accepted_at(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeSecFilingsLookupResult(CamelModel):
    tool_key: Literal["signaldeck.sec_filings.lookup"] = "signaldeck.sec_filings.lookup"
    ticker: str = Field(min_length=1)
    cik: str | None = None
    entity_name: str | None = None
    filings: list[RuntimeSecFiling]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeMarketSentimentLookupResult(CamelModel):
    tool_key: Literal["signaldeck.market_sentiment.lookup"] = "signaldeck.market_sentiment.lookup"
    indicator: Literal["fear_greed"]
    as_of_date: date | None = None
    provider: str = Field(min_length=1)
    score: int | None = Field(default=None, ge=0, le=100)
    label: str | None = None
    previous_close: int | None = Field(default=None, ge=0, le=100)
    week_ago: int | None = Field(default=None, ge=0, le=100)
    month_ago: int | None = Field(default=None, ge=0, le=100)
    year_ago: int | None = Field(default=None, ge=0, le=100)
    source_url: str | None = None
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeReportMemoryWriteResult(CamelModel):
    tool_key: Literal["signaldeck.reports.write"] = "signaldeck.reports.write"
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
    "MARKET_SENTIMENT_LOOKUP_TOOL_KEY",
    "NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS",
    "NEWS_LOOKUP_TOOL_KEY",
    "POSITION_LOOKUP_TOOL_KEY",
    "PREDICTION_MARKETS_LOOKUP_TOOL_KEY",
    "REPORT_LOOKUP_TOOL_KEY",
    "REPORT_MEMORY_WRITE_TOOL_KEY",
    "SEC_FILINGS_LOOKUP_TOOL_KEY",
    "SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY",
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
    "RuntimeMarketSentimentLookupResult",
    "RuntimeNativeToolResult",
    "RuntimeNewsItem",
    "RuntimeNewsLookupResult",
    "RuntimeOhlcvLookupResult",
    "RuntimeOhlcvRow",
    "RuntimeOhlcvSeries",
    "RuntimePredictionMarketContract",
    "RuntimePredictionMarketEvent",
    "RuntimePredictionMarketsLookupResult",
    "RuntimeQuoteLookupResult",
    "RuntimeReportMemoryWriteResult",
    "RuntimeSecFiling",
    "RuntimeSecFilingsLookupResult",
    "RuntimeSocialSentimentLookupResult",
    "RuntimeSocialSentimentMetric",
    "RuntimeSocialSentimentSourceBlock",
]
