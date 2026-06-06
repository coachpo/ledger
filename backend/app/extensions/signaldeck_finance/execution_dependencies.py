from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.services.execution_providers import (
    ExecutionProviderBundle,
    execution_provider_bundle_from_parts,
)
from app.services.quote_provider import QuoteProvider
from app.services.social_sentiment_provider import SocialSentimentSourceAdapter


@dataclass(frozen=True, slots=True)
class FinanceExecutionProviders:
    quote_provider: QuoteProvider | None = None
    fallback_quote_provider: QuoteProvider | None = None
    social_sentiment_adapters: tuple[SocialSentimentSourceAdapter, ...] = ()


def finance_execution_provider_bundle_from_parts(
    *,
    quote_provider: QuoteProvider | None = None,
    fallback_quote_provider: QuoteProvider | None = None,
    social_sentiment_adapters: Sequence[SocialSentimentSourceAdapter] = (),
) -> ExecutionProviderBundle:
    payload = FinanceExecutionProviders(
        quote_provider=quote_provider,
        fallback_quote_provider=fallback_quote_provider,
        social_sentiment_adapters=tuple(social_sentiment_adapters),
    )
    return execution_provider_bundle_from_parts(
        extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
        payload=payload,
    )


def finance_execution_providers_for(
    provider_bundle: ExecutionProviderBundle,
) -> FinanceExecutionProviders | None:
    payload = provider_bundle.payload_for(FINANCE_WORKSPACE_EXTENSION_KEY)
    if payload is None:
        return None
    if not isinstance(payload, FinanceExecutionProviders):
        raise TypeError("Finance execution provider payload has an unexpected type.")
    return payload


def resolve_finance_quote_provider(
    provider_bundle: ExecutionProviderBundle,
) -> QuoteProvider | None:
    providers = finance_execution_providers_for(provider_bundle)
    if providers is None:
        return None
    return providers.quote_provider or providers.fallback_quote_provider


def resolve_social_sentiment_adapters(
    provider_bundle: ExecutionProviderBundle,
) -> tuple[SocialSentimentSourceAdapter, ...]:
    providers = finance_execution_providers_for(provider_bundle)
    if providers is None:
        return ()
    return providers.social_sentiment_adapters


__all__ = [
    "FinanceExecutionProviders",
    "finance_execution_provider_bundle_from_parts",
    "finance_execution_providers_for",
    "resolve_finance_quote_provider",
    "resolve_social_sentiment_adapters",
]
