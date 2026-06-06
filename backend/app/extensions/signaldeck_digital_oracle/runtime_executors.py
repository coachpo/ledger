from __future__ import annotations

from app.agents.runtime_tools.types import RuntimeToolSpec
from app.extensions.signaldeck_digital_oracle.runtime_market_sentiment import (
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_digital_oracle.runtime_prediction_markets import (
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_digital_oracle.runtime_sec_filings import (
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
)

DIGITAL_ORACLE_RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...] = (
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
)


def register() -> tuple[RuntimeToolSpec, ...]:
    return DIGITAL_ORACLE_RUNTIME_TOOL_SPECS


__all__ = [
    "DIGITAL_ORACLE_RUNTIME_TOOL_SPECS",
    "register",
]
