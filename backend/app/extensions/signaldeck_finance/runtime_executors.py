from __future__ import annotations

from dataclasses import replace

from app.agents.runtime_tools.market_data import (
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.agents.runtime_tools.positions import POSITION_LOOKUP_TOOL_SPEC
from app.agents.runtime_tools.reports import REPORT_LOOKUP_TOOL_SPEC, REPORT_MEMORY_WRITE_TOOL_SPEC
from app.agents.runtime_tools.types import RuntimeToolSpec
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


def _owned(spec: RuntimeToolSpec) -> RuntimeToolSpec:
    return replace(spec, owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY)


FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...] = (
    _owned(REPORT_LOOKUP_TOOL_SPEC),
    _owned(REPORT_MEMORY_WRITE_TOOL_SPEC),
    _owned(POSITION_LOOKUP_TOOL_SPEC),
    _owned(MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC),
    _owned(MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC),
    _owned(MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC),
    _owned(INDICATORS_LOOKUP_TOOL_SPEC),
    _owned(FUNDAMENTALS_LOOKUP_TOOL_SPEC),
    _owned(NEWS_LOOKUP_TOOL_SPEC),
    _owned(SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC),
    _owned(INSIDER_DATA_LOOKUP_TOOL_SPEC),
)


def register() -> tuple[RuntimeToolSpec, ...]:
    return FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS


__all__ = [
    "FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS",
    "register",
]
