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
)

SERVER_DECLARED_TOOL_REGISTRY: dict[str, ServerDeclaredToolSpec] = {
    tool.key: tool for tool in SERVER_DECLARED_TOOL_SPECS
}

__all__ = [
    "SERVER_DECLARED_TOOL_REGISTRY",
    "SERVER_DECLARED_TOOL_SPECS",
    "ServerDeclaredToolSpec",
]
