from __future__ import annotations

from app.extensions import BundledServerDeclaredToolContribution as ServerDeclaredToolSpec
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY

_SERVER_DECLARED_MODULE = __name__

DIGITAL_ORACLE_SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = (
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.prediction_markets.lookup",
        display_name="Prediction Markets Lookup",
        description=(
            "Read normalized prediction-market signals from Digital Oracle market "
            "lookups, including optional orderbook depth, with structured warnings "
            "for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.sec_filings.lookup",
        display_name="SEC Filings Lookup",
        description=(
            "Read normalized SEC filing summaries, EDGAR search hits, and Form 4 "
            "ownership summaries with structured warnings for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.market_sentiment.lookup",
        display_name="Market Sentiment Lookup",
        description=(
            "Read normalized market sentiment signals from Digital Oracle sentiment "
            "lookups with structured warnings for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.macro_rates.lookup",
        display_name="Macro Rates Lookup",
        description=(
            "Read normalized macro, yield, policy-rate, and Fed-implied rates "
            "series with structured warnings for partial provider coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.crypto_derivatives.lookup",
        display_name="Crypto Derivatives Lookup",
        description=(
            "Read normalized CoinGecko spot/global-market and Deribit futures, "
            "options, and orderbook data with structured warnings for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.cftc_positioning.lookup",
        display_name="CFTC Positioning Lookup",
        description=(
            "Read normalized CFTC Commitment of Traders positioning reports with "
            "structured warnings for missing, stale, or malformed provider data."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.digital_oracle.options.lookup",
        display_name="Options Lookup",
        description=(
            "Read normalized Yahoo option-chain calls and puts through an optional "
            "yfinance-backed provider with structured warnings for unavailable coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
)


def register() -> tuple[ServerDeclaredToolSpec, ...]:
    return DIGITAL_ORACLE_SERVER_DECLARED_TOOL_SPECS


__all__ = [
    "DIGITAL_ORACLE_SERVER_DECLARED_TOOL_SPECS",
    "register",
]
