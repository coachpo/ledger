"""Private operational identity for the bundled Digital Oracle Runtime extension."""

from __future__ import annotations

DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle"
DIGITAL_ORACLE_LABEL = "Digital Oracle Runtime"
DIGITAL_ORACLE_DEFAULT_ENABLED = True

DIGITAL_ORACLE_DENIED_CODE = "agent_execution_access_denied"

DIGITAL_ORACLE_DENIED_MESSAGES = {
    "signaldeck.prediction_markets.lookup": (
        "Agent is not authorized to use signaldeck.prediction_markets.lookup."
    ),
    "signaldeck.sec_filings.lookup": (
        "Agent is not authorized to use signaldeck.sec_filings.lookup."
    ),
    "signaldeck.market_sentiment.lookup": (
        "Agent is not authorized to use signaldeck.market_sentiment.lookup."
    ),
}

DIGITAL_ORACLE_RUNTIME_TOOL_KEYS = (
    "signaldeck.prediction_markets.lookup",
    "signaldeck.sec_filings.lookup",
    "signaldeck.market_sentiment.lookup",
)
DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_prediction_markets_lookup",
    "signaldeck_sec_filings_lookup",
    "signaldeck_market_sentiment_lookup",
)

__all__ = [
    "DIGITAL_ORACLE_DEFAULT_ENABLED",
    "DIGITAL_ORACLE_DENIED_CODE",
    "DIGITAL_ORACLE_DENIED_MESSAGES",
    "DIGITAL_ORACLE_EXTENSION_KEY",
    "DIGITAL_ORACLE_LABEL",
    "DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES",
    "DIGITAL_ORACLE_RUNTIME_TOOL_KEYS",
]
