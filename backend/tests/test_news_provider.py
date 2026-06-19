from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast, get_type_hints

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
    resolve_finance_news_providers,
)
from app.extensions.signaldeck_finance.provider_factories import create_news_providers
from app.services import news_provider
from app.services.market_data_service import MarketDataService
from app.services.news_provider import (
    DeterministicNewsProvider,
    NewsProviderMalformedResponseError,
    NewsProviderUnavailableError,
    NewsSentiment,
    ProviderNewsItem,
)
from app.services.quote_provider import DeterministicQuoteProvider, QuoteProvider


def test_deterministic_news_provider_preserves_existing_shape() -> None:
    provider = DeterministicNewsProvider()

    result = provider.fetch_news(
        symbols=[" nvda ", "NVDA"],
        query=" earnings ",
        scope="symbol",
        start_date=datetime(2024, 3, 1, tzinfo=UTC),
        end_date=datetime(2024, 4, 1, tzinfo=UTC),
        limit=5,
    )

    assert result.provider == "deterministic_test"
    assert len(result.items) == 1
    assert result.items[0].title == "NVDA deterministic market update"
    assert result.items[0].source == "deterministic_test"
    assert result.items[0].published_at == datetime(2024, 3, 29, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA"]
    assert result.items[0].sentiment == "neutral"


def test_quote_provider_protocol_has_no_news_method() -> None:
    assert "fetch_news" not in QuoteProvider.__dict__


def test_news_provider_contract_exports_sentiment_alias_and_error_codes() -> None:
    unavailable = NewsProviderUnavailableError(
        "provider unavailable", details={"provider": "news_test"}
    )
    malformed = NewsProviderMalformedResponseError(
        "provider malformed response", details={"provider": "news_test"}
    )

    assert get_type_hints(ProviderNewsItem)["sentiment"] == NewsSentiment | None
    assert unavailable.code == "provider_unavailable"
    assert unavailable.details == {"provider": "news_test"}
    assert malformed.code == "provider_malformed_response"
    assert malformed.details == {"provider": "news_test"}
    assert "NewsSentiment" in news_provider.__all__
    assert "NewsProviderUnavailableError" in news_provider.__all__
    assert "NewsProviderMalformedResponseError" in news_provider.__all__


def test_finance_news_settings_normalize_order_and_lists() -> None:
    settings = Settings.model_validate(
        {
            "FINANCE_ALPHA_VANTAGE_API_KEY": "  alpha-key  ",
            "FINANCE_NEWS_PROVIDER_ORDER": " Alpha_Vantage, yahoo, alpha_vantage, deterministic ",
            "FINANCE_GLOBAL_NEWS_QUERIES": " markets, macro , markets ",
            "FINANCE_REDDIT_SUBREDDITS": " stocks, investing, stocks ",
        }
    )

    assert settings.finance_alpha_vantage_api_key == "alpha-key"
    assert settings.finance_news_provider_order == ["alpha_vantage", "yahoo", "deterministic"]
    assert settings.finance_global_news_queries == ["markets", "macro"]
    assert settings.finance_reddit_subreddits == ["stocks", "investing"]


def test_finance_news_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError, match="FINANCE_NEWS_PROVIDER_ORDER"):
        _ = Settings.model_validate({"FINANCE_NEWS_PROVIDER_ORDER": "unknown"})


def test_create_news_providers_preserves_configured_order() -> None:
    settings = Settings.model_validate(
        {
            "finance_news_provider_order": ["alpha_vantage", "yahoo"],
            "finance_alpha_vantage_api_key": "alpha-key",
        }
    )

    providers = create_news_providers(settings)

    assert [provider.__class__.__name__ for provider in providers] == [
        "AlphaVantageNewsProvider",
        "YahooFinanceNewsProvider",
    ]


def test_create_news_providers_uses_deterministic_backend_only() -> None:
    settings = Settings.model_validate(
        {
            "QUOTE_PROVIDER_BACKEND": "deterministic",
            "finance_news_provider_order": ["alpha_vantage", "yahoo"],
            "finance_alpha_vantage_api_key": "alpha-key",
        }
    )

    providers = create_news_providers(settings)

    assert [provider.__class__ for provider in providers] == [DeterministicNewsProvider]


def test_resolve_finance_news_providers_returns_ordered_payload() -> None:
    providers = create_news_providers(
        Settings.model_validate(
            {
                "finance_news_provider_order": ["alpha_vantage", "yahoo"],
                "finance_alpha_vantage_api_key": "alpha-key",
            }
        )
    )
    bundle = finance_execution_provider_bundle_from_parts(news_providers=providers)

    assert resolve_finance_news_providers(bundle) == providers


def test_alpha_news_provider_missing_key_surfaces_service_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MarketDataService, "_require_enabled", lambda self: None)
    providers = create_news_providers(
        Settings.model_validate({"FINANCE_NEWS_PROVIDER_ORDER": "alpha_vantage,yahoo"})
    )
    service = MarketDataService(
        session=cast(Session, None),
        quote_provider=DeterministicQuoteProvider(),
        news_providers=providers,
    )

    result = service.get_news_snapshot(symbols=["nvda"])
    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["items"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "news_api_key_missing",
        "news_provider_unavailable",
        "news_unavailable",
    ]
    assert "FINANCE_ALPHA_VANTAGE_API_KEY" not in json.dumps(payload["warnings"])
