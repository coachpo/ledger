from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerDeclaredToolSpec:
    key: str
    display_name: str
    description: str
    module: str


_SERVER_DECLARED_MODULE = "app.agents.tool_catalog.server_declared"

SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = (
    ServerDeclaredToolSpec(
        key="ledger.market_data.quote_lookup",
        display_name="Market Data Quote Lookup",
        description="Read trusted market quote snapshots from server-owned integrations.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.market_data.history_lookup",
        display_name="Market Data History Lookup",
        description="Read trusted historical market series from server-owned integrations.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.market_data.ohlcv_lookup",
        display_name="OHLCV Lookup",
        description="Read server-owned OHLCV market data for supported symbols and ranges.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.indicators.lookup",
        display_name="Indicators Lookup",
        description="Read server-owned market indicators for supported symbols and ranges.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.fundamentals.lookup",
        display_name="Fundamentals Lookup",
        description=(
            "Read server-owned fundamentals data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.news.lookup",
        display_name="News Lookup",
        description=(
            "Read server-owned news data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.social_sentiment.lookup",
        display_name="Social Sentiment Lookup",
        description=(
            "Read server-owned social sentiment data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.insider_data.lookup",
        display_name="Insider Data Lookup",
        description=(
            "Read server-owned insider data when provider support is "
            "available; otherwise return structured warnings."
        ),
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.positions.lookup",
        display_name="Position Lookup",
        description="Read persisted Ledger positions through server-owned position lookups.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.reports.lookup",
        display_name="Report Lookup",
        description="Read persisted Ledger reports through server-owned report lookups.",
        module=_SERVER_DECLARED_MODULE,
    ),
    ServerDeclaredToolSpec(
        key="ledger.reports.write",
        display_name="Report Memory Write",
        description="Create pending agent-memory reports through server-owned memory writes.",
        module=_SERVER_DECLARED_MODULE,
    ),
)

SERVER_DECLARED_TOOL_REGISTRY: dict[str, ServerDeclaredToolSpec] = {
    tool.key: tool for tool in SERVER_DECLARED_TOOL_SPECS
}

__all__ = [
    "SERVER_DECLARED_TOOL_REGISTRY",
    "SERVER_DECLARED_TOOL_SPECS",
    "ServerDeclaredToolSpec",
]
