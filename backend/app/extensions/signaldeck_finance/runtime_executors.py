from __future__ import annotations

from app.agents.runtime_tools.types import RuntimeToolSpec
from app.extensions.signaldeck_finance.runtime_market_data import (
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_finance.runtime_market_sentiment import (
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_finance.runtime_positions import POSITION_LOOKUP_TOOL_SPEC
from app.extensions.signaldeck_finance.runtime_prediction_markets import (
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_finance.runtime_reports import REPORT_LOOKUP_TOOL_SPEC
from app.extensions.signaldeck_finance.runtime_sec_filings import SEC_FILINGS_LOOKUP_TOOL_SPEC

FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...] = (
    REPORT_LOOKUP_TOOL_SPEC,
    POSITION_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_TOOL_SPEC,
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
)


def register() -> tuple[RuntimeToolSpec, ...]:
    return FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS


__all__ = [
    "FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS",
    "register",
]
