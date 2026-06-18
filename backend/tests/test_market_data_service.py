from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.provider_factories import (
    register as register_finance_workspace_provider_factories,
)
from app.services.market_data_service import MarketDataService
from app.services.quote_provider import (
    ProviderNewsItem,
    ProviderNewsResult,
    QuoteProvider,
    QuoteProviderError,
    QuoteProviderRateLimitError,
    QuoteProviderTimeoutError,
    YahooFinanceQuoteProvider,
)


def _quote_provider(provider: object) -> QuoteProvider:
    return cast(QuoteProvider, provider)


def _service(session: Session, provider: object) -> MarketDataService:
    return MarketDataService(
        session=session,
        quote_provider=_quote_provider(provider),
    )


def _timestamp(value: datetime) -> int:
    return int(value.timestamp())


class _NewsProvider:
    def __init__(
        self,
        *,
        provider_name: str = "news_test",
        items: list[ProviderNewsItem] | None = None,
        failure: QuoteProviderError | None = None,
    ) -> None:
        self.provider_name: str = provider_name
        self.items: list[ProviderNewsItem] = list(items or [])
        self.failure: QuoteProviderError | None = failure
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(provider=self.provider_name, items=self.items[:limit])


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


def test_news_adapter_yahoo_normalizes_company_and_macro_news(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = YahooFinanceQuoteProvider(timeout=0.1)
    calls: list[tuple[str, int]] = []

    def fake_fetch_news_payload(query: str, *, limit: int) -> dict[str, object]:
        calls.append((query, limit))
        if query == "financial markets":
            return {
                "news": [
                    {
                        "title": "Macro market recap",
                        "publisher": "Macro Wire",
                        "providerPublishTime": _timestamp(datetime(2026, 1, 2, tzinfo=UTC)),
                    }
                ]
            }
        return {
            "news": [
                {
                    "title": "Nvidia earnings recap",
                    "publisher": "Market Wire",
                    "providerPublishTime": _timestamp(datetime(2026, 1, 2, tzinfo=UTC)),
                    "link": "https://example.test/nvda",
                    "summary": "Results beat expectations.",
                    "relatedTickers": ["nvda", "NVDA"],
                },
                {
                    "title": "Outside window",
                    "publisher": "Old Wire",
                    "providerPublishTime": _timestamp(datetime(2025, 12, 31, tzinfo=UTC)),
                },
            ]
        }

    monkeypatch.setattr(provider, "_fetch_news_payload", fake_fetch_news_payload)
    result = provider.fetch_news(
        symbols=[" nvda ", "NVDA"],
        query=" earnings ",
        scope="symbol",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 3, tzinfo=UTC),
        limit=5,
    )
    macro_result = provider.fetch_news(
        symbols=[],
        query=None,
        scope="market",
        start_date=None,
        end_date=None,
        limit=2,
    )

    assert calls == [("NVDA earnings", 5), ("financial markets", 2)]
    assert result.provider == "yahoo_finance"
    assert [item.title for item in result.items] == ["Nvidia earnings recap"]
    assert result.items[0].source == "Market Wire"
    assert result.items[0].symbols == ["NVDA"]
    assert macro_result.items[0].symbols == []


def test_news_adapter_rate_limit_degrades_with_structured_warning(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _NewsProvider(
        failure=QuoteProviderRateLimitError(
            "provider rate limited api_key=sk-secret",
            details={"status": "429", "api_key": "sk-secret"},
        )
    )
    with session_factory() as session:
        service = _service(session, provider)
        result = service.get_news_snapshot(symbols=["nvda"], providers=[_quote_provider(provider)])
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
    session_factory: sessionmaker[Session],
) -> None:
    provider = _NewsProvider(failure=QuoteProviderTimeoutError("news provider timed out"))
    with session_factory() as session:
        service = _service(session, provider)
        result = service.get_news_snapshot(symbols=["nvda"], providers=[_quote_provider(provider)])
    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_timeout",
        "news_unavailable",
    ]


def test_news_adapter_empty_result_returns_structured_warning(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _NewsProvider()
    with session_factory() as session:
        service = _service(session, provider)
        result = service.get_news_snapshot(symbols=["nvda"], providers=[_quote_provider(provider)])
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
    session_factory: sessionmaker[Session],
) -> None:
    first_provider = _NewsProvider(
        provider_name="primary_news",
        failure=QuoteProviderError("primary outage", code="provider_unavailable"),
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
    with session_factory() as session:
        service = _service(session, first_provider)
        result = service.get_news_snapshot(
            symbols=["nvda"],
            providers=[_quote_provider(first_provider), _quote_provider(second_provider)],
        )
    payload = result.model_dump(mode="json", by_alias=True)

    assert [item["title"] for item in cast(list[dict[str, object]], payload["items"])] == [
        "Fallback item"
    ]
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_provider_unavailable"
    ]
