from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast, get_type_hints

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.config import FinanceWorkspaceSettings
from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
    resolve_finance_news_providers,
)
from app.extensions.signaldeck_finance.provider_factories import (
    FinanceProviderSecrets,
    create_news_providers,
    create_runtime_news_providers,
)
from app.services import news_provider
from app.services.market_data_service import MarketDataService
from app.services.news_provider import (
    AlphaVantageNewsProvider,
    DeterministicNewsProvider,
    NewsProviderMalformedResponseError,
    NewsProviderUnavailableError,
    NewsProviderUnsupportedQueryError,
    NewsSentiment,
    ProviderNewsItem,
    YahooFinanceNewsProvider,
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
    assert NewsProviderUnsupportedQueryError("unsupported").code == "provider_unsupported_query"
    assert "NewsSentiment" in news_provider.__all__
    assert "NewsProviderUnavailableError" in news_provider.__all__
    assert "NewsProviderMalformedResponseError" in news_provider.__all__
    assert "NewsProviderUnsupportedQueryError" in news_provider.__all__


def test_finance_news_settings_normalize_order_and_lists() -> None:
    settings = FinanceWorkspaceSettings.model_validate(
        {
            "FINANCE_NEWS_PROVIDER_ORDER": " Alpha_Vantage, yahoo, alpha_vantage, deterministic ",
            "FINANCE_GLOBAL_NEWS_QUERIES": " markets, macro , markets ",
            "FINANCE_REDDIT_SUBREDDITS": " stocks, investing, stocks ",
        }
    )

    assert settings.finance_news_provider_order == ["alpha_vantage", "yahoo", "deterministic"]
    assert settings.finance_global_news_queries == ["markets", "macro"]
    assert settings.finance_reddit_subreddits == ["stocks", "investing"]


def test_finance_news_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError, match="FINANCE_NEWS_PROVIDER_ORDER"):
        _ = FinanceWorkspaceSettings.model_validate({"FINANCE_NEWS_PROVIDER_ORDER": "unknown"})


def test_create_news_providers_preserves_configured_order() -> None:
    settings = FinanceWorkspaceSettings.model_validate(
        {
            "finance_news_provider_order": ["alpha_vantage", "yahoo"],
            "quote_provider_timeout_seconds": 3.5,
            "finance_global_news_queries": ["markets", "macro"],
            "finance_global_news_lookback_days": 5,
        }
    )

    providers = create_news_providers(settings)

    assert [provider.__class__.__name__ for provider in providers] == [
        "AlphaVantageNewsProvider",
        "YahooFinanceNewsProvider",
    ]
    yahoo_provider = providers[1]
    assert isinstance(yahoo_provider, YahooFinanceNewsProvider)
    alpha_provider = providers[0]
    assert isinstance(alpha_provider, AlphaVantageNewsProvider)
    assert alpha_provider.api_key is None
    assert alpha_provider.timeout == 3.5
    assert yahoo_provider.timeout == 3.5
    assert yahoo_provider.global_queries == ("markets", "macro")
    assert yahoo_provider.global_lookback_days == 5


def test_create_runtime_news_providers_uses_explicit_alpha_vantage_secret() -> None:
    providers = create_runtime_news_providers(
        provider_secrets=FinanceProviderSecrets(alpha_vantage_api_key="alpha-key"),
        settings=FinanceWorkspaceSettings.model_validate(
            {
                "finance_news_provider_order": ["alpha_vantage", "yahoo"],
                "quote_provider_timeout_seconds": 3.5,
            }
        ),
    )

    alpha_provider = providers[0]
    assert isinstance(alpha_provider, AlphaVantageNewsProvider)
    assert alpha_provider.api_key == "alpha-key"


def test_create_news_providers_uses_deterministic_backend_only() -> None:
    settings = FinanceWorkspaceSettings.model_validate(
        {
            "QUOTE_PROVIDER_BACKEND": "deterministic",
            "finance_news_provider_order": ["alpha_vantage", "yahoo"],
        }
    )

    providers = create_news_providers(settings)

    assert [provider.__class__ for provider in providers] == [DeterministicNewsProvider]


def test_resolve_finance_news_providers_returns_ordered_payload() -> None:
    providers = create_news_providers(
        FinanceWorkspaceSettings.model_validate(
            {
                "finance_news_provider_order": ["alpha_vantage", "yahoo"],
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
        FinanceWorkspaceSettings.model_validate({"FINANCE_NEWS_PROVIDER_ORDER": "alpha_vantage"})
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
        "news_unavailable",
    ]
    assert "apiKey" not in json.dumps(payload["warnings"])
