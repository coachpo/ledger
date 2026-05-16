"""Private operational identity for the bundled finance workspace extension."""

from __future__ import annotations

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"
FINANCE_WORKSPACE_LABEL = "Finance Workspace"
FINANCE_WORKSPACE_DEFAULT_ENABLED = True

FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS = (
    "signaldeck.market_data.quote_lookup",
    "signaldeck.market_data.history_lookup",
    "signaldeck.market_data.ohlcv_lookup",
    "signaldeck.indicators.lookup",
    "signaldeck.fundamentals.lookup",
    "signaldeck.news.lookup",
    "signaldeck.social_sentiment.lookup",
    "signaldeck.insider_data.lookup",
    "signaldeck.positions.lookup",
    "signaldeck.reports.lookup",
    "signaldeck.reports.write",
)

FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_market_data_quote_lookup",
    "signaldeck_market_data_history_lookup",
    "signaldeck_market_data_ohlcv_lookup",
    "signaldeck_indicators_lookup",
    "signaldeck_fundamentals_lookup",
    "signaldeck_news_lookup",
    "signaldeck_social_sentiment_lookup",
    "signaldeck_insider_data_lookup",
    "signaldeck_positions_lookup",
    "signaldeck_reports_lookup",
    "signaldeck_reports_write",
)

__all__ = [
    "FINANCE_WORKSPACE_DEFAULT_ENABLED",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_LABEL",
    "FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
]
