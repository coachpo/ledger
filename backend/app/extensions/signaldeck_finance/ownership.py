"""Private operational identity for the bundled finance workspace extension."""

from __future__ import annotations

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"
FINANCE_WORKSPACE_LABEL = "Finance Workspace"
FINANCE_WORKSPACE_DEFAULT_ENABLED = True

FINANCE_WORKSPACE_DENIED_CODE = "agent_execution_access_denied"

FINANCE_WORKSPACE_DENIED_MESSAGES = {
    "signaldeck.market_data.quote_lookup": (
        "Agent is not authorized to use signaldeck.market_data.quote_lookup."
    ),
    "signaldeck.market_data.history_lookup": (
        "Agent is not authorized to use signaldeck.market_data.history_lookup."
    ),
    "signaldeck.market_data.ohlcv_lookup": (
        "Agent is not authorized to use signaldeck.market_data.ohlcv_lookup."
    ),
    "signaldeck.indicators.lookup": (
        "Agent is not authorized to use signaldeck.indicators.lookup."
    ),
    "signaldeck.fundamentals.lookup": (
        "Agent is not authorized to use signaldeck.fundamentals.lookup."
    ),
    "signaldeck.news.lookup": ("Agent is not authorized to use signaldeck.news.lookup."),
    "signaldeck.social_sentiment.lookup": (
        "Agent is not authorized to use signaldeck.social_sentiment.lookup."
    ),
    "signaldeck.insider_data.lookup": (
        "Agent is not authorized to use signaldeck.insider_data.lookup."
    ),
    "signaldeck.prediction_markets.lookup": (
        "Agent is not authorized to use signaldeck.prediction_markets.lookup."
    ),
    "signaldeck.sec_filings.lookup": (
        "Agent is not authorized to use signaldeck.sec_filings.lookup."
    ),
    "signaldeck.market_sentiment.lookup": (
        "Agent is not authorized to use signaldeck.market_sentiment.lookup."
    ),
    "signaldeck.positions.lookup": ("Agent is not authorized to use signaldeck.positions.lookup."),
    "signaldeck.reports.lookup": ("Agent is not authorized to use signaldeck.reports.lookup."),
    "signaldeck.reports.write": (
        "Agent is not authorized to use the retired signaldeck.reports.write."
    ),
}

FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS = (
    "signaldeck.market_data.quote_lookup",
    "signaldeck.market_data.history_lookup",
    "signaldeck.market_data.ohlcv_lookup",
    "signaldeck.indicators.lookup",
    "signaldeck.fundamentals.lookup",
    "signaldeck.news.lookup",
    "signaldeck.social_sentiment.lookup",
    "signaldeck.insider_data.lookup",
    "signaldeck.prediction_markets.lookup",
    "signaldeck.sec_filings.lookup",
    "signaldeck.market_sentiment.lookup",
    "signaldeck.positions.lookup",
    "signaldeck.reports.lookup",
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
    "signaldeck_prediction_markets_lookup",
    "signaldeck_sec_filings_lookup",
    "signaldeck_market_sentiment_lookup",
    "signaldeck_positions_lookup",
    "signaldeck_reports_lookup",
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
