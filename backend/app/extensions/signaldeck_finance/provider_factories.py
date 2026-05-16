from __future__ import annotations

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


__all__ = [
    "create_deterministic_quote_provider",
    "create_quote_provider",
    "create_social_sentiment_adapters",
]
