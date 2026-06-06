from __future__ import annotations

from app.extensions import BundledServerDeclaredToolContribution as ServerDeclaredToolSpec
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY

_SERVER_DECLARED_MODULE = __name__

DIGITAL_ORACLE_SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = (
    ServerDeclaredToolSpec(
        key="signaldeck.prediction_markets.lookup",
        display_name="Prediction Markets Lookup",
        description=(
            "Read normalized prediction-market signals from Digital Oracle market "
            "lookups with structured warnings for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.sec_filings.lookup",
        display_name="SEC Filings Lookup",
        description=(
            "Read normalized SEC filing signals from Digital Oracle filing lookups "
            "with structured warnings for partial coverage."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.market_sentiment.lookup",
        display_name="Market Sentiment Lookup",
        description=(
            "Read normalized market sentiment signals from Digital Oracle sentiment "
            "lookups with structured warnings for partial coverage."
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
