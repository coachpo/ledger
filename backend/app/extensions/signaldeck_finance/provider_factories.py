from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.services.execution_providers import ExecutionProviderBundle
from app.services.quote_provider import (
    DeterministicQuoteProvider,
    QuoteProvider,
    YahooFinanceQuoteProvider,
)
from app.services.social_sentiment_provider import (
    RedditSocialSentimentAdapter,
    SocialSentimentSourceAdapter,
    StockTwitsSocialSentimentAdapter,
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
        RedditSocialSentimentAdapter(timeout=timeout),
        StockTwitsSocialSentimentAdapter(timeout=timeout),
    )


def create_execution_provider_bundle(
    settings: Settings | None = None,
) -> ExecutionProviderBundle:
    resolved_settings = settings or get_settings()
    return ExecutionProviderBundle(
        quote_provider=create_quote_provider(resolved_settings),
        fallback_quote_provider=create_deterministic_quote_provider(),
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
    )


__all__ = [
    "FinanceWorkspaceProviderFactory",
    "create_deterministic_quote_provider",
    "create_execution_provider_bundle",
    "create_quote_provider",
    "create_social_sentiment_adapters",
    "register",
]
