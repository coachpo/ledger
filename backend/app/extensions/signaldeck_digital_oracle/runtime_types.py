from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.agents.runtime_tools.types import RuntimeToolWarning
from app.schemas.common import CamelModel, ensure_timezone

PREDICTION_MARKETS_LOOKUP_TOOL_KEY = "signaldeck.digital_oracle.prediction_markets.lookup"
SEC_FILINGS_LOOKUP_TOOL_KEY = "signaldeck.digital_oracle.sec_filings.lookup"
MARKET_SENTIMENT_LOOKUP_TOOL_KEY = "signaldeck.digital_oracle.market_sentiment.lookup"

NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS = (
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
)


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


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
    tool_key: Literal["signaldeck.digital_oracle.prediction_markets.lookup"] = (
        "signaldeck.digital_oracle.prediction_markets.lookup"
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
    tool_key: Literal["signaldeck.digital_oracle.sec_filings.lookup"] = (
        "signaldeck.digital_oracle.sec_filings.lookup"
    )
    ticker: str = Field(min_length=1)
    cik: str | None = None
    entity_name: str | None = None
    filings: list[RuntimeSecFiling]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeMarketSentimentLookupResult(CamelModel):
    tool_key: Literal["signaldeck.digital_oracle.market_sentiment.lookup"] = (
        "signaldeck.digital_oracle.market_sentiment.lookup"
    )
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


__all__ = [
    "MARKET_SENTIMENT_LOOKUP_TOOL_KEY",
    "NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS",
    "PREDICTION_MARKETS_LOOKUP_TOOL_KEY",
    "SEC_FILINGS_LOOKUP_TOOL_KEY",
    "RuntimeMarketSentimentLookupResult",
    "RuntimePredictionMarketContract",
    "RuntimePredictionMarketEvent",
    "RuntimePredictionMarketsLookupResult",
    "RuntimeSecFiling",
    "RuntimeSecFilingsLookupResult",
]
