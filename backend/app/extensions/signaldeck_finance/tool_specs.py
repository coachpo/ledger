from __future__ import annotations

from app.extensions import BundledServerDeclaredToolContribution as ServerDeclaredToolSpec
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY

_SERVER_DECLARED_MODULE = __name__

FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = (
    ServerDeclaredToolSpec(
        key="signaldeck.market_data.quote_lookup",
        display_name="Market Data Quote Lookup",
        description="Read trusted market quote snapshots from server-owned integrations.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.market_data.history_lookup",
        display_name="Market Data History Lookup",
        description="Read trusted historical market series from server-owned integrations.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.market_data.ohlcv_lookup",
        display_name="OHLCV Lookup",
        description="Read server-owned OHLCV market data for supported symbols and ranges.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.indicators.lookup",
        display_name="Indicators Lookup",
        description="Read server-owned market indicators for supported symbols and ranges.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.fundamentals.lookup",
        display_name="Fundamentals Lookup",
        description=(
            "Read server-owned fundamentals data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.news.lookup",
        display_name="News Lookup",
        description=(
            "Read server-owned news data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.social_sentiment.lookup",
        display_name="Social Sentiment Lookup",
        description=(
            "Read server-owned social sentiment data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.insider_data.lookup",
        display_name="Insider Data Lookup",
        description=(
            "Read server-owned insider data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.positions.lookup",
        display_name="Position Lookup",
        description="Read persisted SignalDeck positions through server-owned position lookups.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
    ServerDeclaredToolSpec(
        key="signaldeck.reports.lookup",
        display_name="Report Lookup",
        description="Read persisted SignalDeck reports through server-owned report lookups.",
        module=_SERVER_DECLARED_MODULE,
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    ),
)


def register() -> tuple[ServerDeclaredToolSpec, ...]:
    return FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS


__all__ = [
    "FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS",
    "register",
]
