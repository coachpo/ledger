from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.services.quote_provider import QuoteProvider
from app.services.social_sentiment_provider import SocialSentimentSourceAdapter


@dataclass(frozen=True, slots=True)
class ExecutionProviderBundle:
    quote_provider: QuoteProvider | None = None
    fallback_quote_provider: QuoteProvider | None = None
    social_sentiment_adapters: tuple[SocialSentimentSourceAdapter, ...] = ()


def execution_provider_bundle_from_parts(
    *,
    quote_provider: QuoteProvider | None = None,
    fallback_quote_provider: QuoteProvider | None = None,
    social_sentiment_adapters: Sequence[SocialSentimentSourceAdapter] | None = None,
) -> ExecutionProviderBundle:
    return ExecutionProviderBundle(
        quote_provider=quote_provider,
        fallback_quote_provider=fallback_quote_provider,
        social_sentiment_adapters=tuple(social_sentiment_adapters or ()),
    )


def merge_execution_provider_bundles(
    bundles: Iterable[ExecutionProviderBundle],
) -> ExecutionProviderBundle:
    quote_provider: QuoteProvider | None = None
    fallback_quote_provider: QuoteProvider | None = None
    social_sentiment_adapters: list[SocialSentimentSourceAdapter] = []
    for bundle in bundles:
        if quote_provider is None and bundle.quote_provider is not None:
            quote_provider = bundle.quote_provider
        if fallback_quote_provider is None and bundle.fallback_quote_provider is not None:
            fallback_quote_provider = bundle.fallback_quote_provider
        social_sentiment_adapters.extend(bundle.social_sentiment_adapters)
    return ExecutionProviderBundle(
        quote_provider=quote_provider,
        fallback_quote_provider=fallback_quote_provider,
        social_sentiment_adapters=tuple(social_sentiment_adapters),
    )


__all__ = [
    "ExecutionProviderBundle",
    "execution_provider_bundle_from_parts",
    "merge_execution_provider_bundles",
]
