from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
)
from app.services.execution_providers import ExecutionProviderBundle
from app.services.news_provider import (
    AlphaVantageNewsProvider,
    DeterministicNewsProvider,
    NewsProvider,
    YahooFinanceNewsProvider,
)
from app.services.quote_provider import (
    DeterministicQuoteProvider,
    QuoteProvider,
    YahooFinanceQuoteProvider,
)
from app.services.social_sentiment_provider import (
    RedditSocialSentimentAdapter,
    SocialSentimentSourceAdapter,
    StockTwitsSocialSentimentAdapter,
    _RedditRequestConfig,
)


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceProviderFactory:
    key: str
    factory: Callable[[], object]


def create_deterministic_quote_provider() -> QuoteProvider:
    return DeterministicQuoteProvider()


def create_quote_provider(settings: Settings | None = None) -> QuoteProvider:
    resolved_settings = settings or get_settings()
    if resolved_settings.quote_provider_backend == "deterministic":
        return create_deterministic_quote_provider()
    return YahooFinanceQuoteProvider(
        timeout=resolved_settings.quote_provider_timeout_seconds,
    )


def create_social_sentiment_adapters(
    settings: Settings | None = None,
) -> tuple[SocialSentimentSourceAdapter, ...]:
    resolved_settings = settings or get_settings()
    timeout = resolved_settings.quote_provider_timeout_seconds
    return (
        RedditSocialSentimentAdapter(
            timeout=timeout,
            config=_RedditRequestConfig(
                subreddits=tuple(resolved_settings.finance_reddit_subreddits),
                retry_after_max_seconds=(resolved_settings.finance_reddit_retry_after_max_seconds),
                inter_request_delay_seconds=(
                    resolved_settings.finance_reddit_inter_request_delay_seconds
                ),
            ),
        ),
        StockTwitsSocialSentimentAdapter(timeout=timeout),
    )


def create_news_providers(settings: Settings | None = None) -> tuple[NewsProvider, ...]:
    resolved_settings = settings or get_settings()
    if resolved_settings.quote_provider_backend == "deterministic":
        return (DeterministicNewsProvider(),)
    providers: list[NewsProvider] = []
    for provider_key in resolved_settings.finance_news_provider_order:
        match provider_key:
            case "alpha_vantage":
                providers.append(
                    AlphaVantageNewsProvider(
                        api_key=resolved_settings.finance_alpha_vantage_api_key,
                        timeout=resolved_settings.quote_provider_timeout_seconds,
                    )
                )
            case "deterministic":
                providers.append(DeterministicNewsProvider())
            case "yahoo":
                providers.append(
                    YahooFinanceNewsProvider(
                        timeout=resolved_settings.quote_provider_timeout_seconds,
                        global_queries=tuple(resolved_settings.finance_global_news_queries),
                        global_lookback_days=resolved_settings.finance_global_news_lookback_days,
                    )
                )
    return tuple(providers)


def create_execution_provider_bundle(
    settings: Settings | None = None,
) -> ExecutionProviderBundle:
    resolved_settings = settings or get_settings()
    return finance_execution_provider_bundle_from_parts(
        quote_provider=create_quote_provider(resolved_settings),
        fallback_quote_provider=create_deterministic_quote_provider(),
        news_providers=create_news_providers(resolved_settings),
        social_sentiment_adapters=create_social_sentiment_adapters(resolved_settings),
    )


def register() -> tuple[FinanceWorkspaceProviderFactory, ...]:
    return (
        FinanceWorkspaceProviderFactory(
            key="quote_provider",
            factory=create_quote_provider,
        ),
        FinanceWorkspaceProviderFactory(
            key="deterministic_quote_provider",
            factory=create_deterministic_quote_provider,
        ),
        FinanceWorkspaceProviderFactory(
            key="social_sentiment_adapters",
            factory=create_social_sentiment_adapters,
        ),
        FinanceWorkspaceProviderFactory(
            key="news_providers",
            factory=create_news_providers,
        ),
    )


__all__ = [
    "FinanceWorkspaceProviderFactory",
    "create_deterministic_quote_provider",
    "create_execution_provider_bundle",
    "create_news_providers",
    "create_quote_provider",
    "create_social_sentiment_adapters",
    "register",
]
