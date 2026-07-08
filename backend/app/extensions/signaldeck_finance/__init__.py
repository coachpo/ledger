"""Bundled SignalDeck finance workspace extension identity."""

from __future__ import annotations

from app.api.reports import router as reports_router
from app.api.templates import router as templates_router
from app.extensions.contract import Extension
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_DENIED_CODE,
    FINANCE_WORKSPACE_DENIED_MESSAGES,
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_finance.provider_factories import (
    create_deterministic_quote_provider,
    create_execution_provider_bundle,
    create_news_providers,
    create_quote_provider,
    create_social_sentiment_adapters,
)
from app.extensions.signaldeck_finance.runtime_executors import FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS
from app.extensions.signaldeck_finance.tool_specs import (
    FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS,
)

EXTENSION = Extension(
    key=FINANCE_WORKSPACE_EXTENSION_KEY,
    api_routers=(templates_router, reports_router),
    tool_declarations=FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS,
    runtime_tool_specs=FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS,
    provider_factories={
        "deterministic_quote_provider": create_deterministic_quote_provider,
        "execution_provider_bundle": create_execution_provider_bundle,
        "news_providers": create_news_providers,
        "quote_provider": create_quote_provider,
        "social_sentiment_adapters": create_social_sentiment_adapters,
    },
    runtime_dependency_surfaces=(
        "provider.fallbackQuote",
        "provider.quote",
        "provider.socialSentiment",
    ),
    package_private_mcp_tool_keys=("web_search_exa",),
)

__all__ = [
    "EXTENSION",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_DENIED_CODE",
    "FINANCE_WORKSPACE_DENIED_MESSAGES",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
]
