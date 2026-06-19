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


NewsScope = Literal["symbol", "market", "global"]


@dataclass(frozen=True, slots=True)
class ProviderNewsItem:
    title: str
    source: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None
    symbols: list[str] | None = None
    sentiment: Literal["positive", "neutral", "negative", "mixed"] | None = None


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
    "DeterministicNewsProvider",
    "NewsProvider",
    "NewsProviderError",
    "NewsProviderMissingKeyError",
    "NewsProviderRateLimitError",
    "NewsProviderTimeoutError",
    "NewsScope",
    "ProviderNewsItem",
    "ProviderNewsResult",
]
