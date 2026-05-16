from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings, get_settings
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
class FinanceWorkspaceProviderFactoryRegistration:
    key: str
    summary: str
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


def register() -> tuple[FinanceWorkspaceProviderFactoryRegistration, ...]:
    return (
        FinanceWorkspaceProviderFactoryRegistration(
            key="quote_provider",
            summary="Finance quote provider factory for deterministic and Yahoo backends.",
            factory=create_quote_provider,
        ),
        FinanceWorkspaceProviderFactoryRegistration(
            key="social_sentiment_adapters",
            summary="Finance social sentiment adapters for Reddit and StockTwits.",
            factory=create_social_sentiment_adapters,
        ),
    )


__all__ = [
    "FinanceWorkspaceProviderFactoryRegistration",
    "create_deterministic_quote_provider",
    "create_quote_provider",
    "create_social_sentiment_adapters",
    "register",
]
