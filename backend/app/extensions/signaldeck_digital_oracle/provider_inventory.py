"""Private Digital Oracle upstream provider inventory and migration roadmap."""

from __future__ import annotations

from dataclasses import dataclass

from .runtime_types import (
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    OPTIONS_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
)

RATES_LOOKUP_DEFERRED_TOOL_KEY = "signaldeck.rates.lookup"
NO_NEW_RUNTIME_KEYS_REGISTERED = False
UPSTREAM_LICENSE = "MIT, Copyright (c) 2026 komako-workshop"
UPSTREAM_ATTRIBUTION_NOTE = (
    "Inventory is based on upstream module names and provider ownership only. "
    "No substantial upstream code or prompt text is copied here. Preserve the "
    "upstream MIT notice if future tasks copy substantial portions."
)


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderInventoryItem:
    upstream_module: str
    upstream_provider: str
    capability_family: str
    migration_status: str
    signaldeck_tool_key: str | None
    note: str


IN_SCOPE_PROVIDER_INVENTORY: tuple[DigitalOracleProviderInventoryItem, ...] = (
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.polymarket",
        upstream_provider="PolymarketProvider",
        capability_family="prediction markets",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        note="Polymarket event and contract signals feed the preserved lookup key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.kalshi",
        upstream_provider="KalshiProvider",
        capability_family="prediction markets",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        note="Kalshi event and market signals share the preserved prediction lookup key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.edgar",
        upstream_provider="EdgarProvider",
        capability_family="SEC filings",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=SEC_FILINGS_LOOKUP_TOOL_KEY,
        note="SEC EDGAR filing summaries feed the preserved filings lookup key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.fear_greed",
        upstream_provider="FearGreedProvider",
        capability_family="market sentiment",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        note="CNN Fear and Greed data feeds the preserved sentiment lookup key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.treasury",
        upstream_provider="USTreasuryProvider",
        capability_family="rates/macro",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MACRO_RATES_LOOKUP_TOOL_KEY,
        note="US Treasury signals map to the approved macro rates key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.bis",
        upstream_provider="BisProvider",
        capability_family="rates/macro",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MACRO_RATES_LOOKUP_TOOL_KEY,
        note="Central-bank policy rates and credit-gap signals map to macro rates.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.worldbank",
        upstream_provider="WorldBankProvider",
        capability_family="rates/macro",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MACRO_RATES_LOOKUP_TOOL_KEY,
        note="Macro indicators map to the approved macro rates key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.cme_fedwatch",
        upstream_provider="CMEFedWatchProvider",
        capability_family="rates/macro",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MACRO_RATES_LOOKUP_TOOL_KEY,
        note="Fed-implied probabilities map to the approved macro rates key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.fred",
        upstream_provider="FredProvider",
        capability_family="rates/macro",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=MACRO_RATES_LOOKUP_TOOL_KEY,
        note="FRED macro series map to the approved macro rates key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.deribit",
        upstream_provider="DeribitProvider",
        capability_family="derivatives/crypto",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
        note="Crypto option and futures signals map to the approved derivatives key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.coingecko",
        upstream_provider="CoinGeckoProvider",
        capability_family="derivatives/crypto",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
        note="Crypto spot and market-cap signals map to the approved derivatives key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.yahoo",
        upstream_provider="YahooPriceProvider",
        capability_family="options",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=OPTIONS_LOOKUP_TOOL_KEY,
        note="Options-adjacent Yahoo signals map to the approved options key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.yfinance_provider",
        upstream_provider="YFinanceProvider",
        capability_family="options",
        migration_status="phase_1_in_scope",
        signaldeck_tool_key=OPTIONS_LOOKUP_TOOL_KEY,
        note="Option-chain migration stays import-safe and maps to the approved options key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.cftc",
        upstream_provider="CftcCotProvider",
        capability_family="CFTC positioning",
        migration_status="phase_1_unavailable_skeleton",
        signaldeck_tool_key=CFTC_POSITIONING_LOOKUP_TOOL_KEY,
        note="Futures positioning maps to the approved CFTC positioning key.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="SKILL.md and README methodology",
        upstream_provider="methodology/package patterns",
        capability_family="Workflow Package methodology",
        migration_status="phase_1_package_pattern",
        signaldeck_tool_key=None,
        note=(
            "Methodology belongs in package-local agent systemPrompt text and graph "
            "structure, not in global skills, routes, or runtime registration."
        ),
    ),
)

DEFERRED_PROVIDER_INVENTORY: tuple[DigitalOracleProviderInventoryItem, ...] = (
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.web",
        upstream_provider="WebSearchProvider",
        capability_family="generic web",
        migration_status="deferred_package_private_mcp",
        signaldeck_tool_key=None,
        note="Generic web lookup belongs in package-private MCP use, not a global tool.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.prices",
        upstream_provider="PriceHistory models",
        capability_family="price/history",
        migration_status="deferred_finance_reuse_first",
        signaldeck_tool_key=None,
        note="Reuse Finance market history tools before adding Digital Oracle price tools.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.stooq",
        upstream_provider="StooqProvider",
        capability_family="price/history",
        migration_status="deferred_finance_reuse_first",
        signaldeck_tool_key=None,
        note="Historical price signals stay deferred behind Finance reuse.",
    ),
)

__all__ = [
    "DEFERRED_PROVIDER_INVENTORY",
    "IN_SCOPE_PROVIDER_INVENTORY",
    "NO_NEW_RUNTIME_KEYS_REGISTERED",
    "RATES_LOOKUP_DEFERRED_TOOL_KEY",
    "UPSTREAM_ATTRIBUTION_NOTE",
    "UPSTREAM_LICENSE",
    "DigitalOracleProviderInventoryItem",
]
