"""Private Digital Oracle upstream provider inventory and migration roadmap."""

from __future__ import annotations

from dataclasses import dataclass

from .runtime_types import (
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
)

RATES_LOOKUP_DEFERRED_TOOL_KEY = "signaldeck.rates.lookup"
NO_NEW_RUNTIME_KEYS_REGISTERED = True
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
        upstream_module="digital_oracle.providers.treasury",
        upstream_provider="USTreasuryProvider",
        capability_family="rates/macro",
        migration_status="deferred_first_candidate",
        signaldeck_tool_key=RATES_LOOKUP_DEFERRED_TOOL_KEY,
        note="First deferred follow-up candidate; no runtime key is registered now.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.bis",
        upstream_provider="BisProvider",
        capability_family="rates/macro",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Central-bank policy rates and credit-gap signals need a future schema.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.worldbank",
        upstream_provider="WorldBankProvider",
        capability_family="rates/macro",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Macro indicators need a future rates or macro capability decision.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.cme_fedwatch",
        upstream_provider="CMEFedWatchProvider",
        capability_family="rates/macro",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Fed-implied probabilities stay deferred with the rates family.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.deribit",
        upstream_provider="DeribitProvider",
        capability_family="derivatives/crypto",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Crypto derivatives need stable option and futures result schemas first.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.coingecko",
        upstream_provider="CoinGeckoProvider",
        capability_family="derivatives/crypto",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Crypto spot and market-cap signals stay outside phase 1.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.yahoo",
        upstream_provider="YahooPriceProvider",
        capability_family="derivatives/crypto",
        migration_status="deferred_optional_dependency",
        signaldeck_tool_key=None,
        note="Options-adjacent use remains optional and must not require yfinance.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.yfinance_provider",
        upstream_provider="YFinanceProvider",
        capability_family="derivatives/crypto",
        migration_status="deferred_optional_dependency",
        signaldeck_tool_key=None,
        note="Option-chain migration requires lazy optional imports and tests first.",
    ),
    DigitalOracleProviderInventoryItem(
        upstream_module="digital_oracle.providers.cftc",
        upstream_provider="CftcCotProvider",
        capability_family="CFTC positioning",
        migration_status="deferred",
        signaldeck_tool_key=None,
        note="Futures positioning needs a separate capability-family contract.",
    ),
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
