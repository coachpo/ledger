from __future__ import annotations

STOCK_ANALYSIS_TOOL_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "key": "ledger.stock_analysis.market_snapshot",
        "display_name": "Stock Analysis Market Snapshot",
        "description": "Read trusted quote snapshots for the reference stock-analysis workflow.",
        "module": "app.agents.skills.stock_analysis",
    },
    {
        "key": "ledger.stock_analysis.price_history",
        "display_name": "Stock Analysis Price History",
        "description": "Read trusted price history for the stock-analysis workflow.",
        "module": "app.agents.skills.stock_analysis",
    },
    {
        "key": "ledger.stock_analysis.position_inventory",
        "display_name": "Stock Analysis Position Inventory",
        "description": "Read Ledger portfolio positions for the reference stock-analysis workflow.",
        "module": "app.agents.skills.stock_analysis",
    },
    {
        "key": "ledger.stock_analysis.report_lookup",
        "display_name": "Stock Analysis Report Lookup",
        "description": "Read Ledger reports for the reference stock-analysis workflow.",
        "module": "app.agents.skills.stock_analysis",
    },
    {
        "key": "ledger.stock_analysis.market_context",
        "display_name": "Stock Analysis Market Context",
        "description": "Read benchmark market context for the reference stock-analysis workflow.",
        "module": "app.agents.skills.stock_analysis",
    },
)

STOCK_ANALYSIS_TOOL_KEYS = tuple(item["key"] for item in STOCK_ANALYSIS_TOOL_DEFINITIONS)

__all__ = ["STOCK_ANALYSIS_TOOL_DEFINITIONS", "STOCK_ANALYSIS_TOOL_KEYS"]
