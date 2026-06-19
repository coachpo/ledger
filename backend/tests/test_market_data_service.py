from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.provider_factories import (
    register as register_finance_workspace_provider_factories,
)
from app.services.market_data_service import MarketDataService
from app.services.news_provider import (
    NewsProvider,
    NewsProviderError,
    NewsProviderRateLimitError,
    NewsProviderTimeoutError,
    NewsScope,
    ProviderNewsItem,
    ProviderNewsResult,
)
from app.services.quote_provider import DeterministicQuoteProvider


def _news_provider(provider: object) -> NewsProvider:
    return cast(NewsProvider, provider)


def _service(provider: object) -> MarketDataService:
    return MarketDataService(
        session=cast(Session, None),
        quote_provider=DeterministicQuoteProvider(),
        news_providers=(_news_provider(provider),),
    )


class _NewsProvider:
    def __init__(
        self,
        *,
        provider_name: str = "news_test",
        items: list[ProviderNewsItem] | None = None,
        failure: NewsProviderError | None = None,
    ) -> None:
        self.provider_name: str = provider_name
        self.items: list[ProviderNewsItem] = list(items or [])
        self.failure: NewsProviderError | None = failure
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []

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
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(provider=self.provider_name, items=self.items[:limit])


@pytest.fixture()
def news_service_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[object], MarketDataService]:
    monkeypatch.setattr(MarketDataService, "_require_enabled", lambda self: None)
    return _service


def test_market_data_provider_factories_are_extension_owned() -> None:
    registrations = {
        registration.key: registration
        for registration in register_finance_workspace_provider_factories()
    }

    assert "quote_provider" in registrations
    quote_provider = registrations["quote_provider"].factory()
    assert quote_provider.__class__.__name__ in {
        "DeterministicQuoteProvider",
        "YahooFinanceQuoteProvider",
    }


def test_news_adapter_rate_limit_degrades_with_structured_warning(
    news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = _NewsProvider(
        failure=NewsProviderRateLimitError(
            "provider rate limited api_key=sk-secret",
            details={"status": "429", "api_key": "sk-secret"},
        )
    )
    service = news_service_factory(provider)
    result = service.get_news_snapshot(symbols=["nvda"], providers=[_news_provider(provider)])
    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_rate_limited",
        "news_unavailable",
    ]
    warning_json = json.dumps(payload["warnings"])
    assert "sk-secret" not in warning_json
    assert "apiKey" not in warning_json


def test_news_adapter_timeout_degrades_with_structured_warning(
    news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = _NewsProvider(failure=NewsProviderTimeoutError("news provider timed out"))
    service = news_service_factory(provider)
    result = service.get_news_snapshot(symbols=["nvda"], providers=[_news_provider(provider)])
    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_timeout",
        "news_unavailable",
    ]


def test_news_adapter_empty_result_returns_structured_warning(
    news_service_factory: Callable[[object], MarketDataService],
) -> None:
    provider = _NewsProvider()
    service = news_service_factory(provider)
    result = service.get_news_snapshot(symbols=["nvda"], providers=[_news_provider(provider)])
    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["items"] == []
    assert payload["warnings"] == [
        {
            "code": "news_empty",
            "message": "No news returned for the request",
            "details": {
                "symbols": "NVDA",
                "query": "",
                "scope": "symbol",
                "provider": "news_test",
            },
        }
    ]


def test_news_adapter_partial_result_falls_back_after_provider_outage(
    news_service_factory: Callable[[object], MarketDataService],
) -> None:
    first_provider = _NewsProvider(
        provider_name="primary_news",
        failure=NewsProviderError("primary outage", code="provider_unavailable"),
    )
    second_provider = _NewsProvider(
        provider_name="secondary_news",
        items=[
            ProviderNewsItem(
                title="Fallback item",
                source="wire",
                published_at=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ],
    )
    service = news_service_factory(first_provider)
    result = service.get_news_snapshot(
        symbols=["nvda"],
        providers=[_news_provider(first_provider), _news_provider(second_provider)],
    )
    payload = result.model_dump(mode="json", by_alias=True)

    assert [item["title"] for item in cast(list[dict[str, object]], payload["items"])] == [
        "Fallback item"
    ]
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_unavailable"
    ]
