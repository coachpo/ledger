from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.agents.runtime_tools.types import RuntimeToolWarning

from .config import MarketSentimentIndicator, PredictionMarketVenue


def _empty_warnings() -> tuple[RuntimeToolWarning, ...]:
    return ()


class DigitalOracleProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: Mapping[str, object] = details or {}


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsQuery:
    query: str
    venues: tuple[PredictionMarketVenue, ...] | None = None
    item_limit: int | None = None
    include_resolved: bool = False
    include_order_book: bool = False
    depth_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsProviderQuery:
    query: str
    venue: PredictionMarketVenue
    item_limit: int
    include_resolved: bool
    timeout_seconds: float
    include_order_book: bool = False
    depth_limit: int = 5


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketOrderBookLevel:
    price: Decimal
    size: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketOrderBook:
    bids: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = field(default_factory=tuple)
    asks: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = field(default_factory=tuple)
    spread: Decimal | None = None
    depth_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketContract:
    contract_id: str
    title: str
    probability: Decimal | None = None
    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    order_book: DigitalOraclePredictionMarketOrderBook | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketEvent:
    venue: PredictionMarketVenue
    event_id: str
    title: str
    status: str
    url: str | None = None
    end_date: datetime | None = None
    contracts: tuple[DigitalOraclePredictionMarketContract, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsProviderResult:
    provider: PredictionMarketVenue
    events: tuple[DigitalOraclePredictionMarketEvent, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsResult:
    query: str
    events: tuple[DigitalOraclePredictionMarketEvent, ...]
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsQuery:
    ticker: str | None = None
    query: str | None = None
    cik: str | None = None
    form_types: tuple[str, ...] | None = None
    start_date: date | None = None
    end_date: date | None = None
    item_limit: int | None = None
    include_ownership_transactions: bool = False


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsProviderQuery:
    ticker: str | None
    form_types: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    item_limit: int
    edgar_contact_email: str
    timeout_seconds: float
    query: str | None = None
    cik: str | None = None
    include_ownership_transactions: bool = False


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFiling:
    accession_number: str
    form_type: str
    filing_date: date
    accepted_at: datetime | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecSearchHit:
    accession_number: str
    form_type: str
    filing_date: date
    cik: str | None = None
    ticker: str | None = None
    entity_name: str | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None
    matched_text: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecOwnershipTransaction:
    accession_number: str
    filing_date: date
    issuer_name: str | None = None
    issuer_ticker: str | None = None
    reporting_owner_name: str | None = None
    transaction_date: date | None = None
    transaction_code: str | None = None
    acquired_disposed_code: str | None = None
    shares: Decimal | None = None
    price: Decimal | None = None
    ownership_nature: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsProviderResult:
    provider: str
    ticker: str | None
    cik: str | None = None
    entity_name: str | None = None
    filings: tuple[DigitalOracleSecFiling, ...] = field(default_factory=tuple)
    ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsResult:
    ticker: str | None = None
    query: str | None = None
    cik: str | None = None
    entity_name: str | None = None
    filings: tuple[DigitalOracleSecFiling, ...] = field(default_factory=tuple)
    search_hits: tuple[DigitalOracleSecSearchHit, ...] = field(default_factory=tuple)
    ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentQuery:
    indicator: MarketSentimentIndicator = "fear_greed"
    as_of_date: date | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentProviderQuery:
    indicator: MarketSentimentIndicator
    as_of_date: date | None
    source_url: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentProviderResult:
    provider: str
    score: int | None = None
    label: str | None = None
    as_of_date: date | None = None
    previous_close: int | None = None
    week_ago: int | None = None
    month_ago: int | None = None
    year_ago: int | None = None
    source_url: str | None = None
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentResult:
    indicator: MarketSentimentIndicator
    provider: str
    as_of_date: date | None = None
    score: int | None = None
    label: str | None = None
    previous_close: int | None = None
    week_ago: int | None = None
    month_ago: int | None = None
    year_ago: int | None = None
    source_url: str | None = None
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


class DigitalOraclePredictionMarketProvider(Protocol):
    venue: PredictionMarketVenue

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult: ...


class DigitalOracleSecFilingsProvider(Protocol):
    provider_name: str

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult: ...


class DigitalOracleMarketSentimentProvider(Protocol):
    provider_name: str

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentProviderQuery,
    ) -> DigitalOracleMarketSentimentProviderResult: ...


__all__ = [
    "DigitalOracleMarketSentimentProvider",
    "DigitalOracleMarketSentimentProviderQuery",
    "DigitalOracleMarketSentimentProviderResult",
    "DigitalOracleMarketSentimentQuery",
    "DigitalOracleMarketSentimentResult",
    "DigitalOraclePredictionMarketContract",
    "DigitalOraclePredictionMarketEvent",
    "DigitalOraclePredictionMarketOrderBook",
    "DigitalOraclePredictionMarketOrderBookLevel",
    "DigitalOraclePredictionMarketProvider",
    "DigitalOraclePredictionMarketsProviderQuery",
    "DigitalOraclePredictionMarketsProviderResult",
    "DigitalOraclePredictionMarketsQuery",
    "DigitalOraclePredictionMarketsResult",
    "DigitalOracleProviderError",
    "DigitalOracleSecFiling",
    "DigitalOracleSecFilingsProvider",
    "DigitalOracleSecFilingsProviderQuery",
    "DigitalOracleSecFilingsProviderResult",
    "DigitalOracleSecFilingsQuery",
    "DigitalOracleSecFilingsResult",
    "DigitalOracleSecOwnershipTransaction",
    "DigitalOracleSecSearchHit",
]
