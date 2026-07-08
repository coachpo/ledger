"""Private operational identity for the bundled finance workspace extension."""

from __future__ import annotations

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"
FINANCE_WORKSPACE_LABEL = "Finance Workspace"
FINANCE_WORKSPACE_DEFAULT_ENABLED = True

FINANCE_WORKSPACE_DENIED_CODE = "agent_execution_access_denied"

FINANCE_WORKSPACE_DENIED_MESSAGES = {
    "signaldeck.finance.market_data.quote_lookup": (
        "Agent is not authorized to use signaldeck.finance.market_data.quote_lookup."
    ),
    "signaldeck.finance.market_data.history_lookup": (
        "Agent is not authorized to use signaldeck.finance.market_data.history_lookup."
    ),
    "signaldeck.finance.market_data.ohlcv_lookup": (
        "Agent is not authorized to use signaldeck.finance.market_data.ohlcv_lookup."
    ),
    "signaldeck.finance.indicators.lookup": (
        "Agent is not authorized to use signaldeck.finance.indicators.lookup."
    ),
    "signaldeck.finance.fundamentals.lookup": (
        "Agent is not authorized to use signaldeck.finance.fundamentals.lookup."
    ),
    "signaldeck.finance.news.lookup": (
        "Agent is not authorized to use signaldeck.finance.news.lookup."
    ),
    "signaldeck.finance.social_sentiment.lookup": (
        "Agent is not authorized to use signaldeck.finance.social_sentiment.lookup."
    ),
    "signaldeck.finance.insider_data.lookup": (
        "Agent is not authorized to use signaldeck.finance.insider_data.lookup."
    ),
    "signaldeck.finance.reports.lookup": (
        "Agent is not authorized to use signaldeck.finance.reports.lookup."
    ),
}

FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS = (
    "signaldeck.finance.market_data.quote_lookup",
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
    "signaldeck.finance.indicators.lookup",
    "signaldeck.finance.fundamentals.lookup",
    "signaldeck.finance.news.lookup",
    "signaldeck.finance.social_sentiment.lookup",
    "signaldeck.finance.insider_data.lookup",
    "signaldeck.finance.reports.lookup",
)

FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_finance_market_data_quote_lookup",
    "signaldeck_finance_market_data_history_lookup",
    "signaldeck_finance_market_data_ohlcv_lookup",
    "signaldeck_finance_indicators_lookup",
    "signaldeck_finance_fundamentals_lookup",
    "signaldeck_finance_news_lookup",
    "signaldeck_finance_social_sentiment_lookup",
    "signaldeck_finance_insider_data_lookup",
    "signaldeck_finance_reports_lookup",
)

__all__ = [
    "FINANCE_WORKSPACE_DEFAULT_ENABLED",
    "FINANCE_WORKSPACE_DENIED_CODE",
    "FINANCE_WORKSPACE_DENIED_MESSAGES",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_LABEL",
    "FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
]
