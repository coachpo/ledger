from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, Protocol

from app.core.formatting import normalize_symbol


class NewsProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: dict[str, str] = details or {}


class NewsProviderMissingKeyError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_api_key_missing", details=details)


class NewsProviderTimeoutError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_timeout", details=details)


class NewsProviderRateLimitError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_rate_limited", details=details)


class NewsProviderUnavailableError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_unavailable", details=details)


class NewsProviderMalformedResponseError(NewsProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_malformed_response", details=details)


NewsScope = Literal["symbol", "market", "global"]
NewsSentiment = Literal["positive", "neutral", "negative", "mixed"]


@dataclass(frozen=True, slots=True)
class ProviderNewsItem:
    title: str
    source: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None
    symbols: list[str] | None = None
    sentiment: NewsSentiment | None = None


@dataclass(frozen=True, slots=True)
class ProviderNewsResult:
    provider: str
    items: list[ProviderNewsItem]


class NewsProvider(Protocol):
    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult: ...


@dataclass(frozen=True, slots=True)
class AlphaVantageNewsProvider:
    api_key: str | None
    provider_name: str = "alpha_vantage"

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del symbols, query, scope, start_date, end_date, limit
        if self.api_key is None:
            raise NewsProviderMissingKeyError(
                "Alpha Vantage news provider requires a configured API key",
                details={"provider": self.provider_name},
            )
        raise NewsProviderUnavailableError(
            "Alpha Vantage news provider parsing is not implemented yet",
            details={"provider": self.provider_name},
        )


@dataclass(frozen=True, slots=True)
class YahooFinanceNewsProvider:
    provider_name: str = "yahoo"

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del symbols, query, scope, start_date, end_date, limit
        raise NewsProviderUnavailableError(
            "Yahoo Finance news provider parsing is not implemented yet",
            details={"provider": self.provider_name},
        )


class DeterministicNewsProvider:
    provider_name: str = "deterministic_test"

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: NewsScope,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del start_date, end_date
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            query_label = (query or scope).strip().replace("_", " ")
            return ProviderNewsResult(
                provider=self.provider_name,
                items=[
                    ProviderNewsItem(
                        title=f"{query_label} deterministic news update",
                        source="deterministic_test",
                        published_at=datetime.combine(
                            date(2024, 3, 29), datetime.min.time(), tzinfo=UTC
                        ),
                        symbols=[],
                        sentiment="neutral",
                    )
                ][:limit],
            )
        items = [
            ProviderNewsItem(
                title=f"{symbol} deterministic market update",
                source="deterministic_test",
                published_at=datetime.combine(date(2024, 3, 29), datetime.min.time(), tzinfo=UTC),
                symbols=[symbol],
                sentiment="neutral",
            )
            for symbol in normalized_symbols[:limit]
        ]
        return ProviderNewsResult(provider=self.provider_name, items=items)


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized_symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        normalized_symbols.append(symbol)
    return normalized_symbols


__all__ = [
    "AlphaVantageNewsProvider",
    "DeterministicNewsProvider",
    "NewsProvider",
    "NewsProviderError",
    "NewsProviderMalformedResponseError",
    "NewsProviderMissingKeyError",
    "NewsProviderRateLimitError",
    "NewsProviderTimeoutError",
    "NewsProviderUnavailableError",
    "NewsSentiment",
    "NewsScope",
    "ProviderNewsItem",
    "ProviderNewsResult",
    "YahooFinanceNewsProvider",
]
