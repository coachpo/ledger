"""Private operational identity for the bundled Digital Oracle Runtime extension."""

from __future__ import annotations

DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle"

DIGITAL_ORACLE_DENIED_CODE = "agent_execution_access_denied"

DIGITAL_ORACLE_DENIED_MESSAGES = {
    "signaldeck.digital_oracle.prediction_markets.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.prediction_markets.lookup."
    ),
    "signaldeck.digital_oracle.sec_filings.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.sec_filings.lookup."
    ),
    "signaldeck.digital_oracle.market_sentiment.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.market_sentiment.lookup."
    ),
    "signaldeck.digital_oracle.macro_rates.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.macro_rates.lookup."
    ),
    "signaldeck.digital_oracle.crypto_derivatives.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.crypto_derivatives.lookup."
    ),
    "signaldeck.digital_oracle.cftc_positioning.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.cftc_positioning.lookup."
    ),
    "signaldeck.digital_oracle.options.lookup": (
        "Agent is not authorized to use signaldeck.digital_oracle.options.lookup."
    ),
}

DIGITAL_ORACLE_RUNTIME_TOOL_KEYS = (
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.crypto_derivatives.lookup",
    "signaldeck.digital_oracle.cftc_positioning.lookup",
    "signaldeck.digital_oracle.options.lookup",
)
DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_digital_oracle_prediction_markets_lookup",
    "signaldeck_digital_oracle_sec_filings_lookup",
    "signaldeck_digital_oracle_market_sentiment_lookup",
    "signaldeck_digital_oracle_macro_rates_lookup",
    "signaldeck_digital_oracle_crypto_derivatives_lookup",
    "signaldeck_digital_oracle_cftc_positioning_lookup",
    "signaldeck_digital_oracle_options_lookup",
)

__all__ = [
    "DIGITAL_ORACLE_DENIED_CODE",
    "DIGITAL_ORACLE_DENIED_MESSAGES",
    "DIGITAL_ORACLE_EXTENSION_KEY",
    "DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES",
    "DIGITAL_ORACLE_RUNTIME_TOOL_KEYS",
]
