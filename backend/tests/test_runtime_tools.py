from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, cast, override

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp.boundaries import McpClientBoundary
from app.agents.mcp.runtime import McpRuntimeDispatcher, McpRuntimeTool
from app.agents.mcp.tool_adapter import (
    build_mcp_tool_snapshot,
    mcp_snapshot_to_execution_descriptor,
)
from app.agents.runtime_tools import (
    RUNTIME_TOOL_SPECS,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolRegistry,
    RuntimeToolSpec,
    get_default_runtime_tool_registry,
)
from app.agents.runtime_tools.failure_taxonomy import (
    RETRYABLE_FAILURE_CLASSES,
    ToolFailureClass,
    classification_for_error_code,
    provider_status_failure_classification,
)
from app.agents.runtime_tools.types import RuntimeToolWarning
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.core.config import Settings, reset_settings_cache
from app.extensions.signaldeck_digital_oracle.config import (
    DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY,
    DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE,
    DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE,
    EDGAR_CONTACT_EMAIL_MISSING_CODE,
    EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
    EDGAR_CONTACT_EMAIL_SECRET,
    FRED_API_KEY_MISSING_CODE,
    FRED_API_KEY_MISSING_MESSAGE,
    FRED_API_KEY_SECRET,
    MARKET_SENTIMENT_SOURCE_URL,
    CftcPositioningReportType,
    CryptoDerivativesVenue,
    DigitalOracleSettings,
    MacroRatesSource,
    PredictionMarketVenue,
    get_digital_oracle_provider_config,
    reset_digital_oracle_settings_cache,
)
from app.extensions.signaldeck_digital_oracle.factory import (
    DigitalOracleProviderFailure,
    DigitalOracleProviderSecrets,
    create_digital_oracle_phase1_provider_bundle,
    create_prediction_markets_provider_bundle,
    create_sec_filings_provider,
)
from app.extensions.signaldeck_digital_oracle.mappers import (
    map_cftc_positioning_result,
    map_crypto_derivatives_result,
    map_macro_rates_result,
    map_market_sentiment_result,
    map_options_result,
    map_prediction_markets_result,
    map_sec_filings_result,
)
from app.extensions.signaldeck_digital_oracle.ownership import (
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
    DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES,
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_digital_oracle.runtime_cftc_positioning import (
    CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
    CFTC_POSITIONING_LOOKUP_TOOL_SPEC,
    CftcCotPositioningProvider,
    execute_cftc_positioning_lookup,
    parse_cftc_positioning_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_crypto_derivatives import (
    CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC,
    CoinGeckoCryptoDerivativesProvider,
    DeribitCryptoDerivativesProvider,
    execute_crypto_derivatives_lookup,
    parse_crypto_derivatives_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_macro_rates import (
    MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
    MACRO_RATES_LOOKUP_TOOL_SPEC,
    BisMacroRatesProvider,
    FredMacroRatesProvider,
    TreasuryMacroRatesProvider,
    execute_macro_rates_lookup,
    parse_macro_rates_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_market_sentiment import (
    MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
    FearGreedMarketSentimentProvider,
    execute_market_sentiment_lookup,
    parse_market_sentiment_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_options import (
    OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
    OPTIONS_LOOKUP_TOOL_SPEC,
    YahooOptionsProvider,
    execute_options_lookup,
    parse_options_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_options_providers import (
    OptionsChainPayload,
    OptionsTicker,
)
from app.extensions.signaldeck_digital_oracle.runtime_prediction_markets import (
    PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
    KalshiPredictionMarketsProvider,
    PolymarketPredictionMarketsProvider,
    execute_prediction_markets_lookup,
    parse_prediction_markets_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_sec_filings import (
    SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
    EdgarSecFilingsProvider,
    execute_sec_filings_lookup,
    parse_sec_filings_lookup_arguments,
)
from app.extensions.signaldeck_digital_oracle.runtime_types import (
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS,
    OPTIONS_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    RuntimeMarketSentimentLookupResult,
    RuntimePredictionMarketContract,
    RuntimePredictionMarketEvent,
    RuntimePredictionMarketOrderBook,
    RuntimePredictionMarketOrderBookLevel,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFiling,
    RuntimeSecFilingsLookupResult,
    RuntimeSecOwnershipTransaction,
    RuntimeSecSearchHit,
)
from app.extensions.signaldeck_digital_oracle.service import DigitalOraclePhase1Service
from app.extensions.signaldeck_digital_oracle.types import (
    DigitalOracleCftcPositioningProviderQuery,
    DigitalOracleCftcPositioningProviderResult,
    DigitalOracleCftcPositioningQuery,
    DigitalOracleCftcPositioningReport,
    DigitalOracleCftcPositioningRow,
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesOrderBookLevel,
    DigitalOracleCryptoDerivativesProviderQuery,
    DigitalOracleCryptoDerivativesProviderResult,
    DigitalOracleCryptoDerivativesQuery,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
    DigitalOracleMacroRatesResult,
    DigitalOracleMacroRatesSeries,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentProviderResult,
    DigitalOracleMarketSentimentQuery,
    DigitalOracleOptionContract,
    DigitalOracleOptionGreeks,
    DigitalOracleOptionsChain,
    DigitalOracleOptionsProviderQuery,
    DigitalOracleOptionsProviderResult,
    DigitalOracleOptionsQuery,
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketOrderBook,
    DigitalOraclePredictionMarketOrderBookLevel,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOraclePredictionMarketsQuery,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsProviderResult,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecFilingsResult,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)
from app.extensions.signaldeck_finance.config import reset_finance_workspace_settings_cache
from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
)
from app.extensions.signaldeck_finance.grant_policy import (
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_LOOKUP_GRANT_POLICY,
)
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_finance.runtime_market_data import (
    FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    INDICATORS_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
    execute_news_lookup,
    parse_fundamentals_lookup_arguments,
    parse_history_lookup_arguments,
    parse_indicators_lookup_arguments,
    parse_insider_data_lookup_arguments,
    parse_news_lookup_arguments,
    parse_ohlcv_lookup_arguments,
    parse_quote_lookup_arguments,
    parse_social_sentiment_lookup_arguments,
)
from app.extensions.signaldeck_finance.runtime_reports import (
    REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    REPORT_LOOKUP_TOOL_SPEC,
    parse_report_lookup_arguments,
)
from app.extensions.signaldeck_finance.runtime_types import (
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS,
    NEWS_LOOKUP_TOOL_KEY,
    REPORT_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeFinancialStatement,
    RuntimeFinancialStatementLine,
    RuntimeFundamentalMetric,
    RuntimeFundamentalsLookupResult,
    RuntimeHistoryLookupResult,
    RuntimeIndicatorLookupResult,
    RuntimeIndicatorRow,
    RuntimeIndicatorValue,
    RuntimeInsiderDataLookupResult,
    RuntimeInsiderTransaction,
    RuntimeNativeToolResult,
    RuntimeNewsItem,
    RuntimeNewsLookupResult,
    RuntimeOhlcvLookupResult,
    RuntimeOhlcvRow,
    RuntimeOhlcvSeries,
    RuntimeQuoteLookupResult,
    RuntimeSocialSentimentLookupResult,
    RuntimeSocialSentimentMetric,
    RuntimeSocialSentimentSourceBlock,
)
from app.extensions.signaldeck_finance.services.market_data_service import (
    MarketDataService,
    MarketIndicatorSelection,
)
from app.extensions.signaldeck_finance.services.report_service import ReportService
from app.main import create_app
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.schemas.market_data import MarketHistoryPointRead, MarketHistorySeriesRead, MarketQuoteRead
from app.schemas.report import ReportRead
from app.services.agent_execution_service import AgentExecutionService
from app.services.execution_plan import PackageExecutionOwnership
from app.services.execution_providers import ExecutionProviderBundle
from app.services.model_gateway_dto import ModelGatewayError, ModelToolCall
from app.services.model_gateway_openai import ModelToolCallRetryState, build_model_tool_call
from app.services.news_provider import NewsProvider, NewsScope, ProviderNewsItem, ProviderNewsResult
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.quote_provider import (
    ProviderFinancialStatement,
    ProviderFinancialStatementLine,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProvider,
    QuoteProviderError,
    QuoteProviderMissingKeyError,
    QuoteProviderTimeoutError,
)
from app.services.runtime_tool_grants import (
    RuntimeToolGrantError,
    RuntimeToolGrantPolicy,
    RuntimeToolGrantService,
)
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_RUNTIME_RUN_ID = 4242
_RUNTIME_RUN_STEP_ID = 5101
_RUNTIME_AGENT_INVOCATION_ID = 5201
_RUNTIME_OPERATION_INVOCATION_ID = 5301
_RUNTIME_TOOL_CALL_INVOCATION_ID = "tool-call-runtime-tool"
_RUNTIME_TRACE_SPAN_ID = "span-runtime-tools"
_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)

_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS = (
    "signaldeck.finance.market_data.ohlcv_lookup",
    "signaldeck.finance.indicators.lookup",
    "signaldeck.finance.fundamentals.lookup",
    "signaldeck.finance.news.lookup",
    "signaldeck.finance.social_sentiment.lookup",
    "signaldeck.finance.insider_data.lookup",
)
_GENERIC_PLATFORM_RUNTIME_TOOL_OPENAI_FUNCTION_NAMES_BY_KEY = {
    "signaldeck.finance.market_data.ohlcv_lookup": "signaldeck_finance_market_data_ohlcv_lookup",
    "signaldeck.finance.indicators.lookup": "signaldeck_finance_indicators_lookup",
    "signaldeck.finance.fundamentals.lookup": "signaldeck_finance_fundamentals_lookup",
    "signaldeck.finance.news.lookup": "signaldeck_finance_news_lookup",
    "signaldeck.finance.social_sentiment.lookup": "signaldeck_finance_social_sentiment_lookup",
    "signaldeck.finance.insider_data.lookup": "signaldeck_finance_insider_data_lookup",
}
_EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS = {
    "signaldeck.finance.market_data.quote_lookup",
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
    "signaldeck.finance.indicators.lookup",
    "signaldeck.finance.fundamentals.lookup",
    "signaldeck.finance.news.lookup",
    "signaldeck.finance.social_sentiment.lookup",
    "signaldeck.finance.insider_data.lookup",
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.crypto_derivatives.lookup",
    "signaldeck.digital_oracle.cftc_positioning.lookup",
    "signaldeck.digital_oracle.options.lookup",
    "signaldeck.finance.reports.lookup",
}


def _reset_runtime_settings_caches() -> None:
    reset_settings_cache()
    reset_finance_workspace_settings_cache()


def _settings(**overrides: Any) -> Settings:
    return Settings(**overrides)


class _FakeDigitalOraclePredictionProvider:
    def __init__(
        self,
        venue: PredictionMarketVenue,
        *,
        events: Sequence[DigitalOraclePredictionMarketEvent] = (),
        warnings: Sequence[RuntimeToolWarning] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.venue: PredictionMarketVenue = venue
        self.events: tuple[DigitalOraclePredictionMarketEvent, ...] = tuple(events)
        self.warnings: tuple[RuntimeToolWarning, ...] = tuple(warnings)
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOraclePredictionMarketsProviderQuery] = []

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return DigitalOraclePredictionMarketsProviderResult(
            provider=self.venue,
            events=self.events,
            warnings=self.warnings,
        )


class _FakeDigitalOracleSecFilingsProvider:
    provider_name: str = "edgar"

    def __init__(
        self,
        filings: Sequence[DigitalOracleSecFiling],
        *,
        ownership_transactions: Sequence[DigitalOracleSecOwnershipTransaction] = (),
        search_hits: Sequence[DigitalOracleSecSearchHit] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.filings: tuple[DigitalOracleSecFiling, ...] = tuple(filings)
        self.ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = tuple(
            ownership_transactions
        )
        self.search_hits: tuple[DigitalOracleSecSearchHit, ...] = tuple(search_hits)
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleSecFilingsProviderQuery] = []

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return DigitalOracleSecFilingsProviderResult(
            provider=self.provider_name,
            ticker=query.ticker,
            cik="0001045810",
            entity_name="NVIDIA CORP",
            filings=self.filings,
            search_hits=self.search_hits,
            ownership_transactions=self.ownership_transactions,
        )


class _FakeDigitalOracleMarketSentimentProvider:
    provider_name: str = "fear_greed"

    def __init__(
        self,
        result: DigitalOracleMarketSentimentProviderResult | None = None,
        *,
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.result: DigitalOracleMarketSentimentProviderResult = (
            result or DigitalOracleMarketSentimentProviderResult(provider=self.provider_name)
        )
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleMarketSentimentProviderQuery] = []

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentProviderQuery,
    ) -> DigitalOracleMarketSentimentProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return self.result


class _FakeDigitalOracleMacroRatesProvider:
    def __init__(
        self,
        source: MacroRatesSource,
        *,
        series: Sequence[DigitalOracleMacroRatesSeries] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.source: MacroRatesSource = source
        self.series: tuple[DigitalOracleMacroRatesSeries, ...] = tuple(series)
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleMacroRatesProviderQuery] = []

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return DigitalOracleMacroRatesProviderResult(
            provider=self.source,
            series=self.series,
        )


class _FakeDigitalOracleCryptoDerivativesProvider:
    def __init__(
        self,
        venue: CryptoDerivativesVenue,
        *,
        result: DigitalOracleCryptoDerivativesProviderResult | None = None,
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.venue: CryptoDerivativesVenue = venue
        self.result: DigitalOracleCryptoDerivativesProviderResult = (
            result or DigitalOracleCryptoDerivativesProviderResult(provider=venue)
        )
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleCryptoDerivativesProviderQuery] = []

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesProviderQuery,
    ) -> DigitalOracleCryptoDerivativesProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return self.result


class _FakeDigitalOracleCftcPositioningProvider:
    provider_name = "cftc"

    def __init__(
        self,
        *,
        result: DigitalOracleCftcPositioningProviderResult | None = None,
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.result: DigitalOracleCftcPositioningProviderResult = (
            result or DigitalOracleCftcPositioningProviderResult(provider=self.provider_name)
        )
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleCftcPositioningProviderQuery] = []

    def lookup_cftc_positioning(
        self,
        query: DigitalOracleCftcPositioningProviderQuery,
    ) -> DigitalOracleCftcPositioningProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return self.result


class _FakeDigitalOracleOptionsProvider:
    provider_name = "yahoo"

    def __init__(
        self,
        *,
        result: DigitalOracleOptionsProviderResult | None = None,
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.result: DigitalOracleOptionsProviderResult = (
            result or DigitalOracleOptionsProviderResult(provider=self.provider_name)
        )
        self.failure: DigitalOracleProviderError | None = failure
        self.calls: list[DigitalOracleOptionsProviderQuery] = []

    def lookup_options(
        self,
        query: DigitalOracleOptionsProviderQuery,
    ) -> DigitalOracleOptionsProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return self.result


class _FakeOptionsTable:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.rows: tuple[Mapping[str, object], ...] = tuple(rows)

    def to_dict(self, orient: str) -> list[Mapping[str, object]]:
        assert orient == "records"
        return list(self.rows)


class _FakeOptionsChainPayload:
    def __init__(
        self,
        *,
        calls: Sequence[Mapping[str, object]],
        puts: Sequence[Mapping[str, object]],
    ) -> None:
        self.calls = _FakeOptionsTable(calls)
        self.puts = _FakeOptionsTable(puts)


class _FakeOptionsTicker:
    def __init__(
        self,
        *,
        chains_by_expiration: Mapping[str, _FakeOptionsChainPayload],
        spot_price: Decimal | None = Decimal("200"),
    ) -> None:
        self._chains_by_expiration: dict[str, _FakeOptionsChainPayload] = dict(chains_by_expiration)
        self._spot_price = spot_price
        self.option_chain_calls: list[str] = []

    @property
    def options(self) -> Sequence[str]:
        return tuple(self._chains_by_expiration)

    @property
    def fast_info(self) -> Mapping[str, object]:
        if self._spot_price is None:
            return {}
        return {"last_price": str(self._spot_price)}

    @property
    def info(self) -> Mapping[str, object]:
        return {}

    def option_chain(self, date: str) -> OptionsChainPayload:
        self.option_chain_calls.append(date)
        return self._chains_by_expiration[date]


class _FakeOptionsTickerFactory:
    def __init__(self, ticker: _FakeOptionsTicker) -> None:
        self.ticker = ticker
        self.symbols: list[str] = []

    def __call__(self, symbol: str) -> OptionsTicker:
        self.symbols.append(symbol)
        return self.ticker


class _FakePredictionMarketsJsonClient:
    def __init__(self, payloads_by_url_fragment: Mapping[str, object]) -> None:
        self.payloads_by_url_fragment: dict[str, object] = dict(payloads_by_url_fragment)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: PredictionMarketVenue,
    ) -> object:
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "timeout": timeout,
                "provider": provider,
            }
        )
        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake prediction-market payload configured for {url}")


class _FakeEdgarJsonClient:
    def __init__(
        self,
        payloads_by_url_fragment: Mapping[str, object],
        text_by_url_fragment: Mapping[str, str] | None = None,
    ) -> None:
        self.payloads_by_url_fragment: dict[str, object] = dict(payloads_by_url_fragment)
        self.text_by_url_fragment: dict[str, str] = dict(text_by_url_fragment or {})
        self.calls: list[dict[str, object]] = []
        self.text_calls: list[dict[str, object]] = []

    def get_json(self, url: str, *, timeout: float, contact_email: str) -> object:
        self.calls.append({"url": url, "timeout": timeout, "contactEmail": contact_email})
        for fragment, payload in self.payloads_by_url_fragment.items():
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake EDGAR payload configured for {url}")

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        self.text_calls.append({"url": url, "timeout": timeout, "contactEmail": contact_email})
        for fragment, payload in self.text_by_url_fragment.items():
            if fragment in url:
                return payload
        raise AssertionError(f"No fake EDGAR text payload configured for {url}")


class _FakeFearGreedJsonClient:
    def __init__(self, payload: object) -> None:
        self.payload: object = payload
        self.calls: list[dict[str, object]] = []

    def get_json(self, url: str, *, timeout: float, source_url: str) -> object:
        self.calls.append({"url": url, "timeout": timeout, "sourceUrl": source_url})
        return self.payload


class _FakeMacroRatesJsonClient:
    def __init__(self, payloads_by_url_fragment: Mapping[str, object]) -> None:
        self.payloads_by_url_fragment: dict[str, object] = dict(payloads_by_url_fragment)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: MacroRatesSource,
        api_key: str | None = None,
    ) -> object:
        call: dict[str, object] = {
            "url": url,
            "params": dict(params),
            "timeout": timeout,
            "provider": provider,
        }
        if api_key is not None:
            call["apiKey"] = api_key
        self.calls.append(call)
        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake macro-rates payload configured for {url}")


class _FakeCryptoDerivativesJsonClient:
    def __init__(self, payloads_by_url_fragment: Mapping[str, object]) -> None:
        self.payloads_by_url_fragment: dict[str, object] = dict(payloads_by_url_fragment)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: CryptoDerivativesVenue,
    ) -> object:
        self.calls.append(
            {"url": url, "params": dict(params), "timeout": timeout, "provider": provider}
        )
        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake crypto-derivatives payload configured for {url}")


class _FakeCftcPositioningJsonClient:
    def __init__(self, payloads_by_url_fragment: Mapping[str, object]) -> None:
        self.payloads_by_url_fragment: dict[str, object] = dict(payloads_by_url_fragment)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        report_type: CftcPositioningReportType,
    ) -> object:
        self.calls.append(
            {"url": url, "params": dict(params), "timeout": timeout, "reportType": report_type}
        )
        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake CFTC positioning payload configured for {url}")


_DIGITAL_ORACLE_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "digital_oracle"


def _normalize_digital_oracle_fixture_params(
    params: Mapping[str, object] | None,
) -> dict[str, object]:
    if params is None:
        return {}
    return {str(key): value for key, value in sorted(params.items()) if value is not None}


def _digital_oracle_fixture_request_key(
    *,
    kind: str,
    url: str,
    params: Mapping[str, object] | None,
) -> str:
    return json.dumps(
        {
            "kind": kind,
            "url": url,
            "params": _normalize_digital_oracle_fixture_params(params),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class _DigitalOracleFixtureReplayJsonClient:
    def __init__(
        self,
        fixture_names: Sequence[str],
        *,
        fixture_dir: Path = _DIGITAL_ORACLE_FIXTURE_DIR,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._fixtures: dict[str, dict[str, object]] = {}
        for fixture_name in fixture_names:
            path = fixture_dir / fixture_name
            if not path.exists():
                raise AssertionError(f"Missing Digital Oracle fixture file: {path}")
            try:
                raw_payload = cast(object, json.loads(path.read_text()))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"Malformed Digital Oracle fixture JSON: {path}") from exc
            if not isinstance(raw_payload, dict):
                raise AssertionError(f"Digital Oracle fixture must be an object: {path}")
            fixture = cast(dict[str, object], raw_payload)
            kind = fixture.get("kind")
            request = fixture.get("request")
            if kind != "json" or not isinstance(request, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid envelope: {path}")
            request_payload = cast(dict[str, object], request)
            url = request_payload.get("url")
            params = request_payload.get("params")
            if not isinstance(url, str) or not isinstance(params, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid request: {path}")
            has_response = "response" in fixture
            has_error = "error" in fixture
            if has_response == has_error:
                raise AssertionError(
                    f"Digital Oracle fixture must contain exactly one response or error: {path}"
                )
            params_payload = cast(dict[str, object], params)
            key = _digital_oracle_fixture_request_key(
                kind="json",
                url=url,
                params=params_payload,
            )
            if key in self._fixtures:
                raise AssertionError(f"Duplicate Digital Oracle fixture request: {path}")
            self._fixtures[key] = fixture

    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        params: Mapping[str, object] | None = None,
        provider: PredictionMarketVenue | str | None = None,
        contact_email: str | None = None,
        source_url: str | None = None,
    ) -> object:
        normalized_params = _normalize_digital_oracle_fixture_params(params)
        call: dict[str, object] = {"url": url, "timeout": timeout, "params": normalized_params}
        if provider is not None:
            call["provider"] = provider
        if contact_email is not None:
            call["contactEmail"] = contact_email
        if source_url is not None:
            call["sourceUrl"] = source_url
        self.calls.append(call)
        key = _digital_oracle_fixture_request_key(kind="json", url=url, params=normalized_params)
        fixture = self._fixtures.get(key)
        if fixture is None:
            raise AssertionError(
                f"Missing Digital Oracle fixture for {url} params={normalized_params}"
            )
        error = fixture.get("error")
        if isinstance(error, dict):
            error_payload = cast(dict[str, object], error)
            message = error_payload.get("message")
            code = error_payload.get("code")
            details = error_payload.get("details")
            raise DigitalOracleProviderError(
                message if isinstance(message, str) else "Digital Oracle fixture provider error",
                code=code if isinstance(code, str) else "provider_error",
                details=cast(Mapping[str, object], details if isinstance(details, dict) else {}),
            )
        return fixture["response"]

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        del timeout, contact_email
        raise AssertionError(f"No Digital Oracle text fixture configured for {url}")


class _SessionScope:
    def __enter__(self) -> object:
        return object()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False


def _session_factory() -> _SessionScope:
    return _SessionScope()


def _failing_session_factory() -> _SessionScope:
    raise AssertionError("invalid runtime tool arguments should not open a session")


class _RecordingMcpDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def dispatch(self, *, name: str, arguments_json: str) -> dict[str, object]:
        self.calls.append({"arguments_json": arguments_json, "name": name})
        return {"output": {"ok": True}, "toolKey": "mcp.fake"}


class _RecordingMcpToolClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def call_tool(
        self,
        *,
        boundary: McpClientBoundary,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        self.calls.append(
            {
                "boundary": boundary,
                "tool_name": tool_name,
                "arguments": arguments,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"ok": True}


def _failure_taxonomy_mcp_dispatcher(
    client: _RecordingMcpToolClient,
) -> McpRuntimeDispatcher:
    snapshot = build_mcp_tool_snapshot(
        server_key="taxonomy",
        server_version=1,
        original_tool_name="vendor.lookup",
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
    )
    descriptor = mcp_snapshot_to_execution_descriptor(snapshot, owner_extension_key=None)
    boundary = McpClientBoundary(
        server_id=None,
        key="taxonomy",
        version=1,
        name="Taxonomy MCP",
        transport="stdio",
        enabled=True,
        command=("npx",),
    )
    return McpRuntimeDispatcher(
        tools=[McpRuntimeTool(boundary=boundary, snapshot=snapshot, descriptor=descriptor)],
        client=client,
        timeout_seconds=1.0,
    )


def _runtime_context(
    *,
    capability_references: Sequence[dict[str, object]] | None = None,
    fail_on_session: bool = False,
    session_factory_override: sessionmaker[Session] | None = None,
    quote_provider: QuoteProvider | None = None,
    news_providers: Sequence[NewsProvider] = (),
    run_id: int | None = None,
    run_step_id: int | None = None,
    run_agent_invocation_id: int | None = None,
    run_operation_invocation_id: int | None = None,
    agent_key: str | None = None,
    agent_version: int | None = None,
    agent_name: str | None = None,
    workflow_key: str | None = None,
    workflow_version: int | None = None,
    step_id: str | None = None,
    slot: str | None = None,
    trace_id: str | None = None,
    trace_span_id: str | None = None,
    invocation_id: str | None = None,
    package_ownership: PackageExecutionOwnership | None = None,
    secret_values: Mapping[str, object] | None = None,
) -> RuntimeToolContext:
    selected_session_factory = session_factory_override or (
        _failing_session_factory if fail_on_session else _session_factory
    )
    provider_bundle = (
        finance_execution_provider_bundle_from_parts(
            quote_provider=quote_provider,
            news_providers=news_providers,
        )
        if quote_provider is not None or news_providers
        else ExecutionProviderBundle()
    )
    context = RuntimeToolContext(
        session_factory=cast(sessionmaker[Session], selected_session_factory),
        capability_references=list(
            capability_references
            or [
                {
                    "toolKeys": [
                        REPORT_LOOKUP_TOOL_KEY,
                        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
                        MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
                    ],
                }
            ]
        ),
        provider_bundle=provider_bundle,
        run_id=run_id,
        run_step_id=run_step_id,
        run_agent_invocation_id=run_agent_invocation_id,
        run_operation_invocation_id=run_operation_invocation_id,
        agent_key=agent_key,
        agent_version=agent_version,
        agent_name=agent_name,
        package_ownership=package_ownership,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        step_id=step_id,
        slot=slot,
        trace_id=trace_id,
        trace_span_id=trace_span_id,
        invocation_id=invocation_id,
    )
    if secret_values is None:
        return context
    return replace(context, secret_values=dict(secret_values))


def _capability_reference(*, tools: Sequence[str]) -> dict[str, object]:
    return {"toolKeys": list(tools)}


def _seed_runtime_run(
    session_factory: sessionmaker[Session],
    *,
    run_id: int = _RUNTIME_RUN_ID,
    run_step_id: int = _RUNTIME_RUN_STEP_ID,
    run_agent_invocation_id: int = _RUNTIME_AGENT_INVOCATION_ID,
    run_operation_invocation_id: int = _RUNTIME_OPERATION_INVOCATION_ID,
    package_id: int = 1,
    package_key: str = "runtime_tool_test_package",
    workflow_key: str = "runtime_tool_test_workflow",
) -> None:
    with session_factory() as session:
        session.add(
            Run(
                id=run_id,
                target_kind="workflowPackage",
                target_id=package_id,
                target_key=workflow_key,
                target_version=1,
                input={},
                status="running",
                workflow_package_snapshot=RunWorkflowPackageSnapshot(
                    workflow_package_id=package_id,
                    workflow_package_key=package_key,
                    workflow_package_name="Runtime Tool Test Package",
                    workflow_package_status="published",
                    workflow_key=workflow_key,
                    workflow_name="Runtime Tool Test Workflow",
                    manifest_hash=f"runtime-tool-test-manifest-{run_id}",
                    compiled_hash=f"runtime-tool-test-compiled-{run_id}",
                    manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
                    package_definition={},
                    compiled_plan={},
                ),
            )
        )
        session.add(
            RunStep(
                id=run_step_id,
                run_id=run_id,
                step_index=1,
                status="running",
            )
        )
        session.add(
            RunAgentInvocation(
                id=run_agent_invocation_id,
                run_step_id=run_step_id,
                run_id=run_id,
                step_index=1,
                slot="decision",
                position=0,
                agent_id=101,
                agent_key="portfolio_manager",
                agent_version=3,
                output_schema_id=201,
                output_schema_version=1,
                input_mode="wired",
                status="running",
            )
        )
        session.add(
            RunOperationInvocation(
                id=run_operation_invocation_id,
                run_step_id=run_step_id,
                run_id=run_id,
                step_index=1,
                slot="tool_dispatch",
                position=1,
                operation_key="tool_dispatch",
                operation_kind="http",
                output_schema_id=202,
                output_schema_version=1,
                status="running",
            )
        )
        session.commit()


def _parse_noop(arguments_json: str) -> dict[str, object]:
    return {"argumentsJson": arguments_json}


def _execute_noop(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    return {"arguments": arguments}


def _runtime_tool_spec(
    *,
    key: str = "signaldeck.test.lookup",
    openai_function_name: str = "signaldeck_test_lookup",
    sort_order: int = 10,
) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        key=key,
        openai_function_name=openai_function_name,
        display_name="Test Runtime Tool",
        description="Test runtime tool.",
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        guidance=f"Call the {openai_function_name} tool for tests.",
        sort_order=sort_order,
        denied_code="agent_execution_access_denied",
        denied_message=f"Agent is not authorized to use {key}.",
        parser=_parse_noop,
        executor=_execute_noop,
    )


def _runtime_package_ownership(*, package_key: str) -> PackageExecutionOwnership:
    return PackageExecutionOwnership(
        package_id=9001,
        package_key=package_key,
        manifest_hash=f"manifest-{package_key}",
        compiled_hash=f"compiled-{package_key}",
        workflow_key="platform_graph_daily_review",
    )


def _assert_recursive_strict_schema(schema: object, *, path: str) -> None:
    assert isinstance(schema, Mapping), f"{path} must be an object schema"
    payload = cast(dict[object, object], schema)
    raw_type = payload.get("type")
    if isinstance(raw_type, str):
        type_values = {raw_type}
    else:
        assert isinstance(raw_type, list), f"{path}.type must be a string or list"
        type_values = {cast(str, value) for value in raw_type}

    if "object" in type_values:
        properties = payload.get("properties")
        assert isinstance(properties, Mapping), f"{path}.properties must be an object"
        property_mapping = cast(dict[object, object], properties)
        required = payload.get("required")
        assert isinstance(required, list), f"{path}.required must be a list"
        required_names = [cast(str, value) for value in required]
        property_names = [cast(str, key) for key in property_mapping]
        assert (
            payload.get("additionalProperties") is False
        ), f"{path}.additionalProperties must be false"
        assert set(required_names) == set(property_names), f"{path}.required must match properties"
        for key, value in property_mapping.items():
            _assert_recursive_strict_schema(value, path=f"{path}.properties.{key}")

    if "array" in type_values:
        assert "items" in payload, f"{path}.items is required for arrays"
        _assert_recursive_strict_schema(payload["items"], path=f"{path}.items")


def _assert_strict_openai_tool_schema(tool: dict[str, object]) -> None:
    assert set(tool) == {"type", "name", "description", "strict", "parameters"}
    assert tool["type"] == "function"
    assert tool["strict"] is True
    parameters = cast(dict[str, object], tool["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == list(properties)
    _assert_recursive_strict_schema(parameters, path="$.parameters")


def _assert_native_runtime_payload_is_json_safe_and_camel(
    payload: dict[str, object],
) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return

    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


def _report_read() -> ReportRead:
    return ReportRead.model_validate(
        {
            "id": 7,
            "name": "NVDA Backend Lookup",
            "slug": "nvda_backend_lookup",
            "source": "external",
            "content": "# NVDA\n\nRevenue acceleration remains intact.",
            "metadata_": {
                "tags": ["earnings"],
                "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
            },
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )


def _quote_read() -> MarketQuoteRead:
    return MarketQuoteRead(
        symbol="NVDA",
        name="NVIDIA Corporation",
        price=Decimal("120.25000000"),
        currency="USD",
        provider="deterministic_test",
        as_of=_NOW,
        is_stale=False,
        previous_close=Decimal("119.75000000"),
    )


def _history_series_read() -> MarketHistorySeriesRead:
    return MarketHistorySeriesRead(
        symbol="NVDA",
        currency="USD",
        provider="deterministic_test",
        points=[
            MarketHistoryPointRead(at=datetime(2026, 1, 1, tzinfo=UTC), close=Decimal("119.75")),
            MarketHistoryPointRead(at=_NOW, close=Decimal("120.25")),
        ],
    )


class _RecordingQuoteProvider:
    def __init__(self, *, failing_symbols: set[str] | None = None) -> None:
        self.failing_symbols: set[str] = failing_symbols or set()
        self.quote_calls: list[str] = []
        self.history_calls: list[tuple[str, str, str]] = []
        self.ohlcv_calls: list[tuple[str, datetime, datetime, str]] = []

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol.upper()} Incorporated"

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        self.quote_calls.append(normalized_symbol)
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"Quote unavailable for {normalized_symbol}")
        price = Decimal("120.25000000") if normalized_symbol == "NVDA" else Decimal("410.50000000")
        return ProviderQuote(
            symbol=normalized_symbol,
            name=f"{normalized_symbol} Incorporated",
            price=price,
            previous_close=price - Decimal("0.50000000"),
            currency="USD",
            provider="fake_runtime_provider",
            as_of=_NOW,
        )

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        normalized_symbol = symbol.upper()
        self.history_calls.append((normalized_symbol, range_value, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"History unavailable for {normalized_symbol}")
        return ProviderHistorySeries(
            symbol=normalized_symbol,
            currency="USD",
            provider="fake_runtime_provider",
            points=[
                ProviderHistoryPoint(
                    at=datetime(2026, 1, 1, tzinfo=UTC),
                    close=Decimal("118.75"),
                ),
                ProviderHistoryPoint(
                    at=datetime(2026, 1, 2, tzinfo=UTC),
                    close=Decimal("119.75"),
                ),
                ProviderHistoryPoint(at=_NOW, close=Decimal("120.25")),
            ],
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        normalized_symbol = symbol.upper()
        self.ohlcv_calls.append((normalized_symbol, start_date, end_date, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"OHLCV unavailable for {normalized_symbol}")
        mid_session = datetime(2026, 1, 2, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
        return ProviderOhlcvSeries(
            symbol=normalized_symbol,
            currency="USD",
            provider="fake_runtime_provider",
            rows=[
                ProviderOhlcvRow(
                    at=end_date + timedelta(days=1),
                    open=Decimal("999.00"),
                    high=Decimal("1000.00"),
                    low=Decimal("998.00"),
                    close=Decimal("999.50"),
                    volume=9999,
                ),
                ProviderOhlcvRow(
                    at=start_date,
                    open=Decimal("118.00"),
                    high=Decimal("121.00"),
                    low=Decimal("117.00"),
                    close=Decimal("119.75"),
                    volume=1000,
                    adjusted_close=Decimal("119.50"),
                ),
                ProviderOhlcvRow(
                    at=mid_session,
                    open=Decimal("119.00"),
                    high=Decimal("122.00"),
                    low=Decimal("118.00"),
                    close=Decimal("120.00"),
                    volume=1100,
                    adjusted_close=Decimal("119.80"),
                ),
                ProviderOhlcvRow(
                    at=start_date - timedelta(days=1),
                    open=Decimal("1.00"),
                    high=Decimal("2.00"),
                    low=Decimal("0.50"),
                    close=Decimal("1.50"),
                    volume=1,
                ),
                ProviderOhlcvRow(
                    at=end_date,
                    open=Decimal("119.75"),
                    high=Decimal("121.50"),
                    low=Decimal("119.00"),
                    close=Decimal("120.25"),
                    volume=1200,
                ),
            ],
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        return ProviderFundamentals(
            symbol=symbol.upper(),
            provider="fake_runtime_provider",
            as_of=_NOW,
            metrics=[],
            statements=[],
        )

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del symbols, query, scope, start_date, end_date, limit
        return ProviderNewsResult(provider="fake_runtime_provider", items=[])

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        del start_date, end_date, limit
        return ProviderInsiderData(
            symbol=symbol.upper(),
            provider="fake_runtime_provider",
            transactions=[],
        )


class _FinancialContractProvider(_RecordingQuoteProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        failure: QuoteProviderError | None = None,
        empty: bool = False,
        news_count: int = 0,
        insider_count: int = 0,
    ) -> None:
        super().__init__()
        self.provider_name: str = provider_name
        self.failure: QuoteProviderError | None = failure
        self.empty: bool = empty
        self.news_count: int = news_count
        self.insider_count: int = insider_count
        self.fundamental_calls: list[str] = []
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []
        self.insider_calls: list[tuple[str, datetime | None, datetime | None, int]] = []

    @override
    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        normalized_symbol = symbol.upper()
        self.fundamental_calls.append(normalized_symbol)
        if self.failure is not None:
            raise self.failure
        if self.empty:
            return ProviderFundamentals(
                symbol=normalized_symbol,
                provider=self.provider_name,
                as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
                metrics=[],
                statements=[],
            )
        return ProviderFundamentals(
            symbol=normalized_symbol,
            provider=self.provider_name,
            as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
            metrics=[
                ProviderFundamentalMetric(
                    name="market_cap",
                    value=Decimal("1000000.50"),
                    currency="USD",
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="revenue_growth",
                    value=Decimal("0.18"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="free_cash_flow_margin",
                    value=Decimal("0.19"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
            ],
            statements=[
                ProviderFinancialStatement(
                    statement_type="income_statement",
                    period="annual",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="revenue",
                            value=Decimal("500000.25"),
                            currency="USD",
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="balance_sheet",
                    period="quarterly",
                    period_end=datetime(2025, 10, 31, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="assets",
                            value=Decimal("750000.00"),
                            currency="USD",
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="cash_flow",
                    period="trailing_twelve_months",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="operating_cash_flow",
                            value=Decimal("125000.75"),
                            currency="USD",
                        )
                    ],
                ),
            ],
        )

    @override
    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(
            provider=self.provider_name,
            items=[
                ProviderNewsItem(
                    title=f"News {index}",
                    source="wire",
                    published_at=datetime(2026, 1, 2, index, tzinfo=UTC),
                    symbols=symbols,
                    sentiment="neutral",
                )
                for index in range(self.news_count)
            ],
        )

    @override
    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        normalized_symbol = symbol.upper()
        self.insider_calls.append((normalized_symbol, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderInsiderData(
            symbol=normalized_symbol,
            provider=self.provider_name,
            transactions=[
                ProviderInsiderTransaction(
                    insider_name=f"Insider {index}",
                    role="Director",
                    transaction_type="BUY",
                    shares=Decimal("10"),
                    price=Decimal("120.25"),
                    value=Decimal("1202.50"),
                    filed_at=datetime(2026, 1, 3, index, tzinfo=UTC),
                    transaction_date=datetime(2026, 1, 2, index, tzinfo=UTC),
                )
                for index in range(self.insider_count)
            ],
        )


def _ohlcv_series() -> RuntimeOhlcvSeries:
    return RuntimeOhlcvSeries(
        symbol="NVDA",
        currency="USD",
        provider="deterministic_test",
        rows=[
            RuntimeOhlcvRow(
                at=datetime(2026, 1, 1, tzinfo=UTC),
                open=Decimal("118"),
                high=Decimal("121"),
                low=Decimal("117"),
                close=Decimal("119.75"),
                volume=1000,
                adjusted_close=Decimal("119.50"),
            ),
            RuntimeOhlcvRow(
                at=_NOW,
                open=Decimal("119.75"),
                high=Decimal("121.5"),
                low=Decimal("119"),
                close=Decimal("120.25"),
                volume=1200,
            ),
        ],
    )


def test_native_runtime_financial_tool_result_keys_are_signaldeck_prefixed_and_contract_only() -> (
    None
):
    assert NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS == (
        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
        MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
        MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
        INDICATORS_LOOKUP_TOOL_KEY,
        FUNDAMENTALS_LOOKUP_TOOL_KEY,
        NEWS_LOOKUP_TOOL_KEY,
        SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
        INSIDER_DATA_LOOKUP_TOOL_KEY,
    )
    assert NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS == (
        PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        SEC_FILINGS_LOOKUP_TOOL_KEY,
        MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        MACRO_RATES_LOOKUP_TOOL_KEY,
        CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
        CFTC_POSITIONING_LOOKUP_TOOL_KEY,
        OPTIONS_LOOKUP_TOOL_KEY,
    )
    assert all(
        tool_key.startswith("signaldeck.") for tool_key in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS
    )
    assert all(
        tool_key.startswith("signaldeck.") for tool_key in NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS
    )
    assert set(_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS) <= set(NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS)

    with pytest.raises(
        ValidationError, match="Native runtime tool keys must start with signaldeck"
    ):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "external.market_data.quote_lookup"})
    with pytest.raises(ValidationError, match="not registered as a financial tool result"):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "signaldeck.unregistered.lookup"})


def test_builtin_native_runtime_tool_catalog_and_specs_stay_aligned() -> None:
    runtime_specs = get_default_runtime_tool_registry().list_specs()
    runtime_spec_keys = {spec.key for spec in runtime_specs}
    server_declared_keys = {spec.key for spec in SERVER_DECLARED_TOOL_SPECS}
    runtime_function_names = {spec.openai_function_name for spec in runtime_specs}
    digital_oracle_tool_keys = set(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS)

    assert runtime_spec_keys == _EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS
    assert runtime_spec_keys <= server_declared_keys
    assert digital_oracle_tool_keys <= server_declared_keys
    assert digital_oracle_tool_keys <= runtime_spec_keys
    assert all(
        spec.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
        for spec in SERVER_DECLARED_TOOL_SPECS
        if spec.key in digital_oracle_tool_keys
    )
    assert all(
        spec.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
        for spec in runtime_specs
        if spec.key in digital_oracle_tool_keys
    )
    assert len(runtime_function_names) == len(runtime_spec_keys)
    assert runtime_function_names == {
        tool_key.replace(".", "_") for tool_key in _EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS
    }


def test_prediction_markets_sec_filings_market_sentiment_tool_ownership_constants() -> None:
    assert FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS == (
        "signaldeck.finance.market_data.quote_lookup",
        "signaldeck.finance.market_data.history_lookup",
        "signaldeck.finance.market_data.ohlcv_lookup",
        "signaldeck.finance.indicators.lookup",
        "signaldeck.finance.fundamentals.lookup",
        "signaldeck.finance.news.lookup",
        "signaldeck.finance.social_sentiment.lookup",
        "signaldeck.finance.insider_data.lookup",
        "signaldeck.finance.reports.lookup",
    )
    assert FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES == (
        "signaldeck_finance_market_data_quote_lookup",
        "signaldeck_finance_market_data_history_lookup",
        "signaldeck_finance_market_data_ohlcv_lookup",
        "signaldeck_finance_indicators_lookup",
        "signaldeck_finance_fundamentals_lookup",
        "signaldeck_finance_news_lookup",
        "signaldeck_finance_social_sentiment_lookup",
        "signaldeck_finance_insider_data_lookup",
        "signaldeck_finance_reports_lookup",
    )
    assert DIGITAL_ORACLE_RUNTIME_TOOL_KEYS == (
        "signaldeck.digital_oracle.prediction_markets.lookup",
        "signaldeck.digital_oracle.sec_filings.lookup",
        "signaldeck.digital_oracle.market_sentiment.lookup",
        "signaldeck.digital_oracle.macro_rates.lookup",
        "signaldeck.digital_oracle.crypto_derivatives.lookup",
        "signaldeck.digital_oracle.cftc_positioning.lookup",
        "signaldeck.digital_oracle.options.lookup",
    )
    assert DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES == (
        "signaldeck_digital_oracle_prediction_markets_lookup",
        "signaldeck_digital_oracle_sec_filings_lookup",
        "signaldeck_digital_oracle_market_sentiment_lookup",
        "signaldeck_digital_oracle_macro_rates_lookup",
        "signaldeck_digital_oracle_crypto_derivatives_lookup",
        "signaldeck_digital_oracle_cftc_positioning_lookup",
        "signaldeck_digital_oracle_options_lookup",
    )
    assert DIGITAL_ORACLE_DENIED_MESSAGES[
        "signaldeck.digital_oracle.prediction_markets.lookup"
    ] == ("Agent is not authorized to use signaldeck.digital_oracle.prediction_markets.lookup.")
    assert DIGITAL_ORACLE_DENIED_MESSAGES["signaldeck.digital_oracle.sec_filings.lookup"] == (
        "Agent is not authorized to use signaldeck.digital_oracle.sec_filings.lookup."
    )
    assert DIGITAL_ORACLE_DENIED_MESSAGES["signaldeck.digital_oracle.market_sentiment.lookup"] == (
        "Agent is not authorized to use signaldeck.digital_oracle.market_sentiment.lookup."
    )


def test_digital_oracle_researcher_demo_dispatches_mocked_phase1_runtime_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_source = _DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE.read_text()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    assert plan.package_workflow is not None
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }
    assert runtime_agent.key == "digital_oracle_signal_researcher"
    assert runtime_agent.output_schema.key == "digital_oracle_report"
    assert granted_tool_keys == {
        CFTC_POSITIONING_LOOKUP_TOOL_KEY,
        CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
        PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        SEC_FILINGS_LOOKUP_TOOL_KEY,
        MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        MACRO_RATES_LOOKUP_TOOL_KEY,
        OPTIONS_LOOKUP_TOOL_KEY,
    }

    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-nvda-earnings",
                title="Will NVDA beat earnings expectations?",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-nvda-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXNVDA-26",
                title="NVDA closes above $150 this quarter",
                status="open",
            ),
        ),
    )
    sec_provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            ),
        ),
        ownership_transactions=(
            DigitalOracleSecOwnershipTransaction(
                accession_number="0001045810-26-000020",
                filing_date=date(2026, 2, 21),
                issuer_name="NVIDIA CORP",
                issuer_ticker="NVDA",
                reporting_owner_name="Ada Lovelace",
                transaction_date=date(2026, 2, 20),
                transaction_code="P",
                acquired_disposed_code="A",
                shares=Decimal("10"),
                price=Decimal("120.25"),
                ownership_nature="D",
            ),
        ),
    )
    sentiment_provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=79,
            label="extreme_greed",
            as_of_date=date(2026, 1, 2),
            previous_close=74,
            week_ago=66,
            month_ago=58,
            year_ago=42,
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: sec_provider,
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: sentiment_provider,
    )
    _reset_runtime_settings_caches()
    try:
        registry = get_default_runtime_tool_registry()
        context = _runtime_context(
            fail_on_session=True,
            agent_key=runtime_agent.key,
            agent_name=runtime_agent.name,
            workflow_key=plan.package_workflow.key,
            step_id="digital_oracle_research",
            slot="report",
            package_ownership=plan.package_ownership,
            secret_values={"edgar_contact_email": "sec-contact@example.test"},
        )
        declarations = registry.get_tool_declarations(granted_tool_keys)
        prediction_declaration = registry.get_tool_declarations(
            {PREDICTION_MARKETS_LOOKUP_TOOL_KEY}
        )[0]
        prediction_schema = cast(dict[str, object], prediction_declaration.input_schema)
        prediction_properties = cast(dict[str, dict[str, object]], prediction_schema["properties"])
        assert prediction_schema["required"] == [
            "depthLimit",
            "includeOrderBook",
            "includeResolved",
            "itemLimit",
            "query",
            "venues",
        ]
        assert prediction_schema["additionalProperties"] is False
        assert prediction_properties["depthLimit"]["type"] == ["integer", "null"]
        assert prediction_properties["includeOrderBook"]["type"] == ["boolean", "null"]
        assert prediction_properties["query"]["type"] == "string"
        assert prediction_properties["venues"]["type"] == ["array", "null"]
        assert prediction_properties["itemLimit"]["type"] == ["integer", "null"]
        assert prediction_properties["includeResolved"]["type"] == ["boolean", "null"]
        prediction_payload = registry.dispatch(
            name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json=json.dumps(
                {
                    "query": "NVDA earnings",
                    "venues": ["polymarket", "kalshi"],
                    "itemLimit": 3,
                    "includeResolved": False,
                    "includeOrderBook": True,
                    "depthLimit": 2,
                }
            ),
            granted_tool_keys=granted_tool_keys,
            context=context,
        )
        sec_payload = registry.dispatch(
            name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json=json.dumps(
                {
                    "ticker": "NVDA",
                    "formTypes": ["10-K"],
                    "startDate": "2026-01-01",
                    "endDate": "2026-12-31",
                    "itemLimit": 5,
                }
            ),
            granted_tool_keys=granted_tool_keys,
            context=context,
        )
        sentiment_payload = registry.dispatch(
            name=MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json=json.dumps({"indicator": "fear_greed", "asOfDate": "2026-01-02"}),
            granted_tool_keys=granted_tool_keys,
            context=context,
        )
    finally:
        _reset_runtime_settings_caches()

    assert {declaration.tool_key for declaration in declarations} == granted_tool_keys
    assert polymarket_provider.calls[0].query == "NVDA earnings"
    assert kalshi_provider.calls[0].include_resolved is False
    assert polymarket_provider.calls[0].include_order_book is True
    assert kalshi_provider.calls[0].depth_limit == 2
    assert prediction_payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert [event["venue"] for event in prediction_events] == ["polymarket", "kalshi"]
    assert sec_provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert sec_payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert cast(list[dict[str, object]], sec_payload["filings"])[0]["formType"] == "10-K"
    assert sentiment_provider.calls[0].as_of_date == date(2026, 1, 2)
    assert sentiment_payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert sentiment_payload["score"] == 79


def test_digital_oracle_config_keeps_provider_credentials_out_of_backend_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patched:
        patched.setenv("DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT", "7")
        patched.setenv("DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT", "11")
        reset_digital_oracle_settings_cache()
        try:
            config = get_digital_oracle_provider_config()

            assert config.prediction_markets_default_item_limit == 7
            assert config.sec_filings_default_item_limit == 11
            assert config.edgar_contact_email is None
            assert config.fred_api_key is None
        finally:
            reset_digital_oracle_settings_cache()


def test_digital_oracle_provider_config_reads_new_provider_controls_from_backend_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patched:
        patched.setenv("DIGITAL_ORACLE_MACRO_RATES_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT", "13")
        patched.setenv("DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT", "14")
        patched.setenv("DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT", "15")
        patched.setenv("DIGITAL_ORACLE_OPTIONS_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT", "16")
        reset_digital_oracle_settings_cache()
        try:
            config = get_digital_oracle_provider_config()
        finally:
            reset_digital_oracle_settings_cache()

    assert config.macro_rates_enabled is False
    assert config.macro_rates_default_item_limit == 13
    assert config.fred_api_key is None
    assert config.crypto_derivatives_enabled is False
    assert config.crypto_derivatives_default_item_limit == 14
    assert config.cftc_positioning_enabled is False
    assert config.cftc_positioning_default_item_limit == 15
    assert config.options_enabled is False
    assert config.options_default_item_limit == 16


def test_digital_oracle_configured_provider_factory_construction_uses_defaults() -> None:
    settings = DigitalOracleSettings.model_validate(
        {
            "DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5",
            "DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT": "6",
            "DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT": "12",
            "DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT": "13",
            "DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT": "14",
            "DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT": "15",
            "DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT": "16",
        }
    )

    config = get_digital_oracle_provider_config(settings)
    assert config.prediction_markets_enabled is True
    assert config.sec_filings_enabled is True
    assert config.market_sentiment_enabled is True
    assert config.provider_timeout_seconds == 2.5
    assert config.requires_vendored_package is DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE
    assert config.requires_yfinance is DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE
    assert config.requires_vendored_package is False
    assert config.requires_yfinance is False
    assert config.provider_boundary == DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY

    bundle = create_digital_oracle_phase1_provider_bundle(
        settings,
        provider_secrets=DigitalOracleProviderSecrets(
            edgar_contact_email="sec-contact@example.test",
            fred_api_key="fred-key",
        ),
    )
    prediction_markets = bundle.prediction_markets
    sec_filings = bundle.sec_filings
    market_sentiment = bundle.market_sentiment

    assert not isinstance(prediction_markets, DigitalOracleProviderFailure)
    assert prediction_markets.venues == ("polymarket", "kalshi")
    assert prediction_markets.default_item_limit == 6
    assert [provider.key for provider in prediction_markets.providers] == [
        "polymarket",
        "kalshi",
    ]
    assert {provider.timeout_seconds for provider in prediction_markets.providers} == {2.5}

    assert not isinstance(sec_filings, DigitalOracleProviderFailure)
    assert sec_filings.provider.key == "edgar"
    assert sec_filings.provider.default_item_limit == 12
    assert sec_filings.edgar_contact_email == "sec-contact@example.test"

    assert not isinstance(market_sentiment, DigitalOracleProviderFailure)
    assert market_sentiment.provider.key == "fear_greed"
    assert market_sentiment.indicator == "fear_greed"

    assert not isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert bundle.macro_rates.default_item_limit == 13
    assert [provider.key for provider in bundle.macro_rates.providers] == [
        "treasury",
        "bis",
        "worldbank",
        "cme_fedwatch",
        "fred",
    ]
    assert bundle.macro_rates.source_failures == ()

    assert not isinstance(bundle.crypto_derivatives, DigitalOracleProviderFailure)
    assert bundle.crypto_derivatives.default_item_limit == 14
    assert [provider.key for provider in bundle.crypto_derivatives.providers] == [
        "deribit",
        "coingecko",
    ]

    assert not isinstance(bundle.cftc_positioning, DigitalOracleProviderFailure)
    assert bundle.cftc_positioning.default_item_limit == 15
    assert [provider.key for provider in bundle.cftc_positioning.providers] == [
        "cftc",
    ]

    assert not isinstance(bundle.options, DigitalOracleProviderFailure)
    assert bundle.options.default_item_limit == 16
    assert {provider.key for provider in bundle.options.providers} >= {"yahoo"}

    disabled_prediction = create_prediction_markets_provider_bundle(
        DigitalOracleSettings.model_validate({"DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED": "false"})
    )
    assert isinstance(disabled_prediction, DigitalOracleProviderFailure)
    assert disabled_prediction.message == (
        "Digital Oracle prediction markets provider is disabled by backend configuration."
    )


def test_digital_oracle_provider_bundle_disabled_new_sources_return_structured_failures() -> None:
    bundle = create_digital_oracle_phase1_provider_bundle(
        DigitalOracleSettings.model_validate(
            {
                "DIGITAL_ORACLE_MACRO_RATES_ENABLED": "false",
                "DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED": "false",
                "DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED": "false",
                "DIGITAL_ORACLE_OPTIONS_ENABLED": "false",
            }
        )
    )

    assert isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert bundle.macro_rates.details == {"provider": "macro_rates"}
    assert isinstance(bundle.crypto_derivatives, DigitalOracleProviderFailure)
    assert bundle.crypto_derivatives.details == {"provider": "crypto_derivatives"}
    assert isinstance(bundle.cftc_positioning, DigitalOracleProviderFailure)
    assert bundle.cftc_positioning.details == {"provider": "cftc_positioning"}
    assert isinstance(bundle.options, DigitalOracleProviderFailure)
    assert bundle.options.details == {"provider": "options"}


def test_digital_oracle_provider_bundle_missing_fred_key_is_source_scoped_failure() -> None:
    bundle = create_digital_oracle_phase1_provider_bundle(DigitalOracleSettings())

    assert not isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert [failure.details for failure in bundle.macro_rates.source_failures] == [
        {
            "provider": "fred",
            "secret": FRED_API_KEY_SECRET,
        }
    ]


def test_digital_oracle_optional_dependency_missing_yfinance_is_source_scoped_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", None)

    bundle = create_digital_oracle_phase1_provider_bundle(DigitalOracleSettings())

    assert not isinstance(bundle.options, DigitalOracleProviderFailure)
    assert [failure.details for failure in bundle.options.source_failures] == [
        {
            "dependency": "yfinance",
            "provider": "yfinance",
        }
    ]


def test_digital_oracle_edgar_missing_config_returns_structured_failure() -> None:
    result = create_sec_filings_provider(DigitalOracleSettings())

    assert isinstance(result, DigitalOracleProviderFailure)
    assert result.code == EDGAR_CONTACT_EMAIL_MISSING_CODE
    assert result.message == EDGAR_CONTACT_EMAIL_MISSING_MESSAGE
    assert result.details == {
        "provider": "edgar",
        "secret": EDGAR_CONTACT_EMAIL_SECRET,
    }


def test_digital_oracle_missing_edgar_contact_starts_with_warning_payload() -> None:
    reset_digital_oracle_settings_cache()
    try:
        app = create_app(init_database=False)
        payload = map_sec_filings_result(
            DigitalOraclePhase1Service().lookup_sec_filings(
                DigitalOracleSecFilingsQuery(ticker="NVDA")
            )
        ).model_dump(mode="json", by_alias=True)
    finally:
        reset_digital_oracle_settings_cache()

    assert app is not None
    assert payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert payload["ticker"] == "NVDA"
    assert payload["filings"] == []
    assert payload["warnings"] == [
        {
            "code": EDGAR_CONTACT_EMAIL_MISSING_CODE,
            "message": EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            "details": {
                "operation": "sec_filings",
                "provider": "edgar",
            },
        }
    ]


def test_digital_oracle_service_disabled_provider_config_returns_warnings_without_calls() -> None:
    prediction_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-disabled",
                title="Disabled provider event",
                status="open",
            ),
        ),
    )
    sec_provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    sentiment_provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=72,
            label="greed",
        )
    )
    service = DigitalOraclePhase1Service(
        settings=DigitalOracleSettings.model_validate(
            {
                "DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED": "false",
                "DIGITAL_ORACLE_SEC_FILINGS_ENABLED": "false",
                "DIGITAL_ORACLE_MARKET_SENTIMENT_ENABLED": "false",
            }
        ),
        prediction_market_providers=(prediction_provider,),
        sec_filings_provider=sec_provider,
        market_sentiment_provider=sentiment_provider,
    )

    prediction_payload = map_prediction_markets_result(
        service.lookup_prediction_markets(DigitalOraclePredictionMarketsQuery(query="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sec_payload = map_sec_filings_result(
        service.lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sentiment_payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)

    assert prediction_provider.calls == []
    assert sec_provider.calls == []
    assert sentiment_provider.calls == []
    assert prediction_payload["events"] == []
    assert prediction_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": (
                "Digital Oracle prediction markets provider is disabled by backend configuration."
            ),
            "details": {"operation": "prediction_markets", "provider": "prediction_markets"},
        }
    ]
    assert sec_payload["filings"] == []
    assert sec_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": "SEC EDGAR provider is disabled by backend configuration.",
            "details": {"operation": "sec_filings", "provider": "edgar"},
        }
    ]
    assert sentiment_payload["score"] is None
    assert sentiment_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": (
                "Digital Oracle market sentiment provider is disabled by backend configuration."
            ),
            "details": {"operation": "market_sentiment", "provider": "market_sentiment"},
        }
    ]


def test_digital_oracle_service_returns_normalized_phase1_dtos() -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-nvda-earnings",
                title="Will NVDA beat earnings expectations?",
                status="open",
                url="https://polymarket.example/events/nvda-earnings",
                end_date=_NOW,
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-nvda-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                        volume=Decimal("125000.5"),
                        open_interest=Decimal("2500"),
                        order_book=DigitalOraclePredictionMarketOrderBook(
                            bids=(
                                DigitalOraclePredictionMarketOrderBookLevel(
                                    price=Decimal("0.63"),
                                    size=Decimal("120"),
                                ),
                            ),
                            asks=(
                                DigitalOraclePredictionMarketOrderBookLevel(
                                    price=Decimal("0.65"),
                                    size=Decimal("90"),
                                ),
                            ),
                            spread=Decimal("0.02"),
                            depth_limit=2,
                        ),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXNVDA-26",
                title="NVDA closes above $150 this quarter",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXNVDA-26-Y",
                        title="Yes",
                        probability=Decimal("0.41"),
                        yes_price=Decimal("0.42"),
                        no_price=Decimal("0.59"),
                    ),
                ),
            ),
        ),
    )
    sec_provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000011",
                form_type="8-K",
                filing_date=date(2026, 3, 1),
            ),
        ),
        ownership_transactions=(
            DigitalOracleSecOwnershipTransaction(
                accession_number="0001045810-26-000020",
                filing_date=date(2026, 2, 21),
                issuer_name="NVIDIA CORP",
                issuer_ticker="NVDA",
                reporting_owner_name="Ada Lovelace",
                transaction_date=date(2026, 2, 20),
                transaction_code="P",
                acquired_disposed_code="A",
                shares=Decimal("10"),
                price=Decimal("120.25"),
                ownership_nature="D",
            ),
        ),
    )
    sentiment_provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=72,
            label="greed",
            as_of_date=date(2026, 1, 2),
            previous_close=70,
            week_ago=64,
            month_ago=55,
            year_ago=None,
        )
    )
    settings = DigitalOracleSettings.model_validate(
        {
            "DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5",
            "DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT": "6",
            "DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT": "12",
        }
    )
    service = DigitalOraclePhase1Service(
        provider_bundle=create_digital_oracle_phase1_provider_bundle(
            settings,
            provider_secrets=DigitalOracleProviderSecrets(
                edgar_contact_email="sec-contact@example.test"
            ),
        ),
        prediction_market_providers=(polymarket_provider, kalshi_provider),
        sec_filings_provider=sec_provider,
        market_sentiment_provider=sentiment_provider,
    )

    prediction_result = service.lookup_prediction_markets(
        DigitalOraclePredictionMarketsQuery(
            query="  NVDA   earnings ",
            venues=("polymarket", "kalshi"),
            item_limit=3,
            include_order_book=True,
            depth_limit=2,
        )
    )
    prediction_payload = map_prediction_markets_result(prediction_result).model_dump(
        mode="json",
        by_alias=True,
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(prediction_payload)
    assert prediction_result.query == "NVDA earnings"
    provider_item_limits = [
        provider.calls[0].item_limit for provider in (polymarket_provider, kalshi_provider)
    ]
    provider_timeouts = {
        provider.calls[0].timeout_seconds for provider in (polymarket_provider, kalshi_provider)
    }
    assert provider_item_limits == [3, 3]
    assert provider_timeouts == {2.5}
    assert polymarket_provider.calls[0].include_order_book is True
    assert kalshi_provider.calls[0].depth_limit == 2
    assert prediction_payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert [event["venue"] for event in prediction_events] == ["polymarket", "kalshi"]
    assert prediction_events[0]["eventId"] == "pm-nvda-earnings"
    prediction_contracts = cast(list[dict[str, object]], prediction_events[0]["contracts"])
    assert prediction_contracts[0]["yesPrice"] == "0.64"
    assert prediction_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.63", "size": "120"}],
        "asks": [{"price": "0.65", "size": "90"}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert prediction_payload["warnings"] == []

    sec_result = service.lookup_sec_filings(
        DigitalOracleSecFilingsQuery(
            ticker=" nvda ",
            query="annual report",
            form_types=("10-k",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            item_limit=1,
            include_ownership_transactions=True,
        )
    )
    sec_payload = map_sec_filings_result(sec_result).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(sec_payload)
    assert sec_provider.calls[0].ticker == "NVDA"
    assert sec_provider.calls[0].query == "annual report"
    assert sec_provider.calls[0].form_types == ("10-K",)
    assert sec_provider.calls[0].include_ownership_transactions is True
    assert sec_provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert sec_provider.calls[0].timeout_seconds == 2.5
    assert sec_payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert sec_payload["ticker"] == "NVDA"
    sec_filings = cast(list[dict[str, object]], sec_payload["filings"])
    assert [filing["formType"] for filing in sec_filings] == ["10-K"]
    sec_search_hits = cast(list[dict[str, object]], sec_payload["searchHits"])
    assert sec_search_hits[0]["matchedText"] == "Annual report"
    assert sec_payload["ownershipTransactions"] == []
    assert sec_payload["warnings"] == []

    sentiment_result = service.lookup_market_sentiment(
        DigitalOracleMarketSentimentQuery(as_of_date=date(2026, 1, 2))
    )
    sentiment_payload = map_market_sentiment_result(sentiment_result).model_dump(
        mode="json",
        by_alias=True,
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(sentiment_payload)
    assert sentiment_provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert sentiment_provider.calls[0].timeout_seconds == 2.5
    assert sentiment_payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert sentiment_payload["score"] == 72
    assert sentiment_payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert sentiment_payload["warnings"] == []


def test_digital_oracle_service_partial_failures_return_structured_warnings() -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-event",
                title="Will NVDA beat earnings expectations?",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-event-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi provider timed out with api_key=sk-provider-secret",
            code="provider_timeout",
            details={
                "venue": "kalshi",
                "api_key": "sk-provider-secret",
                "request_id": "req-123",
            },
        ),
    )
    empty_sentiment_provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(provider="fear_greed")
    )
    service = DigitalOraclePhase1Service(
        prediction_market_providers=(polymarket_provider, kalshi_provider),
        market_sentiment_provider=empty_sentiment_provider,
    )

    prediction_payload = map_prediction_markets_result(
        service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="NVDA earnings",
                venues=("polymarket", "kalshi"),
            )
        )
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(prediction_payload)
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert [event["venue"] for event in prediction_events] == ["polymarket"]
    warning_payload = cast(list[dict[str, object]], prediction_payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_partial_result",
    ]
    assert warning_payload[0]["message"] == "Kalshi provider timed out with api_key=<redacted>"
    assert warning_payload[0]["details"] == {
        "operation": "prediction_markets",
        "provider": "kalshi",
        "venue": "kalshi",
        "requestId": "req-123",
    }

    sec_payload = map_sec_filings_result(
        DigitalOraclePhase1Service().lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sec_warnings = cast(list[dict[str, object]], sec_payload["warnings"])
    assert sec_payload["filings"] == []
    assert sec_warnings == [
        {
            "code": EDGAR_CONTACT_EMAIL_MISSING_CODE,
            "message": EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            "details": {
                "operation": "sec_filings",
                "provider": "edgar",
            },
        }
    ]

    sentiment_payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    sentiment_warnings = cast(list[dict[str, object]], sentiment_payload["warnings"])
    assert sentiment_payload["score"] is None
    assert sentiment_warnings == [
        {
            "code": "market_sentiment_empty",
            "message": "No market_sentiment data returned from fear_greed.",
            "details": {"operation": "market_sentiment", "provider": "fear_greed"},
        }
    ]


def test_runtime_types_digital_oracle_results_serialize_normalized_contracts() -> None:
    assert NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS == (
        PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        SEC_FILINGS_LOOKUP_TOOL_KEY,
        MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        MACRO_RATES_LOOKUP_TOOL_KEY,
        CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
        CFTC_POSITIONING_LOOKUP_TOOL_KEY,
        OPTIONS_LOOKUP_TOOL_KEY,
    )

    prediction_warning = RuntimeToolWarning(
        code="venue_partial",
        message="Kalshi returned a partial response.",
        details={"venue": "kalshi"},
    )
    prediction_payload = RuntimePredictionMarketsLookupResult(
        query="NVDA earnings probability",
        events=[
            RuntimePredictionMarketEvent(
                venue="polymarket",
                event_id="polymarket-event-1",
                title="Will NVDA beat earnings expectations?",
                status="open",
                url="https://polymarket.example/events/nvda-earnings",
                end_date=_NOW,
                contracts=[
                    RuntimePredictionMarketContract(
                        contract_id="polymarket-market-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                        volume=Decimal("125000.5"),
                        open_interest=Decimal("2500"),
                        order_book=RuntimePredictionMarketOrderBook(
                            bids=[
                                RuntimePredictionMarketOrderBookLevel(
                                    price=Decimal("0.63"),
                                    size=Decimal("250"),
                                )
                            ],
                            asks=[
                                RuntimePredictionMarketOrderBookLevel(
                                    price=Decimal("0.66"),
                                    size=Decimal("175"),
                                )
                            ],
                            spread=Decimal("0.03"),
                            depth_limit=1,
                        ),
                    )
                ],
            )
        ],
        warnings=[prediction_warning],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(prediction_payload)
    assert set(prediction_payload) == {"toolKey", "query", "events", "warnings"}
    assert prediction_payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert prediction_payload["warnings"] == [
        {
            "code": "venue_partial",
            "message": "Kalshi returned a partial response.",
            "details": {"venue": "kalshi"},
        }
    ]
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert set(prediction_events[0]) == {
        "venue",
        "eventId",
        "title",
        "status",
        "url",
        "endDate",
        "contracts",
    }
    assert prediction_events[0]["endDate"] == "2026-01-02T03:04:05Z"
    prediction_contracts = cast(list[dict[str, object]], prediction_events[0]["contracts"])
    assert prediction_contracts[0] == {
        "contractId": "polymarket-market-yes",
        "title": "Yes",
        "probability": "0.62",
        "yesPrice": "0.64",
        "noPrice": "0.38",
        "volume": "125000.5",
        "openInterest": "2500",
        "orderBook": {
            "bids": [{"price": "0.63", "size": "250"}],
            "asks": [{"price": "0.66", "size": "175"}],
            "spread": "0.03",
            "depthLimit": 1,
        },
    }

    sec_payload = RuntimeSecFilingsLookupResult(
        ticker="NVDA",
        query="Annual report",
        cik="0001045810",
        entity_name="NVIDIA CORP",
        filings=[
            RuntimeSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            )
        ],
        search_hits=[
            RuntimeSecSearchHit(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                cik="0001045810",
                ticker="NVDA",
                entity_name="NVIDIA CORP",
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
                matched_text="Annual report",
            )
        ],
        ownership_transactions=[
            RuntimeSecOwnershipTransaction(
                accession_number="0001045810-26-000020",
                filing_date=date(2026, 2, 21),
                issuer_name="NVIDIA CORP",
                issuer_ticker="NVDA",
                reporting_owner_name="Ada Lovelace",
                transaction_date=date(2026, 2, 20),
                transaction_code="P",
                acquired_disposed_code="A",
                shares=Decimal("10"),
                price=Decimal("120.25"),
                ownership_nature="D",
            )
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(sec_payload)
    assert set(sec_payload) == {
        "toolKey",
        "ticker",
        "query",
        "cik",
        "entityName",
        "filings",
        "searchHits",
        "ownershipTransactions",
        "warnings",
    }
    assert sec_payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert sec_payload["warnings"] == []
    sec_filings = cast(list[dict[str, object]], sec_payload["filings"])
    assert sec_filings[0] == {
        "accessionNumber": "0001045810-26-000010",
        "formType": "10-K",
        "filingDate": "2026-02-20",
        "acceptedAt": "2026-01-02T03:04:05Z",
        "primaryDocument": "nvda-20260131.htm",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
        "description": "Annual report",
    }
    sec_search_hits = cast(list[dict[str, object]], sec_payload["searchHits"])
    assert sec_search_hits[0] == {
        "accessionNumber": "0001045810-26-000010",
        "formType": "10-K",
        "filingDate": "2026-02-20",
        "cik": "0001045810",
        "ticker": "NVDA",
        "entityName": "NVIDIA CORP",
        "primaryDocument": "nvda-20260131.htm",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
        "description": "Annual report",
        "matchedText": "Annual report",
    }
    sec_ownership = cast(list[dict[str, object]], sec_payload["ownershipTransactions"])
    assert sec_ownership[0] == {
        "accessionNumber": "0001045810-26-000020",
        "filingDate": "2026-02-21",
        "issuerName": "NVIDIA CORP",
        "issuerTicker": "NVDA",
        "reportingOwnerName": "Ada Lovelace",
        "transactionDate": "2026-02-20",
        "transactionCode": "P",
        "acquiredDisposedCode": "A",
        "shares": "10",
        "price": "120.25",
        "ownershipNature": "D",
    }

    sentiment_warning = RuntimeToolWarning(
        code="history_partial",
        message="Fear and Greed history did not include a year-ago value.",
        details={"provider": "fear_greed"},
    )
    sentiment_payload = RuntimeMarketSentimentLookupResult(
        indicator="fear_greed",
        as_of_date=date(2026, 1, 2),
        provider="fear_greed",
        score=72,
        label="greed",
        previous_close=70,
        week_ago=64,
        month_ago=55,
        year_ago=None,
        source_url="https://www.cnn.com/markets/fear-and-greed",
        warnings=[sentiment_warning],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(sentiment_payload)
    assert set(sentiment_payload) == {
        "toolKey",
        "indicator",
        "asOfDate",
        "provider",
        "score",
        "label",
        "previousClose",
        "weekAgo",
        "monthAgo",
        "yearAgo",
        "sourceUrl",
        "warnings",
    }
    assert sentiment_payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert sentiment_payload["asOfDate"] == "2026-01-02"
    assert sentiment_payload["warnings"] == [
        {
            "code": "history_partial",
            "message": "Fear and Greed history did not include a year-ago value.",
            "details": {"provider": "fear_greed"},
        }
    ]


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            RuntimePredictionMarketsLookupResult,
            {
                "toolKey": PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
                "query": "NVDA",
                "events": [],
                "warnings": [],
                "rawProviderPayload": {},
            },
        ),
        (
            RuntimeSecFilingsLookupResult,
            {
                "toolKey": SEC_FILINGS_LOOKUP_TOOL_KEY,
                "ticker": "NVDA",
                "filings": [],
                "warnings": [],
                "rawFilings": [],
            },
        ),
        (
            RuntimeMarketSentimentLookupResult,
            {
                "toolKey": MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
                "indicator": "fear_greed",
                "provider": "fear_greed",
                "warnings": [],
                "rawScore": {},
            },
        ),
    ],
)
def test_runtime_types_prediction_markets_sec_filings_market_sentiment_reject_raw_fields(
    model: (
        type[RuntimePredictionMarketsLookupResult]
        | type[RuntimeSecFilingsLookupResult]
        | type[RuntimeMarketSentimentLookupResult]
    ),
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _ = model.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            RuntimePredictionMarketsLookupResult,
            {
                "toolKey": SEC_FILINGS_LOOKUP_TOOL_KEY,
                "query": "NVDA",
                "events": [],
                "warnings": [],
            },
        ),
        (
            RuntimeSecFilingsLookupResult,
            {
                "toolKey": MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
                "ticker": "NVDA",
                "filings": [],
                "warnings": [],
            },
        ),
        (
            RuntimeMarketSentimentLookupResult,
            {
                "toolKey": PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
                "indicator": "fear_greed",
                "provider": "fear_greed",
                "warnings": [],
            },
        ),
    ],
)
def test_runtime_types_prediction_markets_sec_filings_market_sentiment_reject_wrong_tool_keys(
    model: (
        type[RuntimePredictionMarketsLookupResult]
        | type[RuntimeSecFilingsLookupResult]
        | type[RuntimeMarketSentimentLookupResult]
    ),
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _ = model.model_validate(payload)


def test_generic_platform_runtime_tool_specs_have_expected_openai_function_names() -> None:
    target_function_names = tuple(
        _GENERIC_PLATFORM_RUNTIME_TOOL_OPENAI_FUNCTION_NAMES_BY_KEY.values()
    )
    assert len(target_function_names) == len(set(target_function_names))

    runtime_function_names = [spec.openai_function_name for spec in RUNTIME_TOOL_SPECS]
    assert len(runtime_function_names) == len(set(runtime_function_names))

    runtime_function_names_by_key = {
        spec.key: spec.openai_function_name for spec in RUNTIME_TOOL_SPECS
    }
    actual_target_function_names_by_key = {
        tool_key: runtime_function_names_by_key.get(tool_key)
        for tool_key in _GENERIC_PLATFORM_RUNTIME_TOOL_KEYS
    }
    assert (
        actual_target_function_names_by_key
        == _GENERIC_PLATFORM_RUNTIME_TOOL_OPENAI_FUNCTION_NAMES_BY_KEY
    )


def test_digital_oracle_runtime_bundle_includes_digital_oracle_runtime_specs() -> None:
    from app.extensions.signaldeck_digital_oracle.runtime_executors import (
        DIGITAL_ORACLE_RUNTIME_TOOL_SPECS,
    )

    runtime_specs_by_key = {spec.key: spec for spec in DIGITAL_ORACLE_RUNTIME_TOOL_SPECS}
    assert (
        runtime_specs_by_key[PREDICTION_MARKETS_LOOKUP_TOOL_KEY]
        is PREDICTION_MARKETS_LOOKUP_TOOL_SPEC
    )
    assert runtime_specs_by_key[SEC_FILINGS_LOOKUP_TOOL_KEY] is SEC_FILINGS_LOOKUP_TOOL_SPEC
    assert (
        runtime_specs_by_key[MARKET_SENTIMENT_LOOKUP_TOOL_KEY] is MARKET_SENTIMENT_LOOKUP_TOOL_SPEC
    )


def test_finance_runtime_bundle_keeps_unique_tool_keys_and_function_names() -> None:
    from app.extensions.signaldeck_finance.runtime_executors import (
        FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS,
    )

    runtime_tool_keys = [spec.key for spec in FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS]
    runtime_function_names = [
        spec.openai_function_name for spec in FINANCE_WORKSPACE_RUNTIME_TOOL_SPECS
    ]

    assert len(runtime_tool_keys) == len(set(runtime_tool_keys))
    assert len(runtime_function_names) == len(set(runtime_function_names))
    assert PREDICTION_MARKETS_LOOKUP_TOOL_KEY not in runtime_tool_keys
    assert SEC_FILINGS_LOOKUP_TOOL_KEY not in runtime_tool_keys
    assert MARKET_SENTIMENT_LOOKUP_TOOL_KEY not in runtime_tool_keys
    assert PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME not in runtime_function_names
    assert SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME not in runtime_function_names
    assert MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME not in runtime_function_names


def test_native_runtime_tool_results_serialize_with_camel_case_contracts() -> None:
    warning = RuntimeToolWarning(
        code="provider_degraded",
        message="Using cached provider data.",
        details={"provider": "deterministic_test", "symbol": "NVDA"},
    )

    quote_payload = RuntimeQuoteLookupResult(
        quotes=[_quote_read()],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(quote_payload)
    assert quote_payload["toolKey"] == "signaldeck.finance.market_data.quote_lookup"
    assert quote_payload["quotes"][0]["previousClose"] == "119.75000000"
    assert quote_payload["quotes"][0]["asOf"] == "2026-01-02T03:04:05Z"
    assert quote_payload["quotes"][0]["isStale"] is False
    assert quote_payload["warnings"] == [
        {
            "code": "provider_degraded",
            "message": "Using cached provider data.",
            "details": {"provider": "deterministic_test", "symbol": "NVDA"},
        }
    ]

    history_payload = RuntimeHistoryLookupResult(
        range="1mo",
        interval="1d",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        series=[_history_series_read()],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(history_payload)
    assert history_payload["toolKey"] == "signaldeck.finance.market_data.history_lookup"
    assert history_payload["endDate"] == "2026-01-02T03:04:05Z"
    assert history_payload["series"][0]["points"][0] == {
        "at": "2026-01-01T00:00:00Z",
        "close": "119.75",
    }

    ohlcv_payload = RuntimeOhlcvLookupResult(
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        series=[_ohlcv_series()],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(ohlcv_payload)
    assert ohlcv_payload["toolKey"] == "signaldeck.finance.market_data.ohlcv_lookup"
    assert ohlcv_payload["series"][0]["rows"][0]["adjustedClose"] == "119.50"

    indicator_payload = RuntimeIndicatorLookupResult(
        symbol="NVDA",
        provider="deterministic_test",
        current_date=_NOW,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        rows=[
            RuntimeIndicatorRow(
                at=datetime(2026, 1, 1, tzinfo=UTC),
                values=[RuntimeIndicatorValue(name="sma_20", value=None, null_reason="warmup")],
            ),
            RuntimeIndicatorRow(
                at=_NOW,
                values=[RuntimeIndicatorValue(name="sma_20", value=Decimal("120.125"))],
            ),
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(indicator_payload)
    assert indicator_payload["toolKey"] == "signaldeck.finance.indicators.lookup"
    assert indicator_payload["currentDate"] == "2026-01-02T03:04:05Z"
    assert indicator_payload["rows"][0]["values"][0] == {
        "name": "sma_20",
        "value": None,
        "nullReason": "warmup",
    }

    fundamentals_payload = RuntimeFundamentalsLookupResult(
        symbol="NVDA",
        provider="deterministic_test",
        as_of=_NOW,
        metrics=[
            RuntimeFundamentalMetric(
                name="market_cap",
                value=Decimal("1000000.50"),
                currency="USD",
                period="ttm",
                as_of=_NOW,
            )
        ],
        statements=[
            RuntimeFinancialStatement(
                statement_type="income_statement",
                period="annual",
                period_end=_NOW,
                lines=[
                    RuntimeFinancialStatementLine(
                        name="revenue",
                        value=Decimal("500000.25"),
                        currency="USD",
                    )
                ],
            )
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(fundamentals_payload)
    assert fundamentals_payload["toolKey"] == "signaldeck.finance.fundamentals.lookup"
    assert fundamentals_payload["metrics"][0]["asOf"] == "2026-01-02T03:04:05Z"
    assert fundamentals_payload["statements"][0]["statementType"] == "income_statement"
    assert fundamentals_payload["statements"][0]["periodEnd"] == "2026-01-02T03:04:05Z"

    news_payload = RuntimeNewsLookupResult(
        symbols=["NVDA"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        items=[
            RuntimeNewsItem(
                title="NVIDIA expands inference capacity",
                source="wire",
                published_at=_NOW,
                summary="Capacity expansion announced.",
                symbols=["NVDA"],
                sentiment="positive",
            )
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(news_payload)
    assert news_payload["toolKey"] == "signaldeck.finance.news.lookup"
    assert news_payload["items"][0]["publishedAt"] == "2026-01-02T03:04:05Z"

    social_sentiment_payload = RuntimeSocialSentimentLookupResult(
        symbol=" nvda ",
        sources=["reddit", "stocktwits", "reddit"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        source_blocks=[
            RuntimeSocialSentimentSourceBlock(
                source="Reddit",
                provider="deterministic_test",
                title="Retail thread",
                summary="Mentions increased.",
                as_of=_NOW,
                symbols=["nvda", "NVDA"],
                sentiment="positive",
                metrics=[
                    RuntimeSocialSentimentMetric(
                        name="Mention Count",
                        value=Decimal("12"),
                        unit="count",
                        source="Reddit",
                        as_of=_NOW,
                    )
                ],
            )
        ],
        metrics=[RuntimeSocialSentimentMetric(name="Bullish Ratio", value=Decimal("0.67"))],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(social_sentiment_payload)
    assert social_sentiment_payload["toolKey"] == "signaldeck.finance.social_sentiment.lookup"
    assert social_sentiment_payload["symbol"] == "NVDA"
    assert social_sentiment_payload["sources"] == ["reddit", "stocktwits"]
    assert social_sentiment_payload["sourceBlocks"][0]["source"] == "reddit"
    assert social_sentiment_payload["sourceBlocks"][0]["symbols"] == ["NVDA"]
    assert social_sentiment_payload["metrics"][0]["name"] == "bullish_ratio"

    insider_payload = RuntimeInsiderDataLookupResult(
        symbol="NVDA",
        provider="deterministic_test",
        transactions=[
            RuntimeInsiderTransaction(
                insider_name="Ada Lovelace",
                role="Director",
                transaction_type="BUY",
                shares=Decimal("10"),
                price=Decimal("120.25"),
                value=Decimal("1202.50"),
                filed_at=_NOW,
                transaction_date=_NOW,
            )
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(insider_payload)
    assert insider_payload["toolKey"] == "signaldeck.finance.insider_data.lookup"
    assert insider_payload["transactions"][0]["insiderName"] == "Ada Lovelace"
    assert insider_payload["transactions"][0]["transactionDate"] == "2026-01-02T03:04:05Z"
    assert insider_payload["transactions"][0]["filedAt"] == "2026-01-02T03:04:05Z"


def test_news_lookup_contract_uses_current_news_fields() -> None:
    parameters = NEWS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], parameters["properties"])

    assert NEWS_LOOKUP_TOOL_SPEC.key == NEWS_LOOKUP_TOOL_KEY
    assert NEWS_LOOKUP_TOOL_SPEC.openai_function_name == NEWS_LOOKUP_OPENAI_FUNCTION_NAME
    assert list(properties) == ["symbols", "query", "scope", "startDate", "endDate", "itemLimit"]
    assert parameters["required"] == [
        "symbols",
        "query",
        "scope",
        "startDate",
        "endDate",
        "itemLimit",
    ]
    assert cast(dict[str, object], properties["scope"])["enum"] == [
        "symbol",
        "market",
        "global",
        None,
    ]

    parsed = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": [" nvda ", "NVDA"],
                "query": " earnings ",
                "scope": "symbol",
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        )
    )
    assert parsed == {
        "symbols": ["NVDA"],
        "query": "earnings",
        "scope": "symbol",
        "start_date": None,
        "end_date": None,
        "item_limit": 25,
    }

    payload = RuntimeNewsLookupResult(
        symbols=["NVDA"],
        query="earnings",
        items=[RuntimeNewsItem(title="News", source="wire", published_at=_NOW)],
    ).model_dump(mode="json", by_alias=True)
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert set(payload) == {
        "toolKey",
        "query",
        "symbols",
        "startDate",
        "endDate",
        "items",
        "warnings",
    }


def test_news_lookup_parser_supports_bounded_global_scope_without_social_mutation() -> None:
    parsed = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": None,
                "query": "macro liquidity and export controls",
                "scope": " global ",
                "startDate": "2026-01-01T00:00:00Z",
                "endDate": "2026-01-03T00:00:00Z",
                "itemLimit": 10,
            }
        )
    )

    assert parsed == {
        "symbols": [],
        "query": "macro liquidity and export controls",
        "scope": "global",
        "start_date": datetime(2026, 1, 1, tzinfo=UTC),
        "end_date": datetime(2026, 1, 3, tzinfo=UTC),
        "item_limit": 10,
    }

    with pytest.raises(RuntimeToolError, match="scope must use: global, market, symbol"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "markets",
                    "scope": "combined_sentiment",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )
    with pytest.raises(RuntimeToolError, match="scope symbol requires symbols"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "markets",
                    "scope": "symbol",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )
    with pytest.raises(RuntimeToolError, match="query must be at most 240 characters"):
        _ = parse_news_lookup_arguments(
            json.dumps(
                {
                    "symbols": None,
                    "query": "x" * 241,
                    "scope": "global",
                    "startDate": None,
                    "endDate": None,
                    "itemLimit": None,
                }
            )
        )


def test_news_lookup_dispatch_uses_injected_finance_news_providers() -> None:
    quote_provider = _RecordingQuoteProvider()
    news_provider = _FinancialContractProvider(provider_name="runtime_news", news_count=3)
    registry = RuntimeToolRegistry([NEWS_LOOKUP_TOOL_SPEC])
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    end_date = datetime(2026, 1, 3, tzinfo=UTC)
    payload = registry.dispatch(
        name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbols": [" nvda "],
                "query": " earnings ",
                "scope": "symbol",
                "startDate": "2026-01-01T00:00:00Z",
                "endDate": "2026-01-03T00:00:00Z",
                "itemLimit": 2,
            }
        ),
        granted_tool_keys={NEWS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            quote_provider=quote_provider,
            news_providers=[news_provider],
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert set(payload) == {
        "toolKey",
        "query",
        "symbols",
        "startDate",
        "endDate",
        "items",
        "warnings",
    }
    assert news_provider.news_calls == [(["NVDA"], "earnings", "symbol", start_date, end_date, 3)]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert payload["query"] == "earnings"
    assert payload["symbols"] == ["NVDA"]
    item_payload = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in item_payload] == ["News 2", "News 1"]
    assert cast(list[dict[str, object]], payload["warnings"])[0] == {
        "code": "news_truncated",
        "message": "News results were truncated to 2 items",
        "details": {"limit": "2", "scope": "symbol"},
    }


def test_news_lookup_uses_context_alpha_vantage_secret_when_provider_order_prefers_alpha(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = _RecordingQuoteProvider()
    created_api_keys: list[str | None] = []
    fetch_calls: list[
        tuple[list[str], str | None, NewsScope, datetime | None, datetime | None, int]
    ] = []

    class RecordingAlphaVantageNewsProvider:
        provider_name = "alpha_vantage"

        def __init__(self, *, api_key: str | None, timeout: float = 5.0) -> None:
            del timeout
            created_api_keys.append(api_key)

        def fetch_news(
            self,
            *,
            symbols: list[str],
            query: str | None,
            scope: NewsScope,
            start_date: datetime | None,
            end_date: datetime | None,
            limit: int,
        ) -> ProviderNewsResult:
            fetch_calls.append((symbols, query, scope, start_date, end_date, limit))
            return ProviderNewsResult(
                provider=self.provider_name,
                items=[
                    ProviderNewsItem(
                        title="Alpha Vantage runtime news",
                        source="alpha_vantage",
                        published_at=_NOW,
                        symbols=symbols,
                    )
                ],
            )

    monkeypatch.setattr(
        "app.extensions.signaldeck_finance.provider_factories.AlphaVantageNewsProvider",
        RecordingAlphaVantageNewsProvider,
    )
    monkeypatch.setenv("QUOTE_PROVIDER_BACKEND", "yahoo")
    monkeypatch.setenv("FINANCE_NEWS_PROVIDER_ORDER", "alpha_vantage")
    _reset_runtime_settings_caches()
    try:
        payload = execute_news_lookup(
            _runtime_context(
                session_factory_override=session_factory,
                quote_provider=quote_provider,
                secret_values={"alpha_vantage_api_key": "caller-alpha-vantage-key"},
            ),
            parse_news_lookup_arguments(
                json.dumps(
                    {
                        "symbols": ["NVDA"],
                        "query": "earnings",
                        "scope": "symbol",
                        "startDate": None,
                        "endDate": None,
                        "itemLimit": 1,
                    }
                )
            ),
        )
    finally:
        _reset_runtime_settings_caches()

    assert created_api_keys == ["caller-alpha-vantage-key"]
    assert fetch_calls == [(["NVDA"], "earnings", "symbol", None, None, 2)]
    assert payload["items"] == [
        {
            "title": "Alpha Vantage runtime news",
            "source": "alpha_vantage",
            "publishedAt": "2026-01-02T03:04:05Z",
            "url": None,
            "summary": None,
            "symbols": ["NVDA"],
            "sentiment": None,
        }
    ]
    assert "caller-alpha-vantage-key" not in json.dumps(payload)


def test_indicator_contract_requires_warmup_reasons_and_rejects_lookahead() -> None:
    with pytest.raises(ValidationError, match="nullReason is required"):
        _ = RuntimeIndicatorValue(name="sma_20", value=None)

    with pytest.raises(ValidationError, match="endDate cannot be after currentDate"):
        _ = RuntimeIndicatorLookupResult(
            symbol="NVDA",
            provider="deterministic_test",
            current_date=datetime(2026, 1, 2, tzinfo=UTC),
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, tzinfo=UTC),
            rows=[],
        )


def test_ohlcv_contract_rejects_non_chronological_rows() -> None:
    with pytest.raises(ValidationError, match="Rows must be chronological"):
        _ = RuntimeOhlcvSeries(
            symbol="NVDA",
            provider="deterministic_test",
            rows=list(reversed(_ohlcv_series().rows)),
        )


def test_market_data_ohlcv_snapshot_normalizes_dedupes_bounds_and_utc_serializes(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider()
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    end_date = datetime(2026, 1, 3, 16, tzinfo=UTC)

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            [" nvda ", "NVDA", "aapl"],
            start_date=start_date,
            end_date=end_date,
            row_limit=3,
        )

    assert provider.ohlcv_calls == [
        ("NVDA", start_date, end_date, "1d"),
        ("AAPL", start_date, end_date, "1d"),
    ]
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"
    assert payload["warnings"] == []

    series = cast(list[dict[str, object]], payload["series"])
    assert [item["symbol"] for item in series] == ["NVDA", "AAPL"]
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert rows == [
        {
            "at": "2026-01-01T00:00:00Z",
            "open": "118.00",
            "high": "121.00",
            "low": "117.00",
            "close": "119.75",
            "volume": 1000,
            "adjustedClose": "119.50",
        },
        {
            "at": "2026-01-02T17:00:00Z",
            "open": "119.00",
            "high": "122.00",
            "low": "118.00",
            "close": "120.00",
            "volume": 1100,
            "adjustedClose": "119.80",
        },
        {
            "at": "2026-01-03T16:00:00Z",
            "open": "119.75",
            "high": "121.50",
            "low": "119.00",
            "close": "120.25",
            "volume": 1200,
            "adjustedClose": None,
        },
    ]


def test_market_data_ohlcv_snapshot_applies_row_limit(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider()

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            ["nvda"],
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            row_limit=2,
        )

    payload = result.model_dump(mode="json", by_alias=True)
    series = cast(list[dict[str, object]], payload["series"])
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]


def test_market_data_ohlcv_snapshot_warns_for_unavailable_symbols_without_rows(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider(failing_symbols={"BAD"})

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_ohlcv_snapshot(
            ["bad", "nvda"],
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            row_limit=3,
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    series = cast(list[dict[str, object]], payload["series"])
    assert [item["symbol"] for item in series] == ["NVDA"]
    assert payload["warnings"] == [
        {
            "code": "ohlcv_unavailable",
            "message": "No OHLCV data available for BAD",
            "details": {"symbol": "BAD"},
        }
    ]


def test_market_data_fundamentals_snapshot_uses_first_provider_success_and_utc_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _FinancialContractProvider(provider_name="fundamentals_primary")

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_fundamentals_snapshot(" nvda ", providers=[provider])

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.fundamental_calls == ["NVDA"]
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fundamentals_primary"
    assert payload["asOf"] == "2026-01-02T17:00:00Z"
    assert payload["metrics"][0]["asOf"] == "2026-01-02T02:00:00Z"
    assert payload["statements"][0]["periodEnd"] == "2026-01-02T02:00:00Z"
    assert payload["warnings"] == []


def test_market_data_fundamentals_snapshot_falls_back_after_provider_failure(
    session_factory: sessionmaker[Session],
) -> None:
    failing_provider = _FinancialContractProvider(
        provider_name="fundamentals_failing",
        failure=QuoteProviderError(
            "primary fundamentals failed with api_key=sk-provider-secret",
            details={
                "provider_status": "503 sk-provider-secret",
                "api_key": "sk-provider-secret",
                "rawSecret": "hidden",
            },
        ),
    )
    success_provider = _FinancialContractProvider(provider_name="fundamentals_secondary")

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=failing_provider)
        result = service.get_fundamentals_snapshot(
            "nvda",
            providers=[failing_provider, success_provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert failing_provider.fundamental_calls == ["NVDA"]
    assert success_provider.fundamental_calls == ["NVDA"]
    assert payload["provider"] == "fundamentals_secondary"
    warning_json = json.dumps(payload["warnings"])
    assert "sk-provider-secret" not in warning_json
    assert "<redacted>" in warning_json
    assert payload["warnings"] == [
        {
            "code": "fundamentals_provider_error",
            "message": "primary fundamentals failed with api_key=<redacted>",
            "details": {
                "providerStatus": "503 <redacted>",
                "operation": "fundamentals",
                "provider": "fundamentals_failing",
            },
        }
    ]


def test_market_data_fundamentals_snapshot_degrades_empty_for_all_provider_failures(
    session_factory: sessionmaker[Session],
) -> None:
    missing_key_provider = _FinancialContractProvider(
        provider_name="fundamentals_missing_key",
        failure=QuoteProviderMissingKeyError("fundamentals API key is missing"),
    )
    failing_provider = _FinancialContractProvider(
        provider_name="fundamentals_error",
        failure=QuoteProviderError("fundamentals provider failed"),
    )

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=missing_key_provider)
        result = service.get_fundamentals_snapshot(
            "nvda",
            providers=[missing_key_provider, failing_provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["metrics"] == []
    assert payload["statements"] == []
    warning_payload = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "fundamentals_api_key_missing",
        "fundamentals_provider_error",
        "fundamentals_unavailable",
    ]


def test_market_data_news_snapshot_truncates_results_and_normalizes_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _FinancialContractProvider(provider_name="news_primary", news_count=4)
    start_date = datetime(2026, 1, 1, 19, tzinfo=timezone(timedelta(hours=-5)))
    end_date = datetime(2026, 1, 2, 19, tzinfo=timezone(timedelta(hours=-5)))

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            symbols=[" nvda ", "NVDA"],
            query=" earnings ",
            start_date=start_date,
            end_date=end_date,
            item_limit=2,
            providers=[provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.news_calls == [
        (["NVDA"], "earnings", "symbol", start_date.astimezone(UTC), end_date.astimezone(UTC), 3)
    ]
    assert payload["query"] == "earnings"
    assert payload["symbols"] == ["NVDA"]
    assert payload["startDate"] == "2026-01-02T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T00:00:00Z"
    item_payload = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in item_payload] == ["News 3", "News 2"]
    assert payload["warnings"] == [
        {
            "code": "news_truncated",
            "message": "News results were truncated to 2 items",
            "details": {"limit": "2", "scope": "symbol"},
        }
    ]


def test_market_data_news_snapshot_supports_global_scope_with_bounded_warning_and_dates(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _FinancialContractProvider(provider_name="global_news", news_count=4)
    start_date = datetime(2026, 1, 2, 1, tzinfo=UTC)
    end_date = datetime(2026, 1, 2, 2, tzinfo=UTC)

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            symbols=[],
            query="macro liquidity",
            scope="global",
            start_date=start_date,
            end_date=end_date,
            item_limit=10,
            providers=[provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.news_calls == [([], "macro liquidity", "global", start_date, end_date, 11)]
    assert payload["query"] == "macro liquidity"
    assert payload["symbols"] == []
    item_payload = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in item_payload] == ["News 2", "News 1"]
    assert payload["warnings"] == [
        {
            "code": "news_global_coverage_limited",
            "message": "Global news coverage is bounded by the configured finance provider",
            "details": {"scope": "global", "provider": "global_news"},
        }
    ]


def test_market_data_news_snapshot_warns_for_empty_global_coverage(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _FinancialContractProvider(provider_name="empty_global_news", news_count=0)

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_news_snapshot(
            query="macro liquidity",
            scope="global",
            providers=[provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["items"] == []
    assert payload["warnings"] == [
        {
            "code": "news_global_coverage_limited",
            "message": "Global news coverage is bounded by the configured finance provider",
            "details": {"scope": "global", "provider": "empty_global_news"},
        },
        {
            "code": "news_empty",
            "message": "No news returned for the request",
            "details": {
                "symbols": "",
                "query": "macro liquidity",
                "scope": "global",
                "provider": "empty_global_news",
            },
        },
    ]


def test_market_data_news_snapshot_bounds_provider_fallback_attempts(
    session_factory: sessionmaker[Session],
) -> None:
    providers = [
        _FinancialContractProvider(
            provider_name=f"news_failing_{index}",
            failure=QuoteProviderTimeoutError("news provider timed out"),
        )
        for index in range(4)
    ]

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=providers[0])
        result = service.get_news_snapshot(symbols=["nvda"], providers=providers)

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert [len(provider.news_calls) for provider in providers] == [1, 1, 1, 0]
    assert payload["items"] == []
    warning_payload = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "news_provider_timeout",
        "news_provider_timeout",
        "news_provider_timeout",
        "news_unavailable",
    ]


def test_market_data_insider_snapshot_truncates_and_utc_serializes(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _FinancialContractProvider(provider_name="insider_primary", insider_count=3)

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_insider_transactions_snapshot(
            " nvda ",
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, tzinfo=UTC),
            transaction_limit=2,
            providers=[provider],
        )

    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.insider_calls == [
        ("NVDA", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC), 3)
    ]
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "insider_primary"
    transaction_payload = cast(list[dict[str, object]], payload["transactions"])
    assert [item["insiderName"] for item in transaction_payload] == [
        "Insider 2",
        "Insider 1",
    ]
    assert transaction_payload[0]["filedAt"] == "2026-01-03T02:00:00Z"
    assert transaction_payload[0]["transactionDate"] == "2026-01-02T02:00:00Z"
    assert payload["warnings"] == [
        {
            "code": "insider_truncated",
            "message": "Insider transactions were truncated to 2 rows",
            "details": {"limit": "2", "symbol": "NVDA"},
        }
    ]


def test_market_data_indicator_snapshot_uses_bounded_ohlcv_without_lookahead(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider()
    start_date = datetime(2026, 1, 1, tzinfo=UTC)
    current_date = datetime(2026, 1, 3, 16, tzinfo=UTC)

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_indicator_snapshot(
            " nvda ",
            current_date=current_date,
            start_date=start_date,
            end_date=current_date,
            indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            row_limit=3,
        )

    assert provider.ohlcv_calls == [("NVDA", start_date, current_date, "1d")]
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fake_runtime_provider"
    assert payload["currentDate"] == "2026-01-03T16:00:00Z"
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"

    rows = cast(list[dict[str, object]], payload["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-01T00:00:00Z",
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]
    row_1_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[0]["values"])}
    assert row_1_values["close"] == {"name": "close", "value": "119.75", "nullReason": None}
    assert row_1_values["sma_2"] == {"name": "sma_2", "value": None, "nullReason": "warmup"}
    assert rows[1]["values"] == [
        {"name": "close", "value": "120.00", "nullReason": None},
        {"name": "sma_2", "value": "119.875", "nullReason": None},
    ]
    assert rows[2]["values"] == [
        {"name": "close", "value": "120.25", "nullReason": None},
        {"name": "sma_2", "value": "120.125", "nullReason": None},
    ]
    assert "999" not in str(rows)


def test_market_data_indicator_snapshot_marks_insufficient_history_nulls(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider()

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        result = service.get_indicator_snapshot(
            "nvda",
            current_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            start_date=datetime(2026, 1, 1, tzinfo=UTC),
            end_date=datetime(2026, 1, 3, 16, tzinfo=UTC),
            indicators=(MarketIndicatorSelection(indicator="sma", window=5),),
            row_limit=3,
        )

    payload = result.model_dump(mode="json", by_alias=True)
    rows = cast(list[dict[str, object]], payload["rows"])
    for row in rows:
        values = cast(list[dict[str, object]], row["values"])
        assert values[1] == {
            "name": "sma_5",
            "value": None,
            "nullReason": "insufficient_history",
        }


def test_market_data_indicator_snapshot_rejects_invalid_bounds_and_future_rows(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _RecordingQuoteProvider()

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="startDate must be before"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=datetime(2026, 1, 4, tzinfo=UTC),
                start_date=datetime(2026, 1, 4, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )
        with pytest.raises(QuoteProviderError, match="endDate cannot be after currentDate"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=datetime(2026, 1, 2, tzinfo=UTC),
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )

    assert provider.ohlcv_calls == []

    current_date = datetime(2026, 1, 3, tzinfo=UTC)

    def fake_get_ohlcv_snapshot(
        self: MarketDataService,
        symbols: list[str],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int | None = None,
    ) -> RuntimeOhlcvLookupResult:
        del self, symbols, row_limit
        return RuntimeOhlcvLookupResult(
            start_date=start_date,
            end_date=end_date,
            series=[
                RuntimeOhlcvSeries(
                    symbol="NVDA",
                    currency="USD",
                    provider="fake_runtime_provider",
                    rows=[
                        RuntimeOhlcvRow(
                            at=current_date + timedelta(minutes=1),
                            open=Decimal("100"),
                            high=Decimal("101"),
                            low=Decimal("99"),
                            close=Decimal("100"),
                            volume=1000,
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(MarketDataService, "get_ohlcv_snapshot", fake_get_ohlcv_snapshot)
    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="cannot be after currentDate"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=current_date,
                start_date=current_date,
                end_date=current_date,
                indicators=(MarketIndicatorSelection(indicator="sma", window=2),),
            )


def test_market_data_ohlcv_snapshot_rejects_invalid_bounds_and_row_limits(
    session_factory: sessionmaker[Session],
) -> None:
    provider = _RecordingQuoteProvider()

    with session_factory() as session:
        service = MarketDataService(session=session, quote_provider=provider)
        with pytest.raises(QuoteProviderError, match="startDate must be before"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 4, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
            )
        with pytest.raises(QuoteProviderError, match="rowLimit must be at least 1"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                row_limit=0,
            )
        with pytest.raises(QuoteProviderError, match="rowLimit must be at most 500"):
            _ = service.get_ohlcv_snapshot(
                ["nvda"],
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
                row_limit=501,
            )

    assert provider.ohlcv_calls == []


def test_report_lookup_source_schema_includes_agent() -> None:
    parameters = REPORT_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], parameters["properties"])
    source_property = cast(dict[str, object], properties["source"])
    assert source_property["enum"] == ["compiled", "uploaded", "external", "agent", None]


def test_report_lookup_accepts_agent_source() -> None:
    parsed = parse_report_lookup_arguments('{"source":"agent"}')
    assert parsed["source"] == "agent"


def test_runtime_tool_spec_is_frozen_and_separates_display_metadata_from_execution_fields() -> None:
    assert REPORT_LOOKUP_TOOL_KEY == "signaldeck.finance.reports.lookup"
    assert REPORT_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_finance_reports_lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key == REPORT_LOOKUP_TOOL_KEY
    assert REPORT_LOOKUP_TOOL_SPEC.openai_function_name == REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    assert REPORT_LOOKUP_TOOL_SPEC.display_name == "Report Lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.description

    assert MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC.key == MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY
    assert (
        MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC.openai_function_name
        == MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC.display_name == "Market Data Quote Lookup"
    assert MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC.key == MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY
    assert (
        MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC.openai_function_name
        == MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC.display_name == "Market Data History Lookup"

    field_name = "key"
    with pytest.raises(FrozenInstanceError):
        setattr(REPORT_LOOKUP_TOOL_SPEC, field_name, "signaldeck.changed")


def test_runtime_tool_context_carries_execution_identity_for_trusted_tools() -> None:
    capability_references: list[dict[str, object]] = [
        {"capabilityKey": "report_writer", "capabilityVersion": 3}
    ]
    quote_provider = _RecordingQuoteProvider()
    context = _runtime_context(
        capability_references=capability_references,
        quote_provider=quote_provider,
        run_id=42,
        agent_key="portfolio_manager",
        agent_version=7,
        agent_name="Portfolio Manager",
        workflow_key="daily_review",
        workflow_version=2,
        step_id="portfolio_decision",
        slot="decision",
        trace_id="trace-123",
    )

    assert context.session_factory is not None
    assert context.capability_references == capability_references
    assert context.provider_bundle.payload_for(FINANCE_WORKSPACE_EXTENSION_KEY) is not None
    assert context.run_id == 42
    assert context.agent_key == "portfolio_manager"
    assert context.agent_version == 7
    assert context.agent_name == "Portfolio Manager"
    assert context.workflow_key == "daily_review"
    assert context.workflow_version == 2
    assert context.step_id == "portfolio_decision"
    assert context.slot == "decision"
    assert context.trace_id == "trace-123"


def test_runtime_tool_registry_rejects_duplicate_keys_and_openai_function_names() -> None:
    spec = _runtime_tool_spec()

    with pytest.raises(ValueError, match="Duplicate runtime tool key"):
        _ = RuntimeToolRegistry(
            [spec, replace(spec, openai_function_name="signaldeck_test_lookup_alt")]
        )

    with pytest.raises(ValueError, match="Duplicate runtime tool OpenAI function name"):
        _ = RuntimeToolRegistry([spec, replace(spec, key="signaldeck.test.lookup.alt")])


def test_runtime_tool_registry_returns_granted_strict_definitions_in_sort_order() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC, MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])

    tools = registry.get_openai_tools({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in tools] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)
    assert tools[0]["description"] == (
        "Read persisted SignalDeck reports by ticker, tag, review type, source, limit, and offset."
    )

    report_parameters = cast(dict[str, object], tools[0]["parameters"])
    report_properties = cast(dict[str, dict[str, object]], report_parameters["properties"])
    assert set(cast(list[str], report_parameters["required"])) == {
        "ticker",
        "tag",
        "reviewType",
        "source",
        "limit",
        "offset",
    }
    source_property = cast(dict[str, object], report_properties["source"])
    assert source_property["enum"] == [
        "compiled",
        "uploaded",
        "external",
        "agent",
        None,
    ]
    quote_only_tools = registry.get_openai_tools({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in quote_only_tools] == [
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME
    ]


def test_runtime_tool_registry_returns_signaldeck_declarations_in_sort_order() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC, MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])

    declarations = registry.get_tool_declarations(
        {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}
    )

    assert [declaration.tool_key for declaration in declarations] == [
        REPORT_LOOKUP_TOOL_KEY,
        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    ]
    assert [declaration.model_name for declaration in declarations] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert {declaration.kind for declaration in declarations} == {"native_runtime"}
    assert all(declaration.strict for declaration in declarations)
    report_schema = cast(dict[str, object], declarations[0].input_schema)
    assert report_schema["required"] == sorted(
        [
            "ticker",
            "tag",
            "reviewType",
            "source",
            "limit",
            "offset",
        ]
    )


def test_runtime_tool_registry_closes_nested_object_schema() -> None:
    nested_spec = replace(
        _runtime_tool_spec(),
        parameters_schema={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                }
            },
            "required": ["payload"],
            "additionalProperties": False,
        },
    )

    registry = RuntimeToolRegistry([nested_spec])
    descriptor = registry.list_execution_descriptors()[0]
    properties = cast(dict[str, object], descriptor.strict_schema["properties"])
    payload_schema = cast(dict[str, object], properties["payload"])

    assert payload_schema["additionalProperties"] is False
    assert payload_schema["required"] == ["value"]


def test_default_runtime_tool_registry_exposes_financial_runtime_specs() -> None:
    registry = get_default_runtime_tool_registry()

    spec_by_key = {spec.key: spec for spec in registry.list_specs()}
    assert spec_by_key[REPORT_LOOKUP_TOOL_KEY].openai_function_name == (
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY].openai_function_name == (
        SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[PREDICTION_MARKETS_LOOKUP_TOOL_KEY].openai_function_name == (
        PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[SEC_FILINGS_LOOKUP_TOOL_KEY].openai_function_name == (
        SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_SENTIMENT_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    tools = registry.get_openai_tools(
        {
            REPORT_LOOKUP_TOOL_KEY,
            MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
            SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
        }
    )
    assert [tool["name"] for tool in tools] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
        SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)


def test_model_facing_runtime_tool_declarations_keep_provider_secrets_internal() -> None:
    registry = get_default_runtime_tool_registry()
    granted_tool_keys = {
        SEC_FILINGS_LOOKUP_TOOL_KEY,
        MACRO_RATES_LOOKUP_TOOL_KEY,
        NEWS_LOOKUP_TOOL_KEY,
    }
    declarations = [
        {
            "kind": declaration.kind,
            "toolKey": declaration.tool_key,
            "modelName": declaration.model_name,
            "description": declaration.description,
            "inputSchema": declaration.input_schema,
            "schemaHash": declaration.schema_hash,
            "strict": declaration.strict,
            "ownerExtensionKey": declaration.owner_extension_key,
        }
        for declaration in registry.get_tool_declarations(granted_tool_keys)
    ]
    serialized_declarations = json.dumps(
        {
            "openaiTools": registry.get_openai_tools(granted_tool_keys),
            "signaldeckTools": declarations,
            "parametersSchemas": [
                SEC_FILINGS_LOOKUP_TOOL_SPEC.parameters_schema,
                MACRO_RATES_LOOKUP_TOOL_SPEC.parameters_schema,
                NEWS_LOOKUP_TOOL_SPEC.parameters_schema,
            ],
        },
        sort_keys=True,
    )

    for forbidden_name in (
        "apiKey",
        "fredApiKey",
        "edgarContactEmail",
        "contactEmail",
    ):
        assert forbidden_name not in serialized_declarations


def test_digital_oracle_runtime_registry_denies_ungranted_tools_before_parsing() -> None:
    registry = get_default_runtime_tool_registry()
    context = _runtime_context(fail_on_session=True)
    cases = (
        (PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME, PREDICTION_MARKETS_LOOKUP_TOOL_KEY),
        (SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME, SEC_FILINGS_LOOKUP_TOOL_KEY),
        (MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME, MARKET_SENTIMENT_LOOKUP_TOOL_KEY),
    )

    for function_name, tool_key in cases:
        with pytest.raises(RuntimeToolError) as exc_info:
            _ = registry.dispatch(
                name=function_name,
                arguments_json="not-json",
                granted_tool_keys=set(),
                context=context,
            )

        assert exc_info.value.code == "agent_execution_access_denied"
        assert exc_info.value.message == DIGITAL_ORACLE_DENIED_MESSAGES[tool_key]


def test_financial_runtime_tool_exposure_follows_quote_history_and_report_lookup_grants() -> None:
    registry = get_default_runtime_tool_registry()

    quote_only = registry.get_openai_tools({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY})
    quote_history = registry.get_openai_tools(
        {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY}
    )
    all_native_financial = registry.get_openai_tools(
        {
            MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
            REPORT_LOOKUP_TOOL_KEY,
        }
    )

    assert [tool["name"] for tool in quote_only] == [MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME]
    assert [tool["name"] for tool in quote_history] == [
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert [tool["name"] for tool in all_native_financial] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]


def test_runtime_tool_registry_deep_copies_openai_parameter_schemas() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    tools = registry.get_openai_tools({REPORT_LOOKUP_TOOL_KEY})
    parameters = cast(dict[str, object], tools[0]["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    ticker_property = cast(dict[str, object], properties["ticker"])
    ticker_property["type"] = "mutated"

    fresh_tools = registry.get_openai_tools({REPORT_LOOKUP_TOOL_KEY})

    fresh_parameters = cast(dict[str, object], fresh_tools[0]["parameters"])
    fresh_properties = cast(dict[str, object], fresh_parameters["properties"])
    fresh_ticker_property = cast(dict[str, object], fresh_properties["ticker"])
    assert fresh_ticker_property["type"] == [
        "string",
        "null",
    ]


def test_runtime_tool_registry_aggregates_guidance_in_sort_order() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC, MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])

    assert registry.get_guidance({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}) == (
        "When you need persisted SignalDeck report context, call the "
        "signaldeck_finance_reports_lookup tool instead of inventing report content.\n\n"
        "When you need current or delayed market quotes, call the "
        "signaldeck_finance_market_data_quote_lookup tool instead of inventing prices. "
        "Disclose returned warnings or empty payloads as "
        "data quality or provider limitations."
    )
    assert registry.get_guidance(set()) == ""


def test_generic_platform_runtime_guidance_discloses_provider_limitations() -> None:
    registry = get_default_runtime_tool_registry()

    guidance = registry.get_guidance(set(_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS))

    assert "call signaldeck_finance_market_data_ohlcv_lookup" in guidance
    assert "call signaldeck_finance_indicators_lookup" in guidance
    assert "call signaldeck_finance_fundamentals_lookup" in guidance
    assert "instead of inventing metrics" in guidance
    assert "call signaldeck_finance_news_lookup" in guidance
    assert "instead of inventing articles" in guidance
    assert "call signaldeck_finance_social_sentiment_lookup" in guidance
    assert "instead of treating news as social data" in guidance
    assert "call signaldeck_finance_insider_data_lookup" in guidance
    assert "Disclose warnings or empty results as data quality" in guidance
    assert guidance.count("data quality or provider limitations") >= 6
    assert "do not claim unavailable coverage" in guidance
    assert "do not present unsupported provider coverage" in guidance


def test_runtime_tool_grant_service_resolves_package_tool_keys_and_fails_closed() -> None:
    service = RuntimeToolGrantService(get_default_tool_catalog())
    capability_references = [
        _capability_reference(tools=[REPORT_LOOKUP_TOOL_KEY, MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY])
    ]

    assert service.resolve_granted_tool_keys(capability_references) == {
        REPORT_LOOKUP_TOOL_KEY,
        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    }
    service.require_runtime_tool_grant(
        capability_references=capability_references,
        grant_policy=REPORT_LOOKUP_GRANT_POLICY,
    )
    with pytest.raises(RuntimeToolGrantError) as exc_info:
        service.require_runtime_tool_grant(
            capability_references=[_capability_reference(tools=["signaldeck.stale.lookup"])],
            grant_policy=REPORT_LOOKUP_GRANT_POLICY,
        )

    assert exc_info.value.code == "capability_tool_keys_invalid"
    assert "stale or invalid tool keys" in exc_info.value.message
    assert exc_info.value.details == [
        {
            "field": "toolKeys.0",
            "issue": "Unknown server-declared tool 'signaldeck.stale.lookup'",
        }
    ]


def test_runtime_tool_registry_rejects_unknown_and_ungranted_names_before_parsing() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as unknown_error:
        _ = registry.dispatch(
            name="signaldeck_unknown_lookup",
            arguments_json='{"ticker":"NVDA"}',
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert unknown_error.value.code == "agent_tool_call_unsupported"
    assert (
        unknown_error.value.message
        == "Agent requested unsupported server tool 'signaldeck_unknown_lookup'."
    )

    with pytest.raises(RuntimeToolError) as ungranted_error:
        _ = registry.dispatch(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert ungranted_error.value.code == "agent_execution_access_denied"
    assert ungranted_error.value.message == (
        "Agent is not authorized to use signaldeck.finance.reports.lookup."
    )


def test_agent_execution_native_to_mcp_fallback_only_for_unsupported_tool_calls() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)
    mcp_dispatcher = _RecordingMcpDispatcher()

    output = AgentExecutionService._dispatch_function_call(
        tool_call=ModelToolCall(
            tool_name="mcp_external_lookup",
            arguments_json='{"ticker":"NVDA"}',
            call_id="call-mcp",
        ),
        granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
        runtime_tool_registry=registry,
        runtime_tool_context=context,
        mcp_dispatcher=cast(Any, mcp_dispatcher),
    )

    assert output == {"output": {"ok": True}, "toolKey": "mcp.fake"}
    assert mcp_dispatcher.calls == [
        {"arguments_json": '{"ticker":"NVDA"}', "name": "mcp_external_lookup"}
    ]

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = AgentExecutionService._dispatch_function_call(
            tool_call=ModelToolCall(
                tool_name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
                arguments_json="not-json",
                call_id="call-denied",
            ),
            granted_tool_keys=set(),
            runtime_tool_registry=registry,
            runtime_tool_context=context,
            mcp_dispatcher=cast(Any, mcp_dispatcher),
        )

    assert exc_info.value.code == "agent_execution_access_denied"
    assert exc_info.value.message == (
        "Agent is not authorized to use signaldeck.finance.reports.lookup."
    )
    assert mcp_dispatcher.calls == [
        {"arguments_json": '{"ticker":"NVDA"}', "name": "mcp_external_lookup"}
    ]

    with pytest.raises(RuntimeToolError) as native_unknown_error:
        _ = AgentExecutionService._dispatch_function_call(
            tool_call=ModelToolCall(
                tool_name="signaldeck_unknown_lookup",
                arguments_json='{"ticker":"NVDA"}',
                call_id="call-native-unknown",
            ),
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            runtime_tool_registry=registry,
            runtime_tool_context=context,
            mcp_dispatcher=cast(Any, mcp_dispatcher),
        )

    assert native_unknown_error.value.code == "agent_tool_call_unsupported"
    assert native_unknown_error.value.retryable is False
    assert mcp_dispatcher.calls == [
        {"arguments_json": '{"ticker":"NVDA"}', "name": "mcp_external_lookup"}
    ]


def test_failure_taxonomy_retryable_allowlist_is_closed_to_parser_schema_failures() -> None:
    assert RETRYABLE_FAILURE_CLASSES == {
        ToolFailureClass.PROVIDER_TOOL_ARGUMENT_JSON_INVALID,
        ToolFailureClass.PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID,
        ToolFailureClass.NATIVE_TOOL_ARGUMENT_VALIDATION,
        ToolFailureClass.MCP_TOOL_ARGUMENT_JSON_INVALID,
        ToolFailureClass.MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
    }
    assert ToolFailureClass.PROVIDER_NETWORK not in RETRYABLE_FAILURE_CLASSES
    assert ToolFailureClass.MCP_TRANSPORT not in RETRYABLE_FAILURE_CLASSES


def test_failure_taxonomy_marks_provider_payload_invalid_json_as_retryable() -> None:
    with pytest.raises(ModelGatewayError) as exc_info:
        _ = build_model_tool_call(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments="{",
            call_id="call-invalid-json",
            context="OpenAI response",
        )

    exc = exc_info.value
    assert exc.code == "model_tool_call_payload_invalid"
    assert exc.failure_class == ToolFailureClass.PROVIDER_TOOL_ARGUMENT_JSON_INVALID.value
    assert exc.retryable is True
    assert exc.runtime_metadata()["failureTaxonomy"] == {
        "failureClass": "provider_tool_argument_json_invalid",
        "retryable": True,
        "disposition": "retryable",
        "phase": "pre_dispatch",
        "source": "provider",
    }


def test_failure_taxonomy_marks_provider_payload_non_object_arguments_as_retryable() -> None:
    with pytest.raises(ModelGatewayError) as exc_info:
        _ = build_model_tool_call(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments="[]",
            call_id="call-non-object",
            context="OpenAI response",
        )

    exc = exc_info.value
    assert exc.failure_class == ToolFailureClass.PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID.value
    assert exc.retryable is True


def test_failure_taxonomy_marks_native_argument_validation_retryable_before_execution() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"limit":51}',
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            context=context,
        )

    exc = exc_info.value
    assert exc.code == "agent_tool_call_invalid"
    assert exc.failure_class == ToolFailureClass.NATIVE_TOOL_ARGUMENT_VALIDATION.value
    assert exc.retryable is True


def test_failure_taxonomy_marks_mcp_invalid_json_and_schema_retryable_before_transport() -> None:
    client = _RecordingMcpToolClient()
    dispatcher = _failure_taxonomy_mcp_dispatcher(client)

    with pytest.raises(RuntimeToolError) as invalid_json:
        _ = dispatcher.dispatch(name="mcp_taxonomy_vendor_lookup", arguments_json="{")
    assert invalid_json.value.failure_class == (
        ToolFailureClass.MCP_TOOL_ARGUMENT_JSON_INVALID.value
    )
    assert invalid_json.value.retryable is True
    assert client.calls == []

    with pytest.raises(RuntimeToolError) as schema_error:
        _ = dispatcher.dispatch(
            name="mcp_taxonomy_vendor_lookup",
            arguments_json='{"ticker":123,"extra":true}',
        )
    assert schema_error.value.failure_class == (
        ToolFailureClass.MCP_TOOL_ARGUMENT_SCHEMA_INVALID.value
    )
    assert schema_error.value.retryable is True
    assert schema_error.value.details == [
        {"field": "extra", "issue": "Unsupported field"},
    ]
    retry_state = ModelToolCallRetryState()
    assert retry_state.can_retry(schema_error.value) is True
    assert retry_state.record_retry(schema_error.value)
    assert retry_state.metadata() == {
        "attemptsUsed": 1,
        "maxAttempts": 1,
        "exhausted": False,
        "failures": [
            {
                "code": "mcp_tool_arguments_invalid",
                "failureTaxonomy": {
                    "failureClass": "mcp_tool_argument_schema_invalid",
                    "retryable": True,
                    "disposition": "retryable",
                    "phase": "pre_dispatch",
                    "source": "mcp_tool",
                },
                "details": [
                    {"field": "extra", "issue": "Unsupported field"},
                ],
            }
        ],
    }
    assert client.calls == []


def test_failure_taxonomy_auth_secret_provider_network_classes_are_fatal() -> None:
    expected = {
        "agent_model_connection_api_key_missing": ToolFailureClass.SECRET_CONTEXT,
        "agent_execution_access_denied": ToolFailureClass.PERMISSION,
        "agent_provider_connection_error": ToolFailureClass.PROVIDER_NETWORK,
        "mcp_runtime_transport_unavailable": ToolFailureClass.MCP_TRANSPORT,
        "agent_result_invalid": ToolFailureClass.EXECUTOR,
    }
    for code, expected_class in expected.items():
        classification = classification_for_error_code(code)
        assert classification.failure_class is expected_class
        assert classification.retryable is False
        assert classification.disposition.value == "fatal"

    auth_classification = provider_status_failure_classification(401)
    assert auth_classification.failure_class is ToolFailureClass.AUTH
    assert auth_classification.retryable is False
    assert provider_status_failure_classification(429).failure_class is (
        ToolFailureClass.PROVIDER_TRANSPORT
    )

    retry_state = ModelToolCallRetryState()
    provider_network_error = ModelGatewayError(
        code="agent_provider_connection_error",
        message="OpenAI request could not reach the API.",
    )
    mcp_transport_error = RuntimeToolError(
        code="mcp_runtime_transport_error",
        message="MCP runtime transport failed while calling a server tool.",
    )
    assert retry_state.can_retry(provider_network_error) is False
    assert retry_state.can_retry(mcp_transport_error) is False
    assert retry_state.metadata() is None


def test_market_data_runtime_tool_registry_denies_ungranted_tools_before_parsing() -> None:
    registry = RuntimeToolRegistry(
        [MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC, MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC]
    )
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as quote_error:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert quote_error.value.code == MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE
    assert quote_error.value.message == MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE

    with pytest.raises(RuntimeToolError) as history_error:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert history_error.value.code == MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE
    assert history_error.value.message == MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE


def test_market_data_quote_lookup_service_denies_missing_capability_reference_grant(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"]}',
            granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            context=_runtime_context(
                capability_references=[
                    _capability_reference(tools=[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY])
                ],
                session_factory_override=session_factory,
                quote_provider=quote_provider,
            ),
        )

    assert exc_info.value.code == MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE
    assert exc_info.value.message == MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE
    assert quote_provider.quote_calls == []


def test_market_data_history_lookup_service_denies_missing_capability_reference_grant(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"range":"3mo","pointLimit":2}',
            granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            context=_runtime_context(
                capability_references=[
                    _capability_reference(tools=[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY])
                ],
                session_factory_override=session_factory,
                quote_provider=quote_provider,
            ),
        )

    assert exc_info.value.code == MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE
    assert exc_info.value.message == MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE
    assert quote_provider.history_calls == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested signaldeck_finance_reports_lookup with invalid JSON "
            + "arguments.",
        ),
        ("[]", "signaldeck_finance_reports_lookup arguments must be a JSON object."),
        (
            '{"unsupported":true}',
            "signaldeck_finance_reports_lookup arguments contained unsupported fields: unsupported",
        ),
        (
            '{"source":"manual"}',
            (
                "signaldeck_finance_reports_lookup source must be one of compiled, uploaded, "
                "external, or agent."
            ),
        ),
        (
            '{"source":"agent"}',
            None,
        ),
        ('{"ticker":123}', "signaldeck_finance_reports_lookup string arguments must be strings."),
        ('{"limit":51}', "signaldeck_finance_reports_lookup limit must be at most 50."),
        ('{"offset":-1}', "signaldeck_finance_reports_lookup offset must be at least 0."),
    ],
)
def test_report_runtime_tool_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str | None,
) -> None:
    if expected_message is None:
        assert parse_report_lookup_arguments(arguments_json)["source"] == "agent"
        return

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_report_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested signaldeck_finance_market_data_quote_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_finance_market_data_quote_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_finance_market_data_quote_lookup arguments contained "
                "unsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_finance_market_data_quote_lookup symbols is required."),
        (
            '{"symbols":"NVDA"}',
            "signaldeck_finance_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[]}',
            "signaldeck_finance_market_data_quote_lookup symbols must contain at least one symbol.",
        ),
        (
            '{"symbols":["A","B","C","D","E","F","G","H","I","J","K"]}',
            "signaldeck_finance_market_data_quote_lookup symbols must contain at most 10 symbols.",
        ),
    ],
)
def test_market_data_quote_lookup_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_quote_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested signaldeck_finance_market_data_history_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_finance_market_data_history_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_finance_market_data_history_lookup arguments contained "
                "unsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_finance_market_data_history_lookup symbols is required."),
        (
            '{"symbols":["NVDA"],"range":"10y"}',
            "signaldeck_finance_market_data_history_lookup range must be one of 1mo, "
            + "3mo, ytd, 1y, or max.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":"2"}',
            "signaldeck_finance_market_data_history_lookup pointLimit must be an integer.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":251}',
            "signaldeck_finance_market_data_history_lookup pointLimit must be at most 250.",
        ),
    ],
)
def test_market_data_history_lookup_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_history_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("parser", "arguments_json", "expected_arguments"),
    [
        (
            parse_ohlcv_lookup_arguments,
            json.dumps(
                {
                    "symbols": [" nvda ", "NVDA", "aapl"],
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T16:00:00-05:00",
                    "rowLimit": 3,
                }
            ),
            {
                "symbols": ["NVDA", "AAPL"],
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": datetime(2026, 1, 3, 21, tzinfo=UTC),
                "row_limit": 3,
            },
        ),
        (
            parse_indicators_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "currentDate": "2026-01-03T16:00:00Z",
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-03T12:00:00-04:00",
                    "indicators": [
                        {"type": "SMA", "window": 20},
                        {"type": "ema", "window": 5},
                        {"type": "sma", "window": 20},
                    ],
                    "rowLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "current_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "indicators": (
                    MarketIndicatorSelection(indicator="sma", window=20),
                    MarketIndicatorSelection(indicator="ema", window=5),
                ),
                "row_limit": 250,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "metricNames": [" Revenue_Growth ", "market_cap", "market_cap"],
                    "statementTypes": [" Income_Statement ", "cash_flow", "cash_flow"],
                    "periods": ["ANNUAL", "trailing_twelve_months"],
                    "statementLimit": 2,
                }
            ),
            {
                "symbol": "NVDA",
                "metric_names": ("revenue_growth", "market_cap"),
                "statement_types": ("income_statement", "cash_flow"),
                "periods": ("annual", "trailing_twelve_months"),
                "statement_limit": 2,
            },
        ),
        (
            parse_news_lookup_arguments,
            json.dumps(
                {
                    "symbols": [" nvda ", "AAPL", "NVDA"],
                    "query": " earnings ",
                    "startDate": "2026-01-01",
                    "endDate": None,
                    "itemLimit": 2,
                }
            ),
            {
                "symbols": ["NVDA", "AAPL"],
                "query": "earnings",
                "scope": "symbol",
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": None,
                "item_limit": 2,
            },
        ),
        (
            parse_social_sentiment_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "sources": ["Reddit", "stocktwits", "reddit"],
                    "startDate": "2026-01-01",
                    "endDate": None,
                    "itemLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "sources": ("reddit", "stocktwits"),
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": None,
                "item_limit": 25,
            },
        ),
        (
            parse_insider_data_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "startDate": None,
                    "endDate": "2026-01-03T16:00:00+00:00",
                    "transactionLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "start_date": None,
                "end_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "transaction_limit": 50,
            },
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_normalize_happy_paths(
    parser: Callable[[str], dict[str, object]],
    arguments_json: str,
    expected_arguments: dict[str, object],
) -> None:
    assert parser(arguments_json) == expected_arguments


def test_indicators_lookup_runtime_tool_spec_uses_expanded_selection_schema() -> None:
    assert INDICATORS_LOOKUP_TOOL_SPEC.key == INDICATORS_LOOKUP_TOOL_KEY
    assert (
        INDICATORS_LOOKUP_TOOL_SPEC.openai_function_name == INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert INDICATORS_LOOKUP_TOOL_SPEC.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert INDICATORS_LOOKUP_TOOL_SPEC.parser is parse_indicators_lookup_arguments

    schema = INDICATORS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    indicators_property = cast(dict[str, object], properties["indicators"])
    indicator_items = cast(dict[str, object], indicators_property["items"])
    indicator_item_properties = cast(dict[str, object], indicator_items["properties"])
    indicator_type_property = cast(dict[str, object], indicator_item_properties["type"])
    assert schema["required"] == [
        "symbol",
        "currentDate",
        "startDate",
        "endDate",
        "indicators",
        "rowLimit",
    ]
    assert set(properties) == {
        "symbol",
        "currentDate",
        "startDate",
        "endDate",
        "indicators",
        "rowLimit",
    }
    assert indicators_property["type"] == "array"
    assert indicators_property["maxItems"] == 24
    assert indicator_type_property["enum"] == [
        "sma",
        "ema",
        "rsi",
        "macd",
        "bollinger_bands",
        "atr",
        "vwma",
    ]


def test_fundamentals_lookup_runtime_tool_spec_uses_metric_selection_schema() -> None:
    assert FUNDAMENTALS_LOOKUP_TOOL_SPEC.key == FUNDAMENTALS_LOOKUP_TOOL_KEY
    assert (
        FUNDAMENTALS_LOOKUP_TOOL_SPEC.openai_function_name
        == FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert FUNDAMENTALS_LOOKUP_TOOL_SPEC.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert FUNDAMENTALS_LOOKUP_TOOL_SPEC.parser is parse_fundamentals_lookup_arguments

    schema = FUNDAMENTALS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    metric_names_property = cast(dict[str, object], properties["metricNames"])
    metric_name_items = cast(dict[str, object], metric_names_property["items"])
    assert schema["required"] == [
        "symbol",
        "metricNames",
        "statementTypes",
        "periods",
        "statementLimit",
    ]
    assert metric_names_property["type"] == ["array", "null"]
    assert metric_name_items["enum"] == [
        "beta",
        "current_ratio",
        "debt_to_equity",
        "dividend_yield",
        "earnings_growth",
        "enterprise_value",
        "ev_to_ebitda",
        "forward_pe",
        "free_cash_flow_margin",
        "gross_margin",
        "market_cap",
        "net_margin",
        "operating_margin",
        "price_to_book",
        "price_to_sales",
        "return_on_assets",
        "return_on_equity",
        "revenue_growth",
        "trailing_pe",
    ]


@pytest.mark.parametrize(
    ("parser", "function_name", "valid_arguments"),
    [
        (
            parse_ohlcv_lookup_arguments,
            MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
        ),
        (
            parse_indicators_lookup_arguments,
            INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 3,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            },
        ),
        (
            parse_news_lookup_arguments,
            NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
        ),
        (
            parse_social_sentiment_lookup_arguments,
            SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
        ),
        (
            parse_insider_data_lookup_arguments,
            INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "transactionLimit": 2,
            },
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_reject_boundary_payloads(
    parser: Callable[[str], dict[str, object]],
    function_name: str,
    valid_arguments: dict[str, object],
) -> None:
    with pytest.raises(RuntimeToolError) as invalid_json_error:
        _ = parser("{")
    assert invalid_json_error.value.code == "agent_tool_call_invalid"
    assert invalid_json_error.value.message == (
        f"OpenAI response requested {function_name} with invalid JSON arguments."
    )

    with pytest.raises(RuntimeToolError) as non_object_error:
        _ = parser("[]")
    assert non_object_error.value.code == "agent_tool_call_invalid"
    assert non_object_error.value.message == f"{function_name} arguments must be a JSON object."

    invalid_arguments = {**valid_arguments, "unsupported": True}
    with pytest.raises(RuntimeToolError) as unexpected_field_error:
        _ = parser(json.dumps(invalid_arguments))
    assert unexpected_field_error.value.code == "agent_tool_call_invalid"
    assert unexpected_field_error.value.message == (
        f"{function_name} arguments contained unsupported fields: unsupported"
    )


@pytest.mark.parametrize(
    ("parser", "arguments", "expected_message"),
    [
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
            "signaldeck_finance_market_data_ohlcv_lookup startDate must be before or "
            + "equal to endDate.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["A", "B", "C", "D", "E", "F"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
            "signaldeck_finance_market_data_ohlcv_lookup symbols must contain at most 5 symbols.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 501,
            },
            "signaldeck_finance_market_data_ohlcv_lookup rowLimit must be at most 500.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-02",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup endDate cannot be after currentDate.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "sma", "window": 2}],
                "rowLimit": 501,
            },
            "signaldeck_finance_indicators_lookup rowLimit must be at most 500.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [{"type": "stochastic", "window": 2}],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup indicator type must use: atr, "
            + "bollinger_bands, ema, macd, rsi, sma, vwma.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "indicators": [
                    {"type": "macd", "fastWindow": 12, "slowWindow": 12, "signalWindow": 9}
                ],
                "rowLimit": 3,
            },
            "signaldeck_finance_indicators_lookup MACD fastWindow must be less than slowWindow.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": ["statement"],
                "periods": None,
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup statementTypes must use: "
            + "balance_sheet, cash_flow, income_statement.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": ["daily"],
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup periods must use: "
            + "annual, quarterly, trailing_twelve_months.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 13,
            },
            "signaldeck_finance_fundamentals_lookup statementLimit must be at most 12.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "metricNames": ["unsupported_metric"],
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            },
            "signaldeck_finance_fundamentals_lookup metricNames must use: beta, "
            + "current_ratio, debt_to_equity, dividend_yield, earnings_growth, "
            + "enterprise_value, ev_to_ebitda, forward_pe, free_cash_flow_margin, "
            + "gross_margin, market_cap, net_margin, operating_margin, price_to_book, "
            + "price_to_sales, return_on_assets, return_on_equity, revenue_growth, "
            + "trailing_pe.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
            "signaldeck_finance_news_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["A", "B", "C", "D", "E", "F"],
                "query": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_news_lookup symbols must contain at most 5 symbols.",
        ),
        (
            parse_news_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "query": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "signaldeck_finance_news_lookup itemLimit must be at most 50.",
        ),
        (
            parse_social_sentiment_lookup_arguments,
            {
                "symbol": "NVDA",
                "sources": ["forums"],
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "signaldeck_finance_social_sentiment_lookup sources must use: reddit, stocktwits.",
        ),
        (
            parse_social_sentiment_lookup_arguments,
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "signaldeck_finance_social_sentiment_lookup itemLimit must be at most 50.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "transactionLimit": 2,
            },
            "signaldeck_finance_insider_data_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": None,
                "endDate": None,
                "transactionLimit": 101,
            },
            "signaldeck_finance_insider_data_lookup transactionLimit must be at most 100.",
        ),
    ],
)
def test_generic_platform_market_data_runtime_tool_parsers_reject_limits_and_bounds(
    parser: Callable[[str], dict[str, object]],
    arguments: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parser(json.dumps(arguments))

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


def test_registry_dispatch_rejects_invalid_arguments_before_service_execution() -> None:
    registry = RuntimeToolRegistry(
        [
            REPORT_LOOKUP_TOOL_SPEC,
            MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
            SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
        ]
    )
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as report_error:
        _ = registry.dispatch(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"limit":51}',
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert (
        report_error.value.message == "signaldeck_finance_reports_lookup limit must be at most 50."
    )

    with pytest.raises(RuntimeToolError) as quote_error:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"unsupported":true}',
            granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert quote_error.value.message == (
        "signaldeck_finance_market_data_quote_lookup arguments contained unsupported fields: "
        "unsupported"
    )

    with pytest.raises(RuntimeToolError) as history_error:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"pointLimit":251}',
            granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert history_error.value.message == (
        "signaldeck_finance_market_data_history_lookup pointLimit must be at most 250."
    )

    with pytest.raises(RuntimeToolError) as social_error:
        _ = registry.dispatch(
            name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbol":"NVDA","unsupported":true}',
            granted_tool_keys={SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert social_error.value.message == (
        "signaldeck_finance_social_sentiment_lookup arguments contained unsupported fields: "
        "unsupported"
    )


def test_reports_lookup_runtime_tool_dispatches_to_report_service_with_defaults_and_report_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_reports(
        self: ReportService,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        del self
        captured_calls.append(
            {
                "capability_references": capability_references,
                "grant_policy": grant_policy,
                "ticker": ticker,
                "tag": tag,
                "review_type": review_type,
                "source": source,
                "limit": limit,
                "offset": offset,
            }
        )
        return [_report_read()]

    monkeypatch.setattr(ReportService, "lookup_reports", fake_lookup_reports)

    payload = registry.dispatch(
        name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"ticker":" nvda "}',
        granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )

    assert captured_calls == [
        {
            "capability_references": [
                {
                    "toolKeys": [
                        REPORT_LOOKUP_TOOL_KEY,
                        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
                        MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
                    ]
                }
            ],
            "grant_policy": REPORT_LOOKUP_GRANT_POLICY,
            "ticker": "NVDA",
            "tag": None,
            "review_type": None,
            "source": None,
            "limit": 50,
            "offset": 0,
        }
    ]
    assert payload["count"] == 1
    reports = cast(list[dict[str, object]], payload["reports"])
    assert len(reports) == 1
    assert set(reports[0]) == {
        "id",
        "name",
        "slug",
        "source",
        "content",
        "metadata",
        "createdAt",
        "updatedAt",
    }
    assert reports[0]["id"] == 7
    assert reports[0]["name"] == "NVDA Backend Lookup"
    assert reports[0]["slug"] == "nvda_backend_lookup"
    assert reports[0]["source"] == "external"
    assert reports[0]["content"] == "# NVDA\n\nRevenue acceleration remains intact."
    assert reports[0]["metadata"] == {
        "author": None,
        "description": None,
        "tags": ["earnings"],
        "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
    }
    assert reports[0]["createdAt"] == "2026-01-02T03:04:05Z"
    assert reports[0]["updatedAt"] == "2026-01-02T03:04:05Z"


def test_market_data_quote_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider(failing_symbols={"BAD"})

    payload = registry.dispatch(
        name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"symbols":[" nvda ","NVDA","bad"]}',
        granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.quote_calls == ["NVDA", "BAD"]
    assert payload["toolKey"] == MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY
    quotes = cast(list[dict[str, object]], payload["quotes"])
    assert len(quotes) == 1
    assert quotes[0]["symbol"] == "NVDA"
    assert quotes[0]["previousClose"] == "119.75000000"
    assert quotes[0]["asOf"] == "2026-01-02T03:04:05Z"
    assert quotes[0]["isStale"] is True
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "quote_unavailable",
            "message": "No quote available for BAD",
            "details": {"symbol": "BAD"},
        }
    ]


def test_market_data_history_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider(failing_symbols={"BAD"})

    payload = registry.dispatch(
        name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"symbols":["nvda","bad"],"range":"3mo","pointLimit":2}',
        granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.history_calls == [("NVDA", "3mo", "1d"), ("BAD", "3mo", "1d")]
    assert payload["toolKey"] == MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY
    assert payload["range"] == "3mo"
    assert payload["interval"] == "1d"
    assert payload["startDate"] == "2026-01-02T00:00:00Z"
    assert payload["endDate"] == "2026-01-02T03:04:05Z"
    series = cast(list[dict[str, object]], payload["series"])
    assert len(series) == 1
    points = cast(list[dict[str, object]], series[0]["points"])
    assert points == [
        {"at": "2026-01-02T00:00:00Z", "close": "119.75"},
        {"at": "2026-01-02T03:04:05Z", "close": "120.25"},
    ]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "history_unavailable",
            "message": "No history available for BAD",
            "details": {"symbol": "BAD"},
        }
    ]


def test_market_data_ohlcv_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    payload = registry.dispatch(
        name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbols": [" nvda ", "NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03T16:00:00Z",
                "rowLimit": 2,
            }
        ),
        granted_tool_keys={MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.ohlcv_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, 16, tzinfo=UTC),
            "1d",
        )
    ]
    assert payload["toolKey"] == MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-03T16:00:00Z"
    series = cast(list[dict[str, object]], payload["series"])
    assert len(series) == 1
    rows = cast(list[dict[str, object]], series[0]["rows"])
    assert [row["at"] for row in rows] == [
        "2026-01-02T17:00:00Z",
        "2026-01-03T16:00:00Z",
    ]
    assert rows[0]["open"] == "119.00"
    assert rows[0]["adjustedClose"] == "119.80"
    assert rows[1]["close"] == "120.25"
    assert payload["warnings"] == []


def test_indicators_lookup_dispatches_success_and_insufficient_history_nulls(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([INDICATORS_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    payload = registry.dispatch(
        name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": " nvda ",
                "currentDate": "2026-01-03T16:00:00Z",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03T16:00:00Z",
                "indicators": [
                    {"type": "sma", "window": 2},
                    {"type": "ema", "window": 2},
                    {"type": "rsi", "window": 2},
                    {"type": "macd", "fastWindow": 1, "slowWindow": 2, "signalWindow": 2},
                    {"type": "bollinger_bands", "window": 2, "standardDeviations": 2},
                    {"type": "atr", "window": 2},
                    {"type": "vwma", "window": 2},
                    {"type": "sma", "window": 5},
                    {"type": "sma", "window": 2},
                ],
                "rowLimit": 3,
            }
        ),
        granted_tool_keys={INDICATORS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.ohlcv_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, 16, tzinfo=UTC),
            "1d",
        )
    ]
    assert payload["toolKey"] == INDICATORS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fake_runtime_provider"
    rows = cast(list[dict[str, object]], payload["rows"])
    row_1_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[0]["values"])}
    assert row_1_values["close"] == {"name": "close", "value": "119.75", "nullReason": None}
    assert row_1_values["sma_2"] == {"name": "sma_2", "value": None, "nullReason": "warmup"}
    row_2_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[1]["values"])}
    assert row_2_values["ema_2"] == {"name": "ema_2", "value": "119.875", "nullReason": None}
    assert row_2_values["atr_2"] == {"name": "atr_2", "value": "4.00", "nullReason": None}
    assert row_2_values["sma_5"] == {
        "name": "sma_5",
        "value": None,
        "nullReason": "insufficient_history",
    }
    row_3_values = {item["name"]: item for item in cast(list[dict[str, object]], rows[2]["values"])}
    assert row_3_values["sma_2"] == {"name": "sma_2", "value": "120.125", "nullReason": None}
    assert row_3_values["ema_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["ema_2"]["value"])) == Decimal("120.125")
    assert row_3_values["rsi_2"] == {"name": "rsi_2", "value": "100", "nullReason": None}
    assert row_3_values["macd_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_1_2_2"]["value"])) == Decimal("0.125")
    assert row_3_values["macd_signal_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_signal_1_2_2"]["value"])) == Decimal("0.125")
    assert row_3_values["macd_histogram_1_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["macd_histogram_1_2_2"]["value"])) == Decimal("0")
    assert row_3_values["bollinger_upper_2_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["bollinger_upper_2_2"]["value"])) == Decimal("120.375")
    assert row_3_values["bollinger_middle_2_2"] == {
        "name": "bollinger_middle_2_2",
        "value": "120.125",
        "nullReason": None,
    }
    assert row_3_values["bollinger_lower_2_2"] == {
        "name": "bollinger_lower_2_2",
        "value": "119.875",
        "nullReason": None,
    }
    assert row_3_values["atr_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["atr_2"]["value"])) == Decimal("3.25")
    assert row_3_values["vwma_2"]["nullReason"] is None
    assert Decimal(cast(str, row_3_values["vwma_2"]["value"])) == Decimal(
        "120.1304347826086956521739130"
    )
    assert payload["warnings"] == []


def test_fundamentals_lookup_dispatches_success_filters_and_limits_statements(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([FUNDAMENTALS_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(provider_name="fundamentals_primary")
    context = _runtime_context(
        session_factory_override=session_factory,
        quote_provider=quote_provider,
    )

    payload = registry.dispatch(
        name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": " nvda ",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            }
        ),
        granted_tool_keys={FUNDAMENTALS_LOOKUP_TOOL_KEY},
        context=context,
    )
    filtered_payload = registry.dispatch(
        name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": "NVDA",
                "metricNames": ["free_cash_flow_margin", "revenue_growth"],
                "statementTypes": ["cash_flow", "balance_sheet"],
                "periods": ["quarterly", "trailing_twelve_months"],
                "statementLimit": 1,
            }
        ),
        granted_tool_keys={FUNDAMENTALS_LOOKUP_TOOL_KEY},
        context=context,
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    _assert_native_runtime_payload_is_json_safe_and_camel(filtered_payload)
    assert quote_provider.fundamental_calls == ["NVDA", "NVDA"]
    assert payload["toolKey"] == FUNDAMENTALS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "fundamentals_primary"
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert [metric["name"] for metric in metrics] == [
        "market_cap",
        "revenue_growth",
        "free_cash_flow_margin",
    ]
    assert metrics[0] == {
        "name": "market_cap",
        "value": "1000000.50",
        "currency": "USD",
        "period": "ttm",
        "asOf": "2026-01-02T02:00:00Z",
    }
    statements = cast(list[dict[str, object]], payload["statements"])
    assert [statement["statementType"] for statement in statements] == [
        "income_statement",
        "balance_sheet",
        "cash_flow",
    ]
    assert [statement["period"] for statement in statements] == [
        "annual",
        "quarterly",
        "trailing_twelve_months",
    ]
    filtered_statements = cast(list[dict[str, object]], filtered_payload["statements"])
    filtered_metrics = cast(list[dict[str, object]], filtered_payload["metrics"])
    assert [metric["name"] for metric in filtered_metrics] == [
        "revenue_growth",
        "free_cash_flow_margin",
    ]
    assert filtered_statements == [
        {
            "statementType": "balance_sheet",
            "period": "quarterly",
            "periodEnd": "2025-11-01T02:00:00Z",
            "lines": [{"name": "assets", "value": "750000.00", "currency": "USD"}],
        }
    ]
    assert payload["warnings"] == []
    assert filtered_payload["warnings"] == []


def test_news_lookup_dispatches_success_and_truncates(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([NEWS_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(provider_name="news_primary", news_count=4)

    payload = registry.dispatch(
        name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbols": [" nvda ", "AAPL", "NVDA"],
                "query": " earnings ",
                "scope": "symbol",
                "startDate": "2026-01-01T19:00:00-05:00",
                "endDate": "2026-01-02T19:00:00-05:00",
                "itemLimit": 2,
            }
        ),
        granted_tool_keys={NEWS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
            news_providers=[quote_provider],
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [
        (
            ["NVDA", "AAPL"],
            "earnings",
            "symbol",
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            3,
        )
    ]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert payload["symbols"] == ["NVDA", "AAPL"]
    assert payload["query"] == "earnings"
    items = cast(list[dict[str, object]], payload["items"])
    assert [item["title"] for item in items] == ["News 3", "News 2"]
    assert payload["warnings"] == [
        {
            "code": "news_truncated",
            "message": "News results were truncated to 2 items",
            "details": {"limit": "2", "scope": "symbol"},
        }
    ]


def test_insider_data_lookup_dispatches_success_and_truncates(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([INSIDER_DATA_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(provider_name="insider_primary", insider_count=3)

    payload = registry.dispatch(
        name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": " nvda ",
                "startDate": "2026-01-01T00:00:00Z",
                "endDate": "2026-01-03T00:00:00Z",
                "transactionLimit": 2,
            }
        ),
        granted_tool_keys={INSIDER_DATA_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.insider_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            3,
        )
    ]
    assert payload["toolKey"] == INSIDER_DATA_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == "insider_primary"
    transactions = cast(list[dict[str, object]], payload["transactions"])
    assert [transaction["insiderName"] for transaction in transactions] == [
        "Insider 2",
        "Insider 1",
    ]
    assert payload["warnings"] == [
        {
            "code": "insider_truncated",
            "message": "Insider transactions were truncated to 2 rows",
            "details": {"limit": "2", "symbol": "NVDA"},
        }
    ]


def test_fundamentals_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([FUNDAMENTALS_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(
        provider_name="unsupported_fundamentals",
        failure=QuoteProviderError(
            "Fundamentals unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_fundamentals", "symbol": "NVDA"},
        ),
    )

    payload = registry.dispatch(
        name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": "NVDA",
                "metricNames": None,
                "statementTypes": None,
                "periods": None,
                "statementLimit": 3,
            }
        ),
        granted_tool_keys={FUNDAMENTALS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.fundamental_calls == ["NVDA"]
    assert payload["toolKey"] == FUNDAMENTALS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["metrics"] == []
    assert payload["statements"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "fundamentals_provider_unavailable",
        "fundamentals_unavailable",
    ]


def test_news_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([NEWS_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(
        provider_name="unsupported_news",
        failure=QuoteProviderError(
            "News unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_news", "symbols": "NVDA"},
        ),
    )

    payload = registry.dispatch(
        name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbols": ["NVDA"],
                "query": "earnings",
                "scope": "symbol",
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            }
        ),
        granted_tool_keys={NEWS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
            news_providers=[quote_provider],
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [(["NVDA"], "earnings", "symbol", None, None, 3)]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
    assert payload["symbols"] == ["NVDA"]
    assert payload["items"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "news_provider_unavailable",
        "news_unavailable",
    ]


def test_insider_data_lookup_provider_unavailable_returns_typed_empty_payload(
    session_factory: sessionmaker[Session],
) -> None:
    registry = RuntimeToolRegistry([INSIDER_DATA_LOOKUP_TOOL_SPEC])
    quote_provider = _FinancialContractProvider(
        provider_name="unsupported_insider",
        failure=QuoteProviderError(
            "Insider unsupported",
            code="provider_unavailable",
            details={"provider": "unsupported_insider", "symbol": "NVDA"},
        ),
    )

    payload = registry.dispatch(
        name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": "NVDA",
                "startDate": None,
                "endDate": None,
                "transactionLimit": 2,
            }
        ),
        granted_tool_keys={INSIDER_DATA_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.insider_calls == [("NVDA", None, None, 3)]
    assert payload["toolKey"] == INSIDER_DATA_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["provider"] == ""
    assert payload["transactions"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "insider_provider_unavailable",
        "insider_unavailable",
    ]


def test_prediction_markets_runtime_tool_spec_and_parser_normalize_arguments() -> None:
    schema = PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.parameters_schema

    assert PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.key == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert (
        PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.openai_function_name
        == PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert schema["required"] == ["query"]
    properties = cast(dict[str, object], schema["properties"])
    venues_schema = cast(dict[str, object], properties["venues"])
    venues_items = cast(dict[str, object], venues_schema["items"])
    assert venues_items["enum"] == ["polymarket", "kalshi"]

    parsed = parse_prediction_markets_lookup_arguments(
        json.dumps(
            {
                "query": "  Fed   rate   cuts  ",
                "venues": [" Kalshi ", "polymarket", "kalshi"],
                "itemLimit": 2,
                "includeResolved": True,
                "includeOrderBook": True,
                "depthLimit": 4,
            }
        )
    )
    assert parsed == {
        "query": "Fed rate cuts",
        "venues": ("kalshi", "polymarket"),
        "item_limit": 2,
        "include_resolved": True,
        "include_order_book": True,
        "depth_limit": 4,
    }

    strict_nullable_payload = parse_prediction_markets_lookup_arguments(
        json.dumps(
            {
                "query": "AAPL next 30 days stock price and major company events",
                "venues": ["polymarket", "kalshi"],
                "itemLimit": 10,
                "includeResolved": True,
                "includeOrderBook": False,
                "depthLimit": 5,
            }
        )
    )
    assert strict_nullable_payload == {
        "query": "AAPL next 30 days stock price and major company events",
        "venues": ("polymarket", "kalshi"),
        "item_limit": 10,
        "include_resolved": True,
        "include_order_book": False,
        "depth_limit": None,
    }

    with pytest.raises(RuntimeToolError) as invalid_venue:
        _ = parse_prediction_markets_lookup_arguments('{"query":"Fed","venues":["predictit"]}')
    assert invalid_venue.value.message == (
        "signaldeck_digital_oracle_prediction_markets_lookup venues must use: kalshi, polymarket."
    )

    with pytest.raises(RuntimeToolError) as invalid_limit:
        _ = parse_prediction_markets_lookup_arguments('{"query":"Fed","itemLimit":21}')
    assert invalid_limit.value.message == (
        "signaldeck_digital_oracle_prediction_markets_lookup itemLimit must be at most 20."
    )

    with pytest.raises(RuntimeToolError) as invalid_depth:
        _ = parse_prediction_markets_lookup_arguments(
            '{"query":"Fed","includeOrderBook":true,"depthLimit":11}'
        )
    assert invalid_depth.value.message == (
        "signaldeck_digital_oracle_prediction_markets_lookup depthLimit must be at most 10."
    )

    inactive_depth_limit = parse_prediction_markets_lookup_arguments(
        '{"query":"Fed","depthLimit":3}'
    )
    assert inactive_depth_limit["include_order_book"] is False
    assert inactive_depth_limit["depth_limit"] is None


def test_prediction_markets_providers_fetch_direct_order_book_depth() -> None:
    client = _FakePredictionMarketsJsonClient(
        {
            "gamma-api.polymarket.com/events": [
                {
                    "id": "pm-fed-event",
                    "slug": "fed-cut",
                    "title": "Fed cut odds",
                    "active": True,
                    "markets": json.dumps(
                        [
                            {
                                "id": "pm-fed-yes",
                                "question": "Will the Fed cut rates?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.61", "0.40"]),
                                "clobTokenIds": json.dumps(["pm-yes-token", "pm-no-token"]),
                            },
                        ]
                    ),
                }
            ],
            "clob.polymarket.com/book?token_id=pm-yes-token": {
                "bids": [
                    {"price": "0.60", "size": "100"},
                    {"price": "0.59", "size": "50"},
                ],
                "asks": [
                    {"price": "0.62", "size": "70"},
                    {"price": "0.63", "size": "25"},
                ],
            },
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26",
                        "event_ticker": "KXFEDCUT",
                        "title": "Fed cut odds",
                        "status": "open",
                        "yes_bid": 55,
                        "yes_ask": 57,
                    }
                ]
            },
            "markets/KXFEDCUT-26/orderbook": {
                "orderbook": {
                    "yes": [[55, 100], [54, 50]],
                    "no": [[43, 75], [42, 25]],
                }
            },
        }
    )
    query = DigitalOraclePredictionMarketsProviderQuery(
        query="Fed cut",
        venue="polymarket",
        item_limit=5,
        include_resolved=False,
        timeout_seconds=1.5,
        include_order_book=True,
        depth_limit=1,
    )

    polymarket_result = PolymarketPredictionMarketsProvider(client).lookup_prediction_markets(query)
    kalshi_result = KalshiPredictionMarketsProvider(client).lookup_prediction_markets(
        replace(query, venue="kalshi")
    )

    polymarket_payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                _FakeDigitalOraclePredictionProvider("polymarket", events=polymarket_result.events),
            ),
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Fed cut",
                venues=("polymarket",),
                include_order_book=True,
                depth_limit=1,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    polymarket_contracts = cast(
        list[dict[str, object]],
        cast(list[dict[str, object]], polymarket_payload["events"])[0]["contracts"],
    )
    kalshi_order_book = kalshi_result.events[0].contracts[0].order_book

    assert polymarket_contracts == [
        {
            "contractId": "pm-fed-yes",
            "title": "Will the Fed cut rates?",
            "probability": "0.61",
            "yesPrice": "0.61",
            "noPrice": "0.40",
            "volume": None,
            "openInterest": None,
            "orderBook": {
                "bids": [{"price": "0.60", "size": "100"}],
                "asks": [{"price": "0.62", "size": "70"}],
                "spread": "0.02",
                "depthLimit": 1,
            },
        }
    ]
    assert polymarket_result.warnings == ()
    assert kalshi_order_book is not None
    assert kalshi_order_book.spread == Decimal("0.02")
    assert [level.price for level in kalshi_order_book.bids] == [Decimal("0.55")]
    assert [level.size for level in kalshi_order_book.bids] == [Decimal("100")]
    assert [level.price for level in kalshi_order_book.asks] == [Decimal("0.57")]
    assert [level.size for level in kalshi_order_book.asks] == [Decimal("75")]
    assert [call["url"] for call in client.calls] == [
        "https://gamma-api.polymarket.com/events",
        "https://clob.polymarket.com/book?token_id=pm-yes-token",
        "https://api.elections.kalshi.com/trade-api/v2/markets",
        "https://api.elections.kalshi.com/trade-api/v2/markets/KXFEDCUT-26/orderbook",
    ]


def test_prediction_markets_providers_preserve_events_when_order_book_degrades() -> None:
    client = _FakePredictionMarketsJsonClient(
        {
            "gamma-api.polymarket.com/events": [
                {
                    "id": "pm-fed-event",
                    "slug": "fed-cut",
                    "title": "Fed cut odds",
                    "active": True,
                    "markets": json.dumps(
                        [
                            {
                                "id": "pm-fed-empty-book",
                                "question": "Will the Fed cut rates?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.61", "0.40"]),
                                "clobTokenIds": json.dumps(["empty-book-token", "no-token"]),
                                "orderBook": {
                                    "bids": [{"price": "0.60", "size": "22"}],
                                    "asks": [{"price": "0.63", "size": "18"}],
                                },
                            },
                            {
                                "id": "pm-fed-one-sided-book",
                                "question": "Will the Fed cut in March?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.41", "0.59"]),
                                "outcomeTokenIds": json.dumps(["one-sided-token", "no-token"]),
                            },
                            {
                                "id": "pm-fed-no-token-embedded-book",
                                "question": "Will the Fed cut in June?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.31", "0.69"]),
                                "orderBook": {
                                    "bids": [{"price": "0.30", "size": "15"}],
                                    "asks": [{"price": "0.32", "size": "20"}],
                                },
                            },
                        ]
                    ),
                }
            ],
            "clob.polymarket.com/book?token_id=empty-book-token": {"bids": [], "asks": []},
            "clob.polymarket.com/book?token_id=one-sided-token": {
                "bids": [{"price": "0.40", "size": "10"}],
                "asks": [],
            },
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26",
                        "event_ticker": "KXFEDCUT",
                        "title": "Fed cut odds",
                        "status": "open",
                        "yes_bid": 55,
                        "yes_ask": 57,
                    }
                ]
            },
            "markets/KXFEDCUT-26/orderbook": DigitalOracleProviderError(
                "Kalshi timed out while fetching orderbook",
                code="provider_timeout",
                details={"provider": "kalshi"},
            ),
        }
    )
    query = DigitalOraclePredictionMarketsProviderQuery(
        query="Fed cut",
        venue="polymarket",
        item_limit=5,
        include_resolved=False,
        timeout_seconds=1.5,
        include_order_book=True,
        depth_limit=2,
    )

    polymarket_result = PolymarketPredictionMarketsProvider(client).lookup_prediction_markets(query)
    kalshi_result = KalshiPredictionMarketsProvider(client).lookup_prediction_markets(
        replace(query, venue="kalshi")
    )
    payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                _FakeDigitalOraclePredictionProvider(
                    "polymarket",
                    events=polymarket_result.events,
                    warnings=polymarket_result.warnings,
                ),
                _FakeDigitalOraclePredictionProvider(
                    "kalshi",
                    events=kalshi_result.events,
                    warnings=kalshi_result.warnings,
                ),
            ),
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Fed cut",
                include_order_book=True,
                depth_limit=2,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    events = cast(list[dict[str, object]], payload["events"])
    polymarket_contracts = cast(list[dict[str, object]], events[0]["contracts"])
    kalshi_contracts = cast(list[dict[str, object]], events[1]["contracts"])
    warnings = cast(list[dict[str, object]], payload["warnings"])

    assert polymarket_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.60", "size": "22"}],
        "asks": [{"price": "0.63", "size": "18"}],
        "spread": "0.03",
        "depthLimit": 2,
    }
    assert polymarket_contracts[1]["orderBook"] == {
        "bids": [{"price": "0.40", "size": "10"}],
        "asks": [],
        "spread": None,
        "depthLimit": 2,
    }
    assert polymarket_contracts[2]["orderBook"] == {
        "bids": [{"price": "0.30", "size": "15"}],
        "asks": [{"price": "0.32", "size": "20"}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert kalshi_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.55", "size": None}],
        "asks": [{"price": "0.57", "size": None}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_order_book_malformed",
        "prediction_markets_order_book_partial",
        "prediction_markets_order_book_unavailable",
        "prediction_markets_order_book_provider_timeout",
    ]
    warning_details = [cast(dict[str, object], warning["details"]) for warning in warnings]
    assert [details["provider"] for details in warning_details] == [
        "polymarket",
        "polymarket",
        "polymarket",
        "kalshi",
    ]
    assert [details["scope"] for details in warning_details] == [
        "orderbook",
        "orderbook",
        "orderbook",
        "orderbook",
    ]


@pytest.mark.parametrize(
    ("function_name", "tool_key", "arguments_json", "expected_message"),
    [
        (
            PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
            PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
            json.dumps({"query": "   "}),
            "signaldeck_digital_oracle_prediction_markets_lookup query must not be empty.",
        ),
        (
            SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
            SEC_FILINGS_LOOKUP_TOOL_KEY,
            json.dumps(
                {
                    "ticker": "NVDA",
                    "startDate": "2026-12-31",
                    "endDate": "2026-01-01",
                }
            ),
            "signaldeck_digital_oracle_sec_filings_lookup startDate must be before or "
            + "equal to endDate.",
        ),
        (
            MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
            json.dumps({"indicator": "fear_greed", "asOfDate": "not-a-date"}),
            "signaldeck_digital_oracle_market_sentiment_lookup asOfDate must be a valid ISO date.",
        ),
    ],
)
def test_digital_oracle_invalid_runtime_arguments_fail_before_provider_clients(
    monkeypatch: pytest.MonkeyPatch,
    function_name: str,
    tool_key: str,
    arguments_json: str,
    expected_message: str,
) -> None:
    def fail_provider_factory() -> object:
        raise AssertionError("invalid Digital Oracle arguments must not construct providers")

    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        fail_provider_factory,
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        fail_provider_factory,
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        fail_provider_factory,
    )
    registry = get_default_runtime_tool_registry()

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=function_name,
            arguments_json=arguments_json,
            granted_tool_keys={tool_key},
            context=_runtime_context(fail_on_session=True),
        )

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message


def test_digital_oracle_fixture_replay_maps_success_payloads_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked_httpx_client(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("Digital Oracle fixture tests must not construct live HTTP clients")

    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.httpx.Client",
        blocked_httpx_client,
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.httpx.Client",
        blocked_httpx_client,
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.httpx.Client",
        blocked_httpx_client,
    )
    fixture_client = _DigitalOracleFixtureReplayJsonClient(
        (
            "prediction_polymarket_success.json",
            "prediction_kalshi_success.json",
            "sec_company_tickers_success.json",
            "sec_submissions_success.json",
            "market_sentiment_success.json",
        )
    )

    polymarket_result = PolymarketPredictionMarketsProvider(
        fixture_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )
    kalshi_result = KalshiPredictionMarketsProvider(fixture_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )
    sec_result = EdgarSecFilingsProvider(http_client=fixture_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    sentiment_result = FearGreedMarketSentimentProvider(
        http_client=fixture_client
    ).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )

    assert polymarket_result.events[0].contracts[0].yes_price == Decimal("0.63")
    assert kalshi_result.events[0].contracts[0].probability == Decimal("0.63")
    assert sec_result.filings[0].form_type == "10-K"
    assert sec_result.filings[0].accepted_at == datetime(2026, 2, 20, 16, 30, 1, tzinfo=UTC)
    assert sentiment_result.score == 72
    assert sentiment_result.label == "greed"
    assert len(fixture_client.calls) == 5


def test_digital_oracle_fixture_replay_malformed_empty_and_error_payloads() -> None:
    fixture_client = _DigitalOracleFixtureReplayJsonClient(
        (
            "prediction_polymarket_malformed.json",
            "prediction_kalshi_empty.json",
            "sec_company_tickers_success.json",
            "sec_submissions_malformed.json",
        )
    )
    empty_sentiment_client = _DigitalOracleFixtureReplayJsonClient(("market_sentiment_empty.json",))
    malformed_sentiment_client = _DigitalOracleFixtureReplayJsonClient(
        ("market_sentiment_malformed.json",)
    )
    prediction_service = DigitalOraclePhase1Service(
        prediction_market_providers=(
            PolymarketPredictionMarketsProvider(fixture_client),
            KalshiPredictionMarketsProvider(fixture_client),
        ),
    )
    prediction_payload = map_prediction_markets_result(
        prediction_service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Malformed",
                venues=("polymarket", "kalshi"),
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)

    sec_result = EdgarSecFilingsProvider(http_client=fixture_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="MALF",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    empty_sentiment_result = FearGreedMarketSentimentProvider(
        http_client=empty_sentiment_client
    ).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    malformed_sentiment_payload = map_market_sentiment_result(
        DigitalOraclePhase1Service(
            market_sentiment_provider=FearGreedMarketSentimentProvider(
                http_client=malformed_sentiment_client
            ),
        ).lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)

    assert prediction_payload["events"] == []
    assert [
        warning["code"] for warning in cast(list[dict[str, object]], prediction_payload["warnings"])
    ] == [
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_empty",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert sec_result.filings == ()
    assert [warning.code for warning in sec_result.warnings] == ["sec_filings_malformed_payload"]
    assert empty_sentiment_result.score is None
    assert [warning.code for warning in empty_sentiment_result.warnings] == [
        "market_sentiment_sparse_history"
    ]
    assert malformed_sentiment_payload["warnings"] == [
        {
            "code": "market_sentiment_provider_error",
            "message": "Fear & Greed provider returned malformed market sentiment data",
            "details": {"operation": "market_sentiment", "provider": "fear_greed"},
        }
    ]


def test_digital_oracle_fixture_replay_provider_errors_degrade_without_network() -> None:
    prediction_client = _DigitalOracleFixtureReplayJsonClient(
        ("prediction_polymarket_timeout.json", "prediction_kalshi_empty.json")
    )
    prediction_payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                PolymarketPredictionMarketsProvider(prediction_client),
                KalshiPredictionMarketsProvider(prediction_client),
            ),
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Timeout",
                venues=("polymarket", "kalshi"),
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    sec_client = _DigitalOracleFixtureReplayJsonClient(("sec_company_tickers_timeout.json",))
    sentiment_client = _DigitalOracleFixtureReplayJsonClient(("market_sentiment_unavailable.json",))
    sec_payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="sec-contact@example.test"
                )
            ),
            sec_filings_provider=EdgarSecFilingsProvider(http_client=sec_client),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sentiment_payload = map_market_sentiment_result(
        DigitalOraclePhase1Service(
            market_sentiment_provider=FearGreedMarketSentimentProvider(
                http_client=sentiment_client
            ),
        ).lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)

    assert [
        warning["code"] for warning in cast(list[dict[str, object]], prediction_payload["warnings"])
    ] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert [
        warning["code"] for warning in cast(list[dict[str, object]], sec_payload["warnings"])
    ] == [
        "sec_filings_provider_timeout",
        "sec_filings_unavailable",
    ]
    assert sentiment_payload["warnings"] == [
        {
            "code": "market_sentiment_provider_unavailable",
            "message": "Fear & Greed fixture is unavailable for market sentiment",
            "details": {"operation": "market_sentiment", "provider": "fear_greed"},
        }
    ]


def test_edgar_sec_filings_search_maps_hits_and_preserves_submissions_fallback() -> None:
    company_payload = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
    submissions_payload = {
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-26-000010"],
                "form": ["10-K"],
                "filingDate": ["2026-02-20"],
                "acceptanceDateTime": ["20260220163001"],
                "primaryDocument": ["nvda-20260131.htm"],
                "primaryDocDescription": ["Annual report"],
            }
        },
    }
    search_payload = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "adsh": "0001045810-26-000010",
                        "form": "10-K",
                        "filedAt": "2026-02-20",
                        "ciks": ["0001045810"],
                        "tickers": ["NVDA"],
                        "companyName": "NVIDIA CORP",
                        "linkToFilingDetails": (
                            "https://www.sec.gov/Archives/edgar/data/1045810/"
                            "000104581026000010/nvda-20260131.htm"
                        ),
                        "fileName": "nvda-20260131.htm",
                        "description": "Annual report mentions accelerated computing.",
                    }
                }
            ]
        }
    }
    client = _FakeEdgarJsonClient(
        {
            "company_tickers.json": company_payload,
            "submissions/CIK0001045810.json": submissions_payload,
            "search-index": search_payload,
        }
    )

    provider_result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query="accelerated computing",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
        )
    )
    payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=_FakeDigitalOracleSecFilingsProvider(
                filings=provider_result.filings,
                search_hits=provider_result.search_hits,
            ),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA", query="accelerated"))
    ).model_dump(mode="json", by_alias=True)

    search_hits = cast(list[dict[str, object]], payload["searchHits"])
    assert provider_result.cik == "0001045810"
    assert provider_result.filings[0].form_type == "10-K"
    assert search_hits == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "cik": "0001045810",
            "ticker": "NVDA",
            "entityName": "NVIDIA CORP",
            "primaryDocument": "nvda-20260131.htm",
            "url": (
                "https://www.sec.gov/Archives/edgar/data/1045810/"
                "000104581026000010/nvda-20260131.htm"
            ),
            "description": "Annual report mentions accelerated computing.",
            "matchedText": "Annual report mentions accelerated computing.",
        }
    ]
    assert "test@example" not in json.dumps(payload)


def test_edgar_sec_filings_cik_lookup_empty_search_warns_and_falls_back_to_metadata() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000011"],
                        "form": ["8-K"],
                        "filingDate": ["2026-03-01"],
                        "primaryDocument": ["nvda-8k.htm"],
                        "primaryDocDescription": ["Current report for AI data center demand"],
                    }
                },
            },
            "search-index": {"hits": {"hits": []}},
        }
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker=None,
            cik="0001045810",
            query="data center",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
        )
    )
    service_payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=_FakeDigitalOracleSecFilingsProvider(
                filings=result.filings,
                search_hits=result.search_hits,
            ),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(cik="1045810", query="data center"))
    ).model_dump(mode="json", by_alias=True)

    assert result.ticker == "NVDA"
    assert [warning.code for warning in result.warnings] == ["sec_filings_search_empty"]
    search_hits = cast(list[dict[str, object]], service_payload["searchHits"])
    assert search_hits[0]["matchedText"] == "Current report for AI data center demand"
    assert "test@example" not in json.dumps(service_payload)


def test_edgar_sec_filings_ownership_transactions_are_bounded_and_malformed_xml_warns() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": [
                            "0001045810-26-000020",
                            "0001045810-26-000021",
                        ],
                        "form": ["4", "4/A"],
                        "filingDate": ["2026-02-22", "2026-02-21"],
                        "primaryDocument": ["form4.xml", "broken.xml"],
                        "primaryDocDescription": ["Statement of ownership", "Broken ownership"],
                    }
                },
            },
        },
        text_by_url_fragment={
            "form4.xml": (
                "<ownershipDocument>"
                "<issuer><issuerName>NVIDIA CORP</issuerName>"
                "<issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>"
                "<reportingOwner><reportingOwnerId>"
                "<rptOwnerName>Ada Lovelace</rptOwnerName>"
                "</reportingOwnerId></reportingOwner>"
                "<nonDerivativeTable>"
                "<nonDerivativeTransaction>"
                "<transactionDate><value>2026-02-20</value></transactionDate>"
                "<transactionCoding><transactionCode>P</transactionCode></transactionCoding>"
                "<transactionAmounts>"
                "<transactionShares><value>10</value></transactionShares>"
                "<transactionPricePerShare><value>120.25</value></transactionPricePerShare>"
                "<transactionAcquiredDisposedCode><value>A</value>"
                "</transactionAcquiredDisposedCode>"
                "</transactionAmounts>"
                "</nonDerivativeTransaction>"
                "<nonDerivativeTransaction>"
                "<transactionDate><value>2026-02-21</value></transactionDate>"
                "<transactionCoding><transactionCode>S</transactionCode></transactionCoding>"
                "</nonDerivativeTransaction>"
                "</nonDerivativeTable>"
                "</ownershipDocument>"
            ),
            "broken.xml": "<ownershipDocument>",
        },
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query=None,
            form_types=("4", "4/A"),
            start_date=None,
            end_date=None,
            item_limit=1,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    malformed_result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query=None,
            form_types=("4", "4/A"),
            start_date=None,
            end_date=None,
            item_limit=3,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    payload = map_sec_filings_result(
        DigitalOracleSecFilingsResult(
            ticker=result.ticker,
            cik=result.cik,
            entity_name=result.entity_name,
            filings=result.filings,
            ownership_transactions=result.ownership_transactions,
            warnings=result.warnings,
        )
    ).model_dump(mode="json", by_alias=True)

    ownership = cast(list[dict[str, object]], payload["ownershipTransactions"])
    assert len(result.ownership_transactions) == 1
    assert ownership[0]["transactionCode"] == "P"
    assert ownership[0]["shares"] == "10"
    assert "sec_filings_malformed_payload" in [
        warning.code for warning in malformed_result.warnings
    ]
    assert "test@example" not in json.dumps(payload)


def test_edgar_sec_filings_search_timeout_and_malformed_ownership_degrade_safely() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000020"],
                        "form": ["4"],
                        "filingDate": ["2026-02-22"],
                        "primaryDocument": ["broken.xml"],
                        "primaryDocDescription": ["Ownership statement"],
                    }
                },
            },
            "search-index": DigitalOracleProviderError(
                "SEC EDGAR timed out while searching filings",
                code="provider_timeout",
                details={"provider": "edgar"},
            ),
        },
        text_by_url_fragment={"broken.xml": "<ownershipDocument>"},
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query="ownership",
            form_types=("4",),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=_FakeDigitalOracleSecFilingsProvider(
                filings=result.filings,
                search_hits=result.search_hits,
                ownership_transactions=result.ownership_transactions,
            ),
        ).lookup_sec_filings(
            DigitalOracleSecFilingsQuery(
                ticker="NVDA",
                query="ownership",
                form_types=("4",),
                include_ownership_transactions=True,
            )
        )
    ).model_dump(mode="json", by_alias=True)

    warning_codes = [warning.code for warning in result.warnings]
    assert "sec_filings_search_unavailable" in warning_codes
    assert "sec_filings_malformed_payload" in warning_codes
    assert payload["ownershipTransactions"] == []
    assert "test@example" not in json.dumps(payload)


def test_digital_oracle_fixture_replay_missing_or_malformed_fixture_fails_deterministically(
    tmp_path: Path,
) -> None:
    with pytest.raises(AssertionError, match="Missing Digital Oracle fixture file"):
        _ = _DigitalOracleFixtureReplayJsonClient(("missing.json",))

    fixture_client = _DigitalOracleFixtureReplayJsonClient(("prediction_kalshi_empty.json",))
    with pytest.raises(AssertionError, match="Missing Digital Oracle fixture"):
        _ = PolymarketPredictionMarketsProvider(fixture_client).lookup_prediction_markets(
            DigitalOraclePredictionMarketsProviderQuery(
                query="Fed cut",
                venue="polymarket",
                item_limit=5,
                include_resolved=False,
                timeout_seconds=1.5,
            )
        )

    malformed_fixture = tmp_path / "malformed.json"
    _ = malformed_fixture.write_text(
        json.dumps({"kind": "json", "request": {"url": "https://example.test", "params": {}}})
    )
    with pytest.raises(AssertionError, match="exactly one response or error"):
        _ = _DigitalOracleFixtureReplayJsonClient(
            ("malformed.json",),
            fixture_dir=tmp_path,
        )


def test_prediction_markets_runtime_providers_normalize_venue_payloads() -> None:
    polymarket_client = _FakePredictionMarketsJsonClient(
        {
            "gamma-api.polymarket.com": [
                {
                    "id": "pm-fed-cut",
                    "slug": "fed-cut-before-june-2026",
                    "title": "Will the Fed cut rates before June 2026?",
                    "active": True,
                    "closed": False,
                    "endDate": "2026-06-01T00:00:00Z",
                    "openInterest": "2500",
                    "markets": [
                        {
                            "id": "pm-fed-cut-market",
                            "question": "Will the Fed cut rates before June 2026?",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.63", "0.37"]',
                            "volumeNum": "125000.5",
                        }
                    ],
                }
            ]
        }
    )
    polymarket_result = PolymarketPredictionMarketsProvider(
        polymarket_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )

    assert polymarket_client.calls[0]["timeout"] == 1.5
    assert cast(dict[str, object], polymarket_client.calls[0]["params"])["limit"] == 5
    polymarket_event = polymarket_result.events[0]
    assert polymarket_event.venue == "polymarket"
    assert polymarket_event.event_id == "pm-fed-cut"
    assert polymarket_event.status == "open"
    assert polymarket_event.end_date == datetime(2026, 6, 1, tzinfo=UTC)
    assert polymarket_event.contracts[0].yes_price == Decimal("0.63")
    assert polymarket_event.contracts[0].no_price == Decimal("0.37")
    assert polymarket_event.contracts[0].volume == Decimal("125000.5")
    assert polymarket_event.contracts[0].open_interest == Decimal("2500")
    assert polymarket_result.warnings == ()

    kalshi_client = _FakePredictionMarketsJsonClient(
        {
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26JUN-T50",
                        "event_ticker": "KXFEDCUT-26JUN",
                        "title": "Fed cut before June 2026",
                        "status": "open",
                        "yes_sub_title": "Yes",
                        "yes_bid": 62,
                        "yes_ask": 64,
                        "no_ask": 38,
                        "last_price": 63,
                        "volume": "9000",
                        "open_interest": 1200,
                        "close_time": "2026-06-01T12:00:00Z",
                    }
                ]
            }
        }
    )
    kalshi_result = KalshiPredictionMarketsProvider(kalshi_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=2.0,
        )
    )

    assert kalshi_client.calls[0]["provider"] == "kalshi"
    kalshi_event = kalshi_result.events[0]
    assert kalshi_event.venue == "kalshi"
    assert kalshi_event.event_id == "KXFEDCUT-26JUN"
    assert kalshi_event.url == "https://kalshi.com/markets/KXFEDCUT-26JUN-T50"
    assert kalshi_event.contracts[0].probability == Decimal("0.63")
    assert kalshi_event.contracts[0].yes_price == Decimal("0.64")
    assert kalshi_event.contracts[0].no_price == Decimal("0.38")
    assert kalshi_event.contracts[0].open_interest == Decimal("1200")
    assert kalshi_result.warnings == ()


def test_prediction_markets_runtime_providers_accept_upstream_shaped_payloads() -> None:
    polymarket_client = _FakePredictionMarketsJsonClient(
        {
            "gamma-api.polymarket.com": [
                {
                    "slug": "resolved-fed-cut",
                    "title": "Resolved market",
                    "active": False,
                    "closed": True,
                    "tag_slug": "fed-cut",
                    "markets": json.dumps(
                        [
                            {
                                "question": "Resolved Fed cut market",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.10", "0.90"]),
                                "clobTokenIds": json.dumps(["resolved-yes-token"]),
                            }
                        ]
                    ),
                },
                {
                    "slug": "live-fed-cut",
                    "title": "Live market",
                    "active": True,
                    "closed": False,
                    "tagSlug": "fed-cut",
                    "markets": json.dumps(
                        [
                            {
                                "question": "Live Fed cut market",
                                "outcomes": ["Yes", "No"],
                                "outcomePrices": ["0.61", "0.39"],
                                "outcomeTokenIds": ["live-yes-token"],
                                "volume_24hr": "4567.89",
                            }
                        ]
                    ),
                },
            ]
        }
    )
    polymarket_result = PolymarketPredictionMarketsProvider(
        polymarket_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=True,
            timeout_seconds=1.5,
        )
    )

    assert [event.status for event in polymarket_result.events] == ["open", "closed"]
    live_contract = polymarket_result.events[0].contracts[0]
    assert live_contract.contract_id == "live-yes-token"
    assert live_contract.volume == Decimal("4567.89")
    assert polymarket_result.events[0].url == "https://polymarket.com/event/live-fed-cut"
    assert polymarket_result.warnings == ()

    kalshi_client = _FakePredictionMarketsJsonClient(
        {
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26JUN-T50",
                        "eventTicker": "KXFEDCUT-26JUN",
                        "event_title": "Fed cut before June 2026",
                        "status": "open",
                        "subtitle": "Yes",
                        "yes_bid_dollars": "0.40",
                        "yes_ask_dollars": "0.60",
                        "no_ask_fp": "0.50",
                        "last_price_fp": "0.90",
                        "yes_bid": 1,
                        "yes_ask": 2,
                        "no_ask": 3,
                        "last_price": 4,
                        "openInterest": "345",
                        "closeDate": "2026-06-01T12:00:00Z",
                    }
                ]
            }
        }
    )
    kalshi_result = KalshiPredictionMarketsProvider(kalshi_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=2.0,
        )
    )

    assert cast(dict[str, object], kalshi_client.calls[0]["params"])["mve_filter"] == "exclude"
    kalshi_event = kalshi_result.events[0]
    assert kalshi_event.event_id == "KXFEDCUT-26JUN"
    assert kalshi_event.title == "Fed cut before June 2026"
    assert kalshi_event.end_date == datetime(2026, 6, 1, 12, tzinfo=UTC)
    assert kalshi_event.contracts[0].title == "Yes"
    assert kalshi_event.contracts[0].probability == Decimal("0.5")
    assert kalshi_event.contracts[0].yes_price == Decimal("0.6")
    assert kalshi_event.contracts[0].no_price == Decimal("0.50")
    assert kalshi_event.contracts[0].open_interest == Decimal("345")


def test_prediction_markets_runtime_executor_filters_venues_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-ignored",
                title="Ignored Polymarket event",
                status="open",
            ),
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUN",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXFEDCUT-26JUN-T50",
                        title="Yes",
                        probability=Decimal("0.63"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                    ),
                ),
            ),
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUL",
                title="Fed cut before July 2026",
                status="open",
            ),
        ),
    )

    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        _runtime_context(fail_on_session=True),
        parse_prediction_markets_lookup_arguments(
            json.dumps(
                {
                    "query": " Fed   cut ",
                    "venues": ["kalshi"],
                    "itemLimit": 1,
                    "includeResolved": True,
                }
            )
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert polymarket_provider.calls == []
    assert kalshi_provider.calls[0].query == "Fed cut"
    assert kalshi_provider.calls[0].item_limit == 1
    assert kalshi_provider.calls[0].include_resolved is True
    assert payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert payload["query"] == "Fed cut"
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["kalshi"]
    assert events[0]["eventId"] == "KXFEDCUT-26JUN"
    contracts = cast(list[dict[str, object]], events[0]["contracts"])
    assert contracts[0]["yesPrice"] == "0.64"
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "prediction_markets_truncated",
            "message": "prediction_markets results were truncated to 1 items.",
            "details": {"operation": "prediction_markets", "limit": "1"},
        }
    ]


def test_prediction_markets_runtime_executor_preserves_partial_provider_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-fed-cut",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-fed-cut-market",
                        title="Will the Fed cut rates before June 2026?",
                        probability=Decimal("0.63"),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi provider timed out with token=sk-runtime-secret",
            code="provider_timeout",
            details={"venue": "kalshi", "token": "sk-runtime-secret"},
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        _runtime_context(fail_on_session=True),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "Fed cut", "venues": ["polymarket", "kalshi"]})
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["polymarket"]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_partial_result",
    ]
    assert warnings[0]["message"] == "Kalshi provider timed out with token=<redacted>"
    assert warnings[0]["details"] == {
        "operation": "prediction_markets",
        "provider": "kalshi",
        "venue": "kalshi",
    }


def test_prediction_markets_runtime_executor_returns_unavailable_when_all_providers_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider("polymarket")
    kalshi_provider = _FakeDigitalOraclePredictionProvider("kalshi")
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )

    payload = execute_prediction_markets_lookup(
        _runtime_context(fail_on_session=True),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "No matching event", "venues": ["polymarket", "kalshi"]})
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["events"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "prediction_markets_empty",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert payload["warnings"] == [
        {
            "code": "prediction_markets_empty",
            "message": "No prediction_markets data returned from polymarket.",
            "details": {"operation": "prediction_markets", "provider": "polymarket"},
        },
        {
            "code": "prediction_markets_empty",
            "message": "No prediction_markets data returned from kalshi.",
            "details": {"operation": "prediction_markets", "provider": "kalshi"},
        },
        {
            "code": "prediction_markets_unavailable",
            "message": "No prediction_markets data available from configured providers.",
            "details": {"operation": "prediction_markets"},
        },
    ]


def test_prediction_markets_runtime_executor_returns_unavailable_when_all_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = _FakeDigitalOraclePredictionProvider(
        "polymarket",
        failure=DigitalOracleProviderError(
            "Polymarket timed out while fetching prediction markets",
            code="provider_timeout",
            details={"provider": "polymarket"},
        ),
    )
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi is unavailable for prediction markets",
            code="provider_unavailable",
            details={"provider": "kalshi"},
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )

    payload = execute_prediction_markets_lookup(
        _runtime_context(fail_on_session=True),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "Fed cut", "venues": ["polymarket", "kalshi"]})
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert payload["query"] == "Fed cut"
    assert payload["events"] == []
    assert payload["warnings"] == [
        {
            "code": "prediction_markets_provider_timeout",
            "message": "Polymarket timed out while fetching prediction markets",
            "details": {"operation": "prediction_markets", "provider": "polymarket"},
        },
        {
            "code": "prediction_markets_provider_unavailable",
            "message": "Kalshi is unavailable for prediction markets",
            "details": {"operation": "prediction_markets", "provider": "kalshi"},
        },
        {
            "code": "prediction_markets_unavailable",
            "message": "No prediction_markets data available from configured providers.",
            "details": {"operation": "prediction_markets"},
        },
    ]


def test_prediction_markets_service_preserves_malformed_adapter_warnings_with_partial_result() -> (
    None
):
    polymarket_client = _FakePredictionMarketsJsonClient(
        {
            "gamma-api.polymarket.com": [
                "not-an-event-row",
                {
                    "id": "pm-fed-cut",
                    "slug": "fed-cut-before-june-2026",
                    "title": "Will the Fed cut rates before June 2026?",
                    "active": True,
                    "closed": False,
                    "markets": [
                        {
                            "id": "pm-fed-cut-market",
                            "question": "Will the Fed cut rates before June 2026?",
                            "outcomes": "not-json",
                            "outcomePrices": '["0.63", "0.37"]',
                        }
                    ],
                },
            ]
        }
    )
    polymarket_provider = PolymarketPredictionMarketsProvider(polymarket_client)
    kalshi_provider = _FakeDigitalOraclePredictionProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUN",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXFEDCUT-26JUN-T50",
                        title="Yes",
                        probability=Decimal("0.63"),
                    ),
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        prediction_market_providers=(polymarket_provider, kalshi_provider),
    )

    payload = map_prediction_markets_result(
        service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Fed cut",
                venues=("polymarket", "kalshi"),
            )
        )
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["kalshi"]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_empty",
        "prediction_markets_partial_result",
    ]
    assert warnings[1]["details"] == {
        "operation": "prediction_markets",
        "provider": "polymarket",
        "field": "market outcomes",
        "eventId": "pm-fed-cut",
    }
    assert warnings[-1]["details"] == {
        "operation": "prediction_markets",
        "providers": "polymarket,kalshi",
        "uncoveredProviders": "polymarket",
    }


def test_crypto_derivatives_tool_spec_uses_native_parameters_schema() -> None:
    assert (
        CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME
        == "signaldeck_digital_oracle_crypto_derivatives_lookup"
    )
    assert CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC.key == CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
    assert CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC.parser is parse_crypto_derivatives_lookup_arguments
    assert CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC.executor is execute_crypto_derivatives_lookup

    schema = CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == []
    assert set(properties) == {
        "assets",
        "venues",
        "dataTypes",
        "expirations",
        "includeOrderBook",
        "depthLimit",
        "itemLimit",
    }
    data_types = cast(dict[str, object], properties["dataTypes"])
    data_type_items = cast(dict[str, object], data_types["items"])
    assert data_type_items["enum"] == [
        "spot",
        "global_market",
        "term_structure",
        "option_chain",
        "order_book",
    ]
    assert cast(dict[str, object], properties["depthLimit"])["maximum"] == 10
    assert cast(dict[str, object], properties["itemLimit"])["maximum"] == 50


def test_crypto_derivatives_parser_normalizes_arrays_and_rejects_invalid_inputs() -> None:
    arguments = parse_crypto_derivatives_lookup_arguments(
        json.dumps(
            {
                "assets": [" btc ", "BTC", " eth "],
                "venues": ["DERIBIT", "coingecko", "deribit"],
                "dataTypes": ["spot", "option_chain", "order_book", "spot"],
                "expirations": ["2026-06-26", "2026-09-25"],
                "includeOrderBook": True,
                "depthLimit": 3,
                "itemLimit": 4,
            }
        )
    )

    assert arguments == {
        "assets": ("BTC", "ETH"),
        "venues": ("deribit", "coingecko"),
        "data_types": ("spot", "option_chain", "order_book"),
        "expirations": (date(2026, 6, 26), date(2026, 9, 25)),
        "include_order_book": True,
        "depth_limit": 3,
        "item_limit": 4,
    }
    assert (
        parse_crypto_derivatives_lookup_arguments(json.dumps({"depthLimit": 3}))["depth_limit"]
        is None
    )

    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"asset": "BTC"}))
    with pytest.raises(RuntimeToolError, match="venues must use"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"venues": ["finance"]}))
    with pytest.raises(RuntimeToolError, match="dataTypes must use"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"dataTypes": ["funding"]}))
    with pytest.raises(RuntimeToolError, match="dataTypes must use"):
        _ = parse_crypto_derivatives_lookup_arguments(
            json.dumps({"dataTypes": ["global_metrics", "options"]})
        )
    with pytest.raises(RuntimeToolError, match="depthLimit must be at most 10"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"depthLimit": 11}))
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"itemLimit": 51}))


def test_cftc_positioning_runtime_tool_spec_uses_approved_parameters_schema() -> None:
    assert (
        CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME
        == "signaldeck_digital_oracle_cftc_positioning_lookup"
    )
    assert CFTC_POSITIONING_LOOKUP_TOOL_SPEC.key == CFTC_POSITIONING_LOOKUP_TOOL_KEY
    assert CFTC_POSITIONING_LOOKUP_TOOL_SPEC.parser is parse_cftc_positioning_lookup_arguments
    assert CFTC_POSITIONING_LOOKUP_TOOL_SPEC.executor is execute_cftc_positioning_lookup
    assert CFTC_POSITIONING_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY

    schema = CFTC_POSITIONING_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == []
    assert set(properties) == {"markets", "reportTypes", "startDate", "endDate", "itemLimit"}
    assert cast(dict[str, object], properties["markets"])["maxItems"] == 10
    assert cast(dict[str, object], properties["itemLimit"])["maximum"] == 50


def test_cftc_positioning_parser_normalizes_filters_and_rejects_invalid_args() -> None:
    arguments = parse_cftc_positioning_lookup_arguments(
        json.dumps(
            {
                "markets": [" Bitcoin ", "BITCOIN", "Gold"],
                "reportTypes": [" legacy_futures_only ", "financial_futures"],
                "startDate": "2026-01-01",
                "endDate": "2026-06-30",
                "itemLimit": 5,
            }
        )
    )

    assert arguments == {
        "markets": ("Bitcoin", "Gold"),
        "report_types": ("legacy_futures_only", "financial_futures"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 6, 30),
        "item_limit": 5,
    }
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_cftc_positioning_lookup_arguments(json.dumps({"market": "Bitcoin"}))
    with pytest.raises(RuntimeToolError, match="reportTypes must use"):
        _ = parse_cftc_positioning_lookup_arguments(json.dumps({"reportTypes": ["legacy"]}))
    with pytest.raises(RuntimeToolError, match="markets must contain at most 10"):
        _ = parse_cftc_positioning_lookup_arguments(
            json.dumps({"markets": [f"M{index}" for index in range(11)]})
        )
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_cftc_positioning_lookup_arguments(
            json.dumps({"startDate": "2026-06-30", "endDate": "2026-01-01"})
        )


def test_cftc_positioning_provider_maps_fake_rows_and_malformed_warning() -> None:
    client = _FakeCftcPositioningJsonClient(
        {
            "6dca-aqww": [
                {
                    "market_and_exchange_names": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
                    "cftc_contract_market_code": "133741",
                    "report_date_as_yyyy_mm_dd": "2026-06-16T00:00:00",
                    "noncomm_positions_long_all": "1200",
                    "noncomm_positions_short_all": "900",
                    "noncomm_positions_spread_all": "45",
                    "open_interest_all": "18300",
                },
                {"market_and_exchange_names": "malformed"},
            ]
        }
    )
    provider = CftcCotPositioningProvider(client)

    result = provider.lookup_cftc_positioning(
        DigitalOracleCftcPositioningProviderQuery(
            markets=("Bitcoin",),
            report_types=("legacy_futures_only",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            item_limit=5,
            timeout_seconds=2.5,
        )
    )

    assert cast(dict[str, object], client.calls[0]["params"])["$limit"] == 5
    assert result.reports[0].report_date == date(2026, 6, 16)
    assert result.reports[0].rows[0].non_commercial_net == Decimal("300")
    assert [warning.code for warning in result.warnings] == ["cftc_positioning_malformed_payload"]


def test_cftc_positioning_service_filters_dates_report_types_and_markets() -> None:
    provider = _FakeDigitalOracleCftcPositioningProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="BITCOIN - CME",
                            contract_market_code="133741",
                            producer_long=Decimal("1200"),
                            producer_short=Decimal("900"),
                            producer_net=Decimal("300"),
                            open_interest=Decimal("18300"),
                        ),
                    ),
                ),
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="financial_futures",
                    report_date=date(2025, 12, 30),
                    rows=(DigitalOracleCftcPositioningRow(market="GOLD"),),
                ),
            ),
        )
    )
    service = DigitalOraclePhase1Service(cftc_positioning_providers=(provider,))

    payload = map_cftc_positioning_result(
        service.lookup_cftc_positioning(
            DigitalOracleCftcPositioningQuery(
                markets=("bitcoin",),
                report_types=("legacy_futures_only",),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].markets == ("bitcoin",)
    assert provider.calls[0].report_types == ("legacy_futures_only",)
    reports = cast(list[dict[str, object]], payload["reports"])
    assert reports[0]["reportDate"] == "2026-06-16"
    row = cast(list[dict[str, object]], reports[0]["rows"])[0]
    assert row["producerNet"] == "300"
    assert row["openInterest"] == "18300"
    assert payload["warnings"] == []


def test_cftc_positioning_missing_market_and_provider_failure_return_warnings() -> None:
    empty_provider = _FakeDigitalOracleCftcPositioningProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(DigitalOracleCftcPositioningRow(market="GOLD"),),
                ),
            ),
        )
    )
    failed_provider = _FakeDigitalOracleCftcPositioningProvider(
        failure=DigitalOracleProviderError(
            "CFTC timed out with provider token sk-provider-secret",
            code="provider_timeout",
            details={"provider": "cftc", "api_key": "sk-provider-secret"},
        )
    )

    empty_payload = map_cftc_positioning_result(
        DigitalOraclePhase1Service(
            cftc_positioning_providers=(empty_provider,)
        ).lookup_cftc_positioning(DigitalOracleCftcPositioningQuery(markets=("Bitcoin",)))
    ).model_dump(mode="json", by_alias=True)
    failure_payload = map_cftc_positioning_result(
        DigitalOraclePhase1Service(
            cftc_positioning_providers=(failed_provider,)
        ).lookup_cftc_positioning(DigitalOracleCftcPositioningQuery(markets=("Bitcoin",)))
    ).model_dump(mode="json", by_alias=True)

    assert empty_payload["reports"] == []
    empty_warnings = cast(list[dict[str, object]], empty_payload["warnings"])
    assert [warning["code"] for warning in empty_warnings] == [
        "cftc_positioning_empty",
        "cftc_positioning_unavailable",
    ]
    failure_warnings = cast(list[dict[str, object]], failure_payload["warnings"])
    assert [warning["code"] for warning in failure_warnings] == [
        "cftc_positioning_provider_timeout",
        "cftc_positioning_unavailable",
    ]
    assert "sk-provider-secret" not in json.dumps(failure_payload)
    assert "api_key" not in json.dumps(failure_payload)


def test_cftc_positioning_runtime_registry_dispatch_and_disabled_extension_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleCftcPositioningProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="BITCOIN - CME",
                            managed_money_long=Decimal("7200"),
                            managed_money_short=Decimal("6800"),
                            managed_money_net=Decimal("400"),
                        ),
                    ),
                ),
            ),
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_cftc_positioning.create_cftc_positioning_providers",
        lambda: (provider,),
    )
    registry = RuntimeToolRegistry([CFTC_POSITIONING_LOOKUP_TOOL_SPEC])
    payload = registry.dispatch(
        name=CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {"markets": ["Bitcoin"], "reportTypes": ["legacy_futures_only"], "itemLimit": 1}
        ),
        granted_tool_keys={CFTC_POSITIONING_LOOKUP_TOOL_KEY},
        context=_runtime_context(fail_on_session=True),
    )

    assert provider.calls[0].item_limit == 1
    assert payload["toolKey"] == CFTC_POSITIONING_LOOKUP_TOOL_KEY
    reports = cast(list[dict[str, object]], payload["reports"])
    row = cast(list[dict[str, object]], reports[0]["rows"])[0]
    assert row["managedMoneyNet"] == "400"
    with pytest.raises(RuntimeToolError) as denied_error:
        _ = registry.dispatch(
            name=CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=_runtime_context(fail_on_session=True),
        )
    assert denied_error.value.code == "agent_execution_access_denied"
    assert (
        denied_error.value.message
        == DIGITAL_ORACLE_DENIED_MESSAGES[CFTC_POSITIONING_LOOKUP_TOOL_KEY]
    )


def test_crypto_derivatives_service_maps_fake_provider_results_to_camel_payload() -> None:
    coingecko_provider = _FakeDigitalOracleCryptoDerivativesProvider(
        "coingecko",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="coingecko",
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="coingecko",
                    symbol="BTC",
                    price=Decimal("65000.5"),
                    currency="USD",
                    as_of=_NOW,
                ),
            ),
            global_metrics=(
                DigitalOracleCryptoDerivativesGlobalMetrics(
                    provider="coingecko",
                    symbol=None,
                    market_cap=Decimal("2500000000000"),
                    volume_24h=Decimal("80000000000"),
                    as_of=_NOW,
                ),
            ),
        ),
    )
    deribit_provider = _FakeDigitalOracleCryptoDerivativesProvider(
        "deribit",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="deribit",
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    instrument="BTC-26JUN26",
                    implied_volatility=Decimal("0.55"),
                    open_interest=Decimal("1200"),
                ),
            ),
            options=(
                DigitalOracleCryptoDerivativesOptionSummary(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    strike=Decimal("70000"),
                    option_type="call",
                    implied_volatility=Decimal("0.61"),
                    open_interest=Decimal("35"),
                ),
            ),
            order_books=(
                DigitalOracleCryptoDerivativesOrderBook(
                    provider="deribit",
                    symbol="BTC",
                    instrument="BTC-26JUN26",
                    bids=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64990"),
                            size=Decimal("2.5"),
                        ),
                    ),
                    asks=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("65010"),
                            size=Decimal("1.75"),
                        ),
                    ),
                    depth_limit=2,
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        settings=DigitalOracleSettings.model_validate({"DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5"}),
        crypto_derivatives_providers=(deribit_provider, coingecko_provider),
    )

    payload = map_crypto_derivatives_result(
        service.lookup_crypto_derivatives(
            DigitalOracleCryptoDerivativesQuery(
                assets=(" btc ", "BTC"),
                venues=("coingecko", "deribit"),
                data_types=(
                    "spot",
                    "global_market",
                    "term_structure",
                    "option_chain",
                    "order_book",
                ),
                include_order_book=True,
                depth_limit=2,
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert coingecko_provider.calls[0].assets == ("BTC",)
    assert deribit_provider.calls[0].depth_limit == 2
    assert payload["toolKey"] == CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
    assert payload["assets"] == ["BTC"]
    assert cast(list[dict[str, object]], payload["spot"])[0]["price"] == "65000.5"
    assert cast(list[dict[str, object]], payload["globalMetrics"])[0]["marketCap"] == (
        "2500000000000"
    )
    assert cast(list[dict[str, object]], payload["termStructure"])[0]["instrument"] == (
        "BTC-26JUN26"
    )
    assert cast(list[dict[str, object]], payload["options"])[0]["optionType"] == "call"
    assert cast(list[dict[str, object]], payload["orderBooks"])[0]["bids"] == [
        {"price": "64990", "size": "2.5"}
    ]
    assert payload["warnings"] == []


def test_crypto_derivatives_providers_normalize_coingecko_and_deribit_payloads() -> None:
    coingecko_client = _FakeCryptoDerivativesJsonClient(
        {
            "simple/price": {
                "bitcoin": {
                    "usd": 65000.5,
                    "usd_market_cap": 1280000000000,
                    "usd_24h_vol": 32000000000,
                    "last_updated_at": 1767225600,
                }
            },
            "/global": {
                "data": {
                    "total_market_cap": {"usd": "2500000000000"},
                    "total_volume": {"usd": "80000000000"},
                    "updated_at": 1767225600,
                }
            },
        }
    )
    coingecko_result = CoinGeckoCryptoDerivativesProvider(
        coingecko_client
    ).lookup_crypto_derivatives(
        DigitalOracleCryptoDerivativesProviderQuery(
            venue="coingecko",
            assets=("BTC",),
            data_types=("spot", "global_market"),
            expirations=None,
            include_order_book=False,
            depth_limit=5,
            item_limit=5,
            timeout_seconds=2.5,
        )
    )

    assert coingecko_result.spot[0].symbol == "BTC"
    assert coingecko_result.spot[0].price == Decimal("65000.5")
    assert coingecko_result.global_metrics[0].market_cap == Decimal("2500000000000")
    assert cast(dict[str, object], coingecko_client.calls[0]["params"])["ids"] == "bitcoin"

    deribit_client = _FakeCryptoDerivativesJsonClient(
        {
            "get_instruments": {
                "result": [
                    {
                        "instrument_name": "BTC-26JUN26",
                        "expiration_timestamp": 1782432000000,
                    },
                    {
                        "instrument_name": "BTC-26JUN26-70000-C",
                        "expiration_timestamp": 1782432000000,
                        "strike": "70000",
                        "option_type": "call",
                    },
                ]
            },
            "get_book_summary_by_currency": {
                "result": [
                    {
                        "instrument_name": "BTC-26JUN26",
                        "mark_iv": "55",
                        "open_interest": "1200",
                    },
                    {
                        "instrument_name": "BTC-26JUN26-70000-C",
                        "mark_iv": "61",
                        "open_interest": "35",
                    },
                ]
            },
            "get_order_book": {
                "result": {
                    "instrument_name": "BTC-26JUN26",
                    "bids": [["64990", "2.5"], ["64980", "1"]],
                    "asks": [["65010", "1.75"], ["65020", "3"]],
                }
            },
        }
    )
    deribit_result = DeribitCryptoDerivativesProvider(deribit_client).lookup_crypto_derivatives(
        DigitalOracleCryptoDerivativesProviderQuery(
            venue="deribit",
            assets=("BTC",),
            data_types=("term_structure", "option_chain", "order_book"),
            expirations=(date(2026, 6, 26),),
            include_order_book=True,
            depth_limit=1,
            item_limit=5,
            timeout_seconds=2.5,
        )
    )

    assert deribit_result.term_structure[0].instrument == "BTC-26JUN26"
    assert deribit_result.term_structure[0].implied_volatility == Decimal("55")
    assert deribit_result.options[0].strike == Decimal("70000")
    assert deribit_result.options[0].open_interest == Decimal("35")
    assert deribit_result.order_books[0].bids == (
        DigitalOracleCryptoDerivativesOrderBookLevel(
            price=Decimal("64990"),
            size=Decimal("2.5"),
        ),
    )


def test_crypto_derivatives_failure_paths_preserve_partial_results_and_scrub_payloads() -> None:
    coingecko_provider = _FakeDigitalOracleCryptoDerivativesProvider(
        "coingecko",
        failure=DigitalOracleProviderError(
            "CoinGecko rate limited crypto derivatives with provider token sk-provider-secret",
            code="provider_rate_limited",
            details={"provider": "coingecko", "api_key": "sk-provider-secret", "status": "429"},
        ),
    )
    deribit_provider = _FakeDigitalOracleCryptoDerivativesProvider(
        "deribit",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="deribit",
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    instrument="BTC-26JUN26",
                ),
            ),
            warnings=(
                RuntimeToolWarning(
                    code="crypto_derivatives_malformed_payload",
                    message="deribit returned malformed crypto-derivatives orderbook.",
                    details={
                        "operation": "crypto_derivatives",
                        "provider": "deribit",
                        "field": "orderbook",
                    },
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        crypto_derivatives_providers=(coingecko_provider, deribit_provider),
    )

    payload = map_crypto_derivatives_result(
        service.lookup_crypto_derivatives(
            DigitalOracleCryptoDerivativesQuery(
                assets=("BTC",),
                venues=("coingecko", "deribit"),
                data_types=("spot", "term_structure", "order_book"),
                include_order_book=True,
            )
        )
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert cast(list[dict[str, object]], payload["termStructure"])[0]["instrument"] == (
        "BTC-26JUN26"
    )
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "crypto_derivatives_provider_rate_limited",
        "crypto_derivatives_malformed_payload",
        "crypto_derivatives_partial_result",
    ]
    assert warnings[0]["message"] == (
        "CoinGecko rate limited crypto derivatives with provider token <redacted>"
    )
    assert warnings[0]["details"] == {
        "operation": "crypto_derivatives",
        "provider": "coingecko",
        "status": "429",
    }
    payload_json = json.dumps(payload, sort_keys=True)
    assert "rawPayload" not in payload_json
    assert "providerPayload" not in payload_json
    assert "api_key" not in payload_json
    assert "sk-provider-secret" not in payload_json


def test_crypto_derivatives_executor_dispatches_native_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleCryptoDerivativesProvider(
        "coingecko",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="coingecko",
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="coingecko",
                    symbol="BTC",
                    price=Decimal("65000.5"),
                    currency="USD",
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_crypto_derivatives.create_crypto_derivatives_providers",
        lambda: (provider,),
    )

    payload = execute_crypto_derivatives_lookup(
        _runtime_context(fail_on_session=True),
        parse_crypto_derivatives_lookup_arguments(
            json.dumps(
                {
                    "assets": ["btc"],
                    "venues": ["coingecko"],
                    "dataTypes": ["spot"],
                    "itemLimit": 1,
                }
            )
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].assets == ("BTC",)
    assert provider.calls[0].item_limit == 1
    assert payload["toolKey"] == CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
    assert cast(list[dict[str, object]], payload["spot"])[0]["price"] == "65000.5"


def test_options_lookup_tool_spec_uses_native_parameters_schema() -> None:
    assert OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_digital_oracle_options_lookup"
    assert OPTIONS_LOOKUP_TOOL_SPEC.key == OPTIONS_LOOKUP_TOOL_KEY
    assert OPTIONS_LOOKUP_TOOL_SPEC.parser is parse_options_lookup_arguments
    assert OPTIONS_LOOKUP_TOOL_SPEC.executor is execute_options_lookup
    assert OPTIONS_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY

    schema = OPTIONS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == ["symbols"]
    assert set(properties) == {"symbols", "expirations", "includeGreeks", "moneyness", "itemLimit"}
    assert cast(dict[str, object], properties["symbols"])["maxItems"] == 10
    assert cast(dict[str, object], properties["itemLimit"])["maximum"] == 50


def test_options_lookup_parser_normalizes_symbols_and_rejects_invalid_args() -> None:
    arguments = parse_options_lookup_arguments(
        json.dumps(
            {
                "symbols": [" aapl ", "AAPL", "msft"],
                "expirations": ["2026-07-17"],
                "includeGreeks": True,
                "moneyness": "near_the_money",
                "itemLimit": 5,
            }
        )
    )

    assert arguments == {
        "symbols": ("AAPL", "MSFT"),
        "expirations": (date(2026, 7, 17),),
        "include_greeks": True,
        "moneyness": "near_the_money",
        "item_limit": 5,
    }
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_options_lookup_arguments(json.dumps({"symbol": "AAPL"}))
    with pytest.raises(RuntimeToolError, match="symbols is required"):
        _ = parse_options_lookup_arguments(json.dumps({}))
    with pytest.raises(RuntimeToolError, match="symbols must contain at most 10"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": [f"S{index}" for index in range(11)]})
        )
    with pytest.raises(RuntimeToolError, match="expirations must be valid ISO dates"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": ["AAPL"], "expirations": ["soon"]})
        )
    with pytest.raises(RuntimeToolError, match="moneyness must use"):
        _ = parse_options_lookup_arguments(json.dumps({"symbols": ["AAPL"], "moneyness": "atm"}))
    with pytest.raises(RuntimeToolError, match="includeGreeks must be a boolean"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": ["AAPL"], "includeGreeks": "yes"})
        )
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_options_lookup_arguments(json.dumps({"symbols": ["AAPL"], "itemLimit": 51}))


def test_options_lookup_provider_maps_fake_yfinance_chain_and_filters_moneyness() -> None:
    ticker = _FakeOptionsTicker(
        chains_by_expiration={
            "2026-07-17": _FakeOptionsChainPayload(
                calls=(
                    {
                        "contractSymbol": "AAPL260717C00190000",
                        "strike": "190",
                        "lastPrice": "12.5",
                        "bid": "12.4",
                        "ask": "12.6",
                        "volume": "1000",
                        "openInterest": "5000",
                        "delta": "0.61",
                        "gamma": "0.04",
                        "theta": "-0.03",
                        "vega": "0.18",
                        "rho": "0.05",
                        "impliedVolatility": "0.32",
                    },
                    {"contractSymbol": "AAPL260717C00210000", "strike": "210"},
                ),
                puts=(
                    {"contractSymbol": "AAPL260717P00190000", "strike": "190"},
                    {
                        "contractSymbol": "AAPL260717P00210000",
                        "strike": "210",
                        "lastPrice": "13.1",
                        "bid": "13.0",
                        "ask": "13.2",
                        "openInterest": "4200",
                        "delta": "-0.39",
                        "impliedVolatility": "0.31",
                    },
                ),
            )
        },
        spot_price=Decimal("200"),
    )
    factory = _FakeOptionsTickerFactory(ticker)

    result = YahooOptionsProvider(factory).lookup_options(
        DigitalOracleOptionsProviderQuery(
            symbol="AAPL",
            expirations=(date(2026, 7, 17),),
            include_greeks=True,
            moneyness="itm",
            item_limit=5,
            timeout_seconds=2.5,
        )
    )

    assert factory.symbols == ["AAPL"]
    assert ticker.option_chain_calls == ["2026-07-17"]
    assert result.warnings == ()
    chain = result.chains[0]
    assert chain.expiry_date == date(2026, 7, 17)
    assert chain.calls[0].contract_symbol == "AAPL260717C00190000"
    assert chain.calls[0].greeks == DigitalOracleOptionGreeks(
        delta=Decimal("0.61"),
        gamma=Decimal("0.04"),
        theta=Decimal("-0.03"),
        vega=Decimal("0.18"),
        rho=Decimal("0.05"),
        implied_volatility=Decimal("0.32"),
    )
    assert [contract.contract_symbol for contract in chain.puts] == ["AAPL260717P00210000"]


def test_options_lookup_service_and_executor_return_normalized_fake_provider_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleOptionsProvider(
        result=DigitalOracleOptionsProviderResult(
            provider="yahoo",
            chains=(
                DigitalOracleOptionsChain(
                    provider="yahoo",
                    symbol="AAPL",
                    expiry_date=date(2026, 7, 17),
                    calls=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717C00200000",
                            strike=Decimal("200"),
                            bid=Decimal("6.2"),
                            ask=Decimal("6.3"),
                            last_price=Decimal("6.25"),
                            volume=Decimal("1000"),
                            open_interest=Decimal("5000"),
                            greeks=DigitalOracleOptionGreeks(implied_volatility=Decimal("0.32")),
                        ),
                    ),
                    puts=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717P00200000",
                            strike=Decimal("200"),
                            bid=Decimal("5.7"),
                            ask=Decimal("5.8"),
                            last_price=Decimal("5.75"),
                        ),
                    ),
                ),
            ),
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.factory.importlib.util.find_spec",
        lambda module_name: object(),
    )
    service_payload = map_options_result(
        DigitalOraclePhase1Service(options_providers=(provider,)).lookup_options(
            DigitalOracleOptionsQuery(
                symbols=(" aapl ",),
                expirations=(date(2026, 7, 17),),
                include_greeks=True,
                moneyness="near_the_money",
                item_limit=1,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_options.create_options_providers",
        lambda: (provider,),
    )
    executor_payload = execute_options_lookup(
        _runtime_context(fail_on_session=True),
        parse_options_lookup_arguments(
            json.dumps(
                {
                    "symbols": ["AAPL"],
                    "expirations": ["2026-07-17"],
                    "includeGreeks": True,
                    "moneyness": "near_the_money",
                    "itemLimit": 1,
                }
            )
        ),
    )

    for payload in (service_payload, executor_payload):
        _assert_native_runtime_payload_is_json_safe_and_camel(payload)
        assert payload["toolKey"] == OPTIONS_LOOKUP_TOOL_KEY
        assert payload["symbol"] == "AAPL"
        chain = cast(list[dict[str, object]], payload["chains"])[0]
        assert chain["expiryDate"] == "2026-07-17"
        call = cast(list[dict[str, object]], chain["calls"])[0]
        assert call["contractSymbol"] == "AAPL260717C00200000"
        assert call["bid"] == "6.2"
        assert cast(dict[str, object], call["greeks"])["impliedVolatility"] == "0.32"
        assert payload["warnings"] == []


def test_options_lookup_missing_yfinance_degrades_and_keeps_registry_import_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_yfinance(module_name: str) -> object:
        if module_name == "yfinance":
            raise ImportError("No module named yfinance")
        return importlib.import_module(module_name)

    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.factory.importlib.util.find_spec",
        lambda module_name: None if module_name == "yfinance" else object(),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_options_providers.importlib.import_module",
        missing_yfinance,
    )
    _reset_runtime_settings_caches()
    try:
        app = create_app(init_database=False)
        registry = get_default_runtime_tool_registry()
        payload = registry.dispatch(
            name=OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json=json.dumps({"symbols": ["AAPL"], "includeGreeks": True}),
            granted_tool_keys={OPTIONS_LOOKUP_TOOL_KEY},
            context=_runtime_context(fail_on_session=True),
        )
    finally:
        _reset_runtime_settings_caches()

    assert app is not None
    assert OPTIONS_LOOKUP_TOOL_KEY in {spec.key for spec in registry.list_specs()}
    assert payload["toolKey"] == OPTIONS_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "AAPL"
    assert payload["chains"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "digital_oracle_yfinance_missing",
        "options_provider_unavailable",
        "options_unavailable",
    ]
    assert warnings[0]["details"] == {
        "operation": "options",
        "dependency": "yfinance",
        "provider": "yfinance",
    }
    assert warnings[1]["details"] == {
        "operation": "options",
        "provider": "yahoo",
        "dependency": "yfinance",
    }


def test_sec_filings_runtime_tool_spec_uses_approved_parameters_schema() -> None:
    assert SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_digital_oracle_sec_filings_lookup"
    assert SEC_FILINGS_LOOKUP_TOOL_SPEC.key == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert (
        SEC_FILINGS_LOOKUP_TOOL_SPEC.openai_function_name == SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert SEC_FILINGS_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert SEC_FILINGS_LOOKUP_TOOL_SPEC.parser is parse_sec_filings_lookup_arguments
    assert SEC_FILINGS_LOOKUP_TOOL_SPEC.executor is execute_sec_filings_lookup

    schema = SEC_FILINGS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == []
    assert set(properties) == {
        "ticker",
        "query",
        "cik",
        "formTypes",
        "startDate",
        "endDate",
        "itemLimit",
        "includeOwnershipTransactions",
    }
    assert cast(dict[str, object], properties["query"])["maxLength"] == 200
    assert cast(dict[str, object], properties["itemLimit"])["maximum"] == 50


def test_sec_filings_parser_normalizes_ticker_form_types_and_dates() -> None:
    arguments = parse_sec_filings_lookup_arguments(
        json.dumps(
            {
                "ticker": " nvda ",
                "query": "  Annual   report  ",
                "cik": "CIK1045810",
                "formTypes": [" 10-k ", "8-K", "10-K"],
                "startDate": "2026-01-01",
                "endDate": "2026-12-31",
                "itemLimit": 3,
                "includeOwnershipTransactions": True,
            }
        )
    )

    assert arguments == {
        "ticker": "NVDA",
        "query": "Annual report",
        "cik": "0001045810",
        "form_types": ("10-K", "8-K"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "item_limit": 3,
        "include_ownership_transactions": True,
    }

    assert parse_sec_filings_lookup_arguments(json.dumps({"cik": "320193"})) == {
        "ticker": None,
        "query": None,
        "cik": "0000320193",
        "form_types": None,
        "start_date": None,
        "end_date": None,
        "item_limit": None,
        "include_ownership_transactions": False,
    }

    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA", "contactEmail": "x"}))
    with pytest.raises(RuntimeToolError, match="ticker or cik is required"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"query": "annual report"}))
    with pytest.raises(RuntimeToolError, match="query must not be empty"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA", "query": "   "}))
    with pytest.raises(RuntimeToolError, match="cik must contain 1 to 10 digits"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"cik": "12-34"}))
    with pytest.raises(RuntimeToolError, match="includeOwnershipTransactions must be a boolean"):
        _ = parse_sec_filings_lookup_arguments(
            json.dumps({"ticker": "NVDA", "includeOwnershipTransactions": "yes"})
        )
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_sec_filings_lookup_arguments(
            json.dumps(
                {
                    "ticker": "NVDA",
                    "startDate": "2026-12-31",
                    "endDate": "2026-01-01",
                }
            )
        )


def test_edgar_sec_filings_provider_maps_company_submissions_to_normalized_filings() -> None:
    form4_xml = """
<ownershipDocument>
  <issuer>
    <issuerName>NVIDIA CORP</issuerName>
    <issuerTradingSymbol>NVDA</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Ada Lovelace</rptOwnerName></reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-02-21</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10</value></transactionShares>
        <transactionPricePerShare><value>120.25</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""
    newer_form4_xml = """
<ownershipDocument>
  <issuer>
    <issuerName>NVIDIA CORP</issuerName>
    <issuerTradingSymbol>NVDA</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Grace Hopper</rptOwnerName></reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-03-04</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5</value></transactionShares>
        <transactionPricePerShare><value>130.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""
    client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": [
                            "0001045810-26-000010",
                            "0001045810-26-000011",
                            "0001045810-26-000020",
                            "0001045810-26-000021",
                        ],
                        "form": ["10-K", "8-K", "4", "4"],
                        "filingDate": [
                            "2026-02-20",
                            "2026-03-01",
                            "2026-02-22",
                            "2026-03-05",
                        ],
                        "acceptanceDateTime": [
                            "2026-02-20T16:30:01.000Z",
                            "20260301120000",
                            "2026-02-22T12:00:00Z",
                            "2026-03-05T12:00:00Z",
                        ],
                        "primaryDocument": [
                            "nvda-20260131.htm",
                            "nvda-8k.htm",
                            "form4.xml",
                            "form4-new.xml",
                        ],
                        "primaryDocDescription": [
                            "Annual report",
                            "Current report",
                            "Statement of changes in beneficial ownership",
                            "Statement of changes in beneficial ownership",
                        ],
                    }
                },
            },
        },
        text_by_url_fragment={"form4.xml": form4_xml, "form4-new.xml": newer_form4_xml},
    )
    provider = EdgarSecFilingsProvider(http_client=client)

    result = provider.lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=2,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )

    assert [call["contactEmail"] for call in client.calls] == [
        "sec-contact@example.test",
        "sec-contact@example.test",
    ]
    assert [call["timeout"] for call in client.calls] == [2.5, 2.5]
    assert result.cik == "0001045810"
    assert result.entity_name == "NVIDIA CORP"
    assert result.warnings == ()
    assert [filing.form_type for filing in result.filings] == ["10-K", "8-K", "4", "4"]
    assert result.filings[0].accepted_at == datetime(2026, 2, 20, 16, 30, 1, tzinfo=UTC)
    assert result.filings[0].url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-20260131.htm"
    )
    assert result.filings[0].description == "Annual report"
    assert len(client.text_calls) == 1
    assert client.text_calls[0]["contactEmail"] == "sec-contact@example.test"
    assert "form4-new.xml" in str(client.text_calls[0]["url"])
    assert result.ownership_transactions == (
        DigitalOracleSecOwnershipTransaction(
            accession_number="0001045810-26-000021",
            filing_date=date(2026, 3, 5),
            issuer_name="NVIDIA CORP",
            issuer_ticker="NVDA",
            reporting_owner_name="Grace Hopper",
            transaction_date=date(2026, 3, 4),
            transaction_code="S",
            acquired_disposed_code="D",
            shares=Decimal("5"),
            price=Decimal("130.50"),
            ownership_nature="I",
        ),
    )


def test_edgar_sec_filings_provider_uses_first_exact_ticker_when_mapping_is_ambiguous() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1111111, "ticker": "NVDA", "title": "FIRST NVDA CORP"},
                "1": {"cik_str": 2222222, "ticker": "NVDA", "title": "SECOND NVDA CORP"},
            },
            "CIK0001111111": {
                "name": "FIRST NVDA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001111111-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )

    assert [call["url"] for call in client.calls] == [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/CIK0001111111.json",
    ]
    assert result.cik == "0001111111"
    assert result.entity_name == "FIRST NVDA CORP"
    assert result.filings[0].accession_number == "0001111111-26-000010"
    assert result.warnings == ()


def test_edgar_sec_filings_provider_supports_cik_lookup_without_ticker() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"},
            },
            "CIK0000320193": {
                "name": "APPLE INC",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000320193-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker=None,
            query=None,
            cik="0000320193",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )

    assert [call["url"] for call in client.calls] == [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/CIK0000320193.json",
    ]
    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert result.entity_name == "APPLE INC"
    assert result.filings[0].accession_number == "0000320193-26-000010"


def test_edgar_sec_filings_provider_tolerates_optional_arrays_and_reuses_cik_cache() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )
    provider = EdgarSecFilingsProvider(http_client=client)
    query = DigitalOracleSecFilingsProviderQuery(
        ticker="NVDA",
        form_types=(),
        start_date=None,
        end_date=None,
        item_limit=10,
        edgar_contact_email="sec-contact@example.test",
        timeout_seconds=2.5,
    )

    first_result = provider.lookup_sec_filings(query)
    second_result = provider.lookup_sec_filings(query)

    assert [call["url"] for call in client.calls].count(
        "https://www.sec.gov/files/company_tickers.json"
    ) == 1
    assert first_result.filings[0].primary_document is None
    assert first_result.filings[0].description is None
    assert first_result.filings[0].url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010"
    )
    assert second_result.filings[0].accession_number == "0001045810-26-000010"


def test_edgar_sec_filings_provider_warns_when_recent_data_is_archived_only() -> None:
    client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {"recent": {"accessionNumber": []}, "files": [{"name": "CIK.json"}]},
            },
        }
    )

    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )

    assert result.filings == ()
    assert [warning.code for warning in result.warnings] == ["sec_filings_stale_archive"]
    assert result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "ticker": "NVDA",
        "cik": "0001045810",
    }


def test_edgar_sec_filings_provider_warns_for_ticker_miss_and_malformed_recent_rows() -> None:
    not_found_client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"},
            },
        }
    )
    not_found_result = EdgarSecFilingsProvider(http_client=not_found_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )

    assert len(not_found_client.calls) == 1
    assert not_found_result.filings == ()
    assert [warning.code for warning in not_found_result.warnings] == [
        "sec_filings_ticker_not_found"
    ]
    assert not_found_result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "ticker": "NVDA",
    }

    malformed_client = _FakeEdgarJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["not-a-date"],
                        "primaryDocument": ["nvda-20260131.htm"],
                    }
                },
            },
        }
    )
    malformed_result = EdgarSecFilingsProvider(http_client=malformed_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )

    assert malformed_result.filings == ()
    assert [warning.code for warning in malformed_result.warnings] == [
        "sec_filings_malformed_payload"
    ]
    assert malformed_result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "field": "filing row",
    }


def test_sec_filings_runtime_executor_filters_forms_dates_and_returns_normalized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000011",
                form_type="8-K",
                filing_date=date(2025, 12, 31),
                primary_document="nvda-old-8k.htm",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000012",
                form_type="10-Q",
                filing_date=date(2026, 4, 1),
                primary_document="nvda-10q.htm",
            ),
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_sec_filings_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"edgar_contact_email": "sec-contact@example.test"},
            ),
            parse_sec_filings_lookup_arguments(
                json.dumps(
                    {
                        "ticker": " nvda ",
                        "query": "annual report",
                        "cik": "1045810",
                        "formTypes": ["10-k", "8-k"],
                        "startDate": "2026-01-01",
                        "endDate": "2026-12-31",
                        "itemLimit": 5,
                        "includeOwnershipTransactions": True,
                    }
                )
            ),
        )
    finally:
        _reset_runtime_settings_caches()

    assert provider.calls[0].ticker == "NVDA"
    assert provider.calls[0].query == "annual report"
    assert provider.calls[0].cik == "0001045810"
    assert provider.calls[0].form_types == ("10-K", "8-K")
    assert provider.calls[0].start_date == date(2026, 1, 1)
    assert provider.calls[0].end_date == date(2026, 12, 31)
    assert provider.calls[0].item_limit == 5
    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert provider.calls[0].include_ownership_transactions is True
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert payload["ticker"] == "NVDA"
    assert payload["cik"] == "0001045810"
    assert payload["entityName"] == "NVIDIA CORP"
    filings = cast(list[dict[str, object]], payload["filings"])
    assert filings == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "acceptedAt": "2026-01-02T03:04:05Z",
            "primaryDocument": "nvda-20260131.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
            "description": "Annual report",
        }
    ]
    search_hits = cast(list[dict[str, object]], payload["searchHits"])
    assert search_hits == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "cik": "0001045810",
            "ticker": "NVDA",
            "entityName": "NVIDIA CORP",
            "primaryDocument": "nvda-20260131.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
            "description": "Annual report",
            "matchedText": "Annual report",
        }
    ]
    assert payload["ownershipTransactions"] == []
    assert payload["warnings"] == []


def test_sec_filings_runtime_executor_uses_context_edgar_contact_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_sec_filings_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"edgar_contact_email": "caller-edgar@example.test"},
            ),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        _reset_runtime_settings_caches()

    assert provider.calls[0].edgar_contact_email == "caller-edgar@example.test"
    assert payload["filings"] == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "acceptedAt": None,
            "primaryDocument": None,
            "url": None,
            "description": None,
        }
    ]
    assert "caller-edgar@example.test" not in json.dumps(payload)


def test_sec_filings_runtime_executor_preserves_missing_edgar_email_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_sec_filings_lookup(
            _runtime_context(fail_on_session=True),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        _reset_runtime_settings_caches()

    assert provider.calls == []
    assert payload["filings"] == []
    assert payload["warnings"] == [
        {
            "code": EDGAR_CONTACT_EMAIL_MISSING_CODE,
            "message": EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            "details": {
                "operation": "sec_filings",
                "provider": "edgar",
            },
        }
    ]


def test_sec_filings_runtime_executor_degrades_provider_failure_and_redacts_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleSecFilingsProvider(
        filings=(),
        failure=DigitalOracleProviderError(
            "SEC EDGAR rate limited api_key=sk-edgar-secret",
            code="provider_rate_limited",
            details={"request_id": "edgar-123", "api_key": "sk-edgar-secret"},
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_sec_filings_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"edgar_contact_email": "sec-contact@example.test"},
            ),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        _reset_runtime_settings_caches()

    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert payload["filings"] == []
    warning_json = json.dumps(payload["warnings"])
    assert "sk-edgar-secret" not in warning_json
    assert payload["warnings"] == [
        {
            "code": "sec_filings_provider_rate_limited",
            "message": "SEC EDGAR rate limited api_key=<redacted>",
            "details": {
                "operation": "sec_filings",
                "provider": "edgar",
                "requestId": "edgar-123",
            },
        },
        {
            "code": "sec_filings_unavailable",
            "message": "No sec_filings data available from configured providers.",
            "details": {"operation": "sec_filings"},
        },
    ]


def test_sec_filings_runtime_executor_returns_empty_warning_for_configured_edgar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleSecFilingsProvider(filings=())
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_sec_filings_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"edgar_contact_email": "sec-contact@example.test"},
            ),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        _reset_runtime_settings_caches()

    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert payload["filings"] == []
    assert payload["warnings"] == [
        {
            "code": "sec_filings_empty",
            "message": "No sec_filings data returned from edgar.",
            "details": {"operation": "sec_filings", "provider": "edgar"},
        }
    ]


def test_macro_rates_runtime_tool_spec_uses_approved_parameters_schema() -> None:
    assert MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_digital_oracle_macro_rates_lookup"
    assert MACRO_RATES_LOOKUP_TOOL_SPEC.key == MACRO_RATES_LOOKUP_TOOL_KEY
    assert (
        MACRO_RATES_LOOKUP_TOOL_SPEC.openai_function_name == MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert MACRO_RATES_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert MACRO_RATES_LOOKUP_TOOL_SPEC.parser is parse_macro_rates_lookup_arguments
    assert MACRO_RATES_LOOKUP_TOOL_SPEC.executor is execute_macro_rates_lookup

    schema = MACRO_RATES_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    sources_schema = cast(dict[str, object], properties["sources"])
    families_schema = cast(dict[str, object], properties["families"])
    assert schema["required"] == []
    assert set(properties) == {
        "query",
        "sources",
        "families",
        "seriesIds",
        "countries",
        "startDate",
        "endDate",
        "asOfDate",
        "itemLimit",
    }
    assert cast(dict[str, object], sources_schema["items"])["enum"] == [
        "treasury",
        "bis",
        "worldbank",
        "cme_fedwatch",
        "fred",
    ]
    assert cast(dict[str, object], families_schema["items"])["enum"] == [
        "macro_indicators",
        "yield_curve",
        "fx_rates",
        "policy_rates",
        "credit_gaps",
        "fedwatch",
    ]
    assert cast(dict[str, object], properties["itemLimit"])["maximum"] == 50


def test_macro_rates_parser_normalizes_sources_families_dates_and_filters() -> None:
    arguments = parse_macro_rates_lookup_arguments(
        json.dumps(
            {
                "query": "  Fed   rates  ",
                "sources": [" FRED ", "treasury", "fred"],
                "families": [" Policy_Rates ", "yield_curve", "policy_rates"],
                "seriesIds": [" DGS10 ", "DGS10", "FEDFUNDS"],
                "countries": [" us ", "United States", "US"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-31",
                "asOfDate": "2026-02-01",
                "itemLimit": 3,
            }
        )
    )

    assert arguments == {
        "query": "Fed rates",
        "sources": ("fred", "treasury"),
        "families": ("policy_rates", "yield_curve"),
        "series_ids": ("DGS10", "FEDFUNDS"),
        "countries": ("US", "UNITED STATES"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "as_of_date": date(2026, 2, 1),
        "item_limit": 3,
    }

    assert parse_macro_rates_lookup_arguments("{}") == {
        "query": None,
        "sources": None,
        "families": None,
        "series_ids": None,
        "countries": None,
        "start_date": None,
        "end_date": None,
        "as_of_date": None,
        "item_limit": None,
    }

    with pytest.raises(RuntimeToolError, match="sources must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"sources": ["ecb"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["rates"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["policy_rate"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["macro_indicator"]}))
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_macro_rates_lookup_arguments(
            json.dumps({"startDate": "2026-02-01", "endDate": "2026-01-01"})
        )
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"itemLimit": 51}))


def test_macro_rates_providers_map_public_payloads_to_normalized_series() -> None:
    client = _FakeMacroRatesJsonClient(
        {
            "fred/series/observations": {
                "observations": [
                    {"date": "2026-01-02", "value": "4.33"},
                    {"date": "2026-01-03", "value": "."},
                ]
            },
            "treasury.gov": {
                "data": [
                    {
                        "record_date": "2026-01-02",
                        "security_desc": "10-Year Treasury Constant Maturity",
                        "avg_interest_rate_amt": "4.15",
                        "security_term": "10 Yr",
                    }
                ]
            },
            "bis.org": {
                "observations": [
                    {
                        "date": "2026-01-02",
                        "value": "5.25",
                        "country": "US",
                        "series_id": "BIS-US-POLICY",
                        "label": "United States policy rate",
                    }
                ]
            },
        }
    )
    fred_query = DigitalOracleMacroRatesProviderQuery(
        source="fred",
        query="Fed funds",
        families=("macro_indicators",),
        series_ids=("FEDFUNDS",),
        countries=("US",),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        as_of_date=None,
        item_limit=5,
        timeout_seconds=2.5,
        fred_api_key="fred-key",
    )
    treasury_query = replace(
        fred_query,
        source="treasury",
        families=("yield_curve",),
        fred_api_key=None,
    )
    bis_query = replace(fred_query, source="bis", families=("policy_rates",), fred_api_key=None)

    fred_result = FredMacroRatesProvider(client).lookup_macro_rates(fred_query)
    treasury_result = TreasuryMacroRatesProvider(client).lookup_macro_rates(treasury_query)
    bis_result = BisMacroRatesProvider(client).lookup_macro_rates(bis_query)

    assert fred_result.series[0].provider == "fred"
    assert fred_result.series[0].family == "macro_indicators"
    assert fred_result.series[0].series_id == "FEDFUNDS"
    assert fred_result.series[0].date == date(2026, 1, 2)
    assert fred_result.series[0].value == Decimal("4.33")
    assert [warning.code for warning in fred_result.warnings] == ["macro_rates_malformed_payload"]
    assert treasury_result.series[0].tenor == "10Y"
    assert treasury_result.series[0].family == "yield_curve"
    assert bis_result.series[0].family == "policy_rates"
    assert bis_result.series[0].country == "US"
    non_fred_calls = [call for call in client.calls if call["provider"] != "fred"]
    assert "fred-key" not in json.dumps(non_fred_calls)


def test_macro_rates_runtime_executor_returns_normalized_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fred_provider = _FakeDigitalOracleMacroRatesProvider(
        "fred",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="fred",
                family="macro_indicators",
                series_id="FEDFUNDS",
                label="Federal Funds Effective Rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.33"),
                source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
            ),
        ),
    )
    treasury_provider = _FakeDigitalOracleMacroRatesProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-10Y",
                label="US Treasury 10Y par yield",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.15"),
                tenor="10Y",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    bis_provider = _FakeDigitalOracleMacroRatesProvider(
        "bis",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="bis",
                family="policy_rates",
                series_id="BIS-US-POLICY",
                label="United States policy rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("5.25"),
                source_url="https://www.bis.org/statistics/",
            ),
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_macro_rates.create_macro_rates_providers",
        lambda: (fred_provider, treasury_provider, bis_provider),
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_macro_rates_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"fred_api_key": "fred-key"},
            ),
            parse_macro_rates_lookup_arguments(
                json.dumps(
                    {
                        "query": "rates",
                        "sources": ["fred", "treasury", "bis"],
                        "itemLimit": 3,
                    }
                )
            ),
        )
    finally:
        _reset_runtime_settings_caches()

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == MACRO_RATES_LOOKUP_TOOL_KEY
    assert payload["query"] == "rates"
    series = cast(list[dict[str, object]], payload["series"])
    assert [item["provider"] for item in series] == ["fred", "treasury", "bis"]
    assert [item["seriesId"] for item in series] == ["FEDFUNDS", "UST-10Y", "BIS-US-POLICY"]
    assert series[1]["tenor"] == "10Y"
    assert payload["warnings"] == []


def test_macro_rates_runtime_executor_uses_context_fred_api_key_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fred_provider = _FakeDigitalOracleMacroRatesProvider(
        "fred",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="fred",
                family="macro_indicators",
                series_id="FEDFUNDS",
                label="Federal Funds Effective Rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.33"),
            ),
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_macro_rates.create_macro_rates_providers",
        lambda: (fred_provider,),
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_macro_rates_lookup(
            _runtime_context(
                fail_on_session=True,
                secret_values={"fred_api_key": "caller-fred-key"},
            ),
            parse_macro_rates_lookup_arguments(
                json.dumps({"sources": ["fred"], "seriesIds": ["FEDFUNDS"], "itemLimit": 1})
            ),
        )
    finally:
        _reset_runtime_settings_caches()

    assert fred_provider.calls[0].fred_api_key == "caller-fred-key"
    assert payload["series"] == [
        {
            "provider": "fred",
            "family": "macro_indicators",
            "seriesId": "FEDFUNDS",
            "label": "Federal Funds Effective Rate",
            "country": "US",
            "currency": "USD",
            "unit": "percent",
            "date": "2026-01-02",
            "value": "4.33",
            "tenor": None,
            "sourceUrl": None,
        }
    ]
    assert "caller-fred-key" not in json.dumps(payload)


def test_macro_rates_runtime_executor_preserves_partial_warnings_without_fred_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treasury_provider = _FakeDigitalOracleMacroRatesProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-10Y",
                label="US Treasury 10Y par yield",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.15"),
                tenor="10Y",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    bis_provider = _FakeDigitalOracleMacroRatesProvider(
        "bis",
        failure=DigitalOracleProviderError(
            "BIS timed out while fetching policy rates",
            code="provider_timeout",
            details={"provider": "bis"},
        ),
    )
    fred_provider = _FakeDigitalOracleMacroRatesProvider("fred")
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_macro_rates.create_macro_rates_providers",
        lambda: (treasury_provider, bis_provider, fred_provider),
    )
    _reset_runtime_settings_caches()
    try:
        payload = execute_macro_rates_lookup(
            _runtime_context(fail_on_session=True),
            parse_macro_rates_lookup_arguments(
                json.dumps({"sources": ["treasury", "bis", "fred"], "itemLimit": 5})
            ),
        )
    finally:
        _reset_runtime_settings_caches()

    assert fred_provider.calls == []
    assert treasury_provider.calls[0].source == "treasury"
    assert bis_provider.calls[0].source == "bis"
    series = cast(list[dict[str, object]], payload["series"])
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [item["provider"] for item in series] == ["treasury"]
    assert [warning["code"] for warning in warnings] == [
        FRED_API_KEY_MISSING_CODE,
        "macro_rates_provider_timeout",
        "macro_rates_partial_result",
    ]
    assert warnings[0]["message"] == FRED_API_KEY_MISSING_MESSAGE
    assert warnings[0]["details"] == {
        "operation": "macro_rates",
        "provider": "fred",
    }
    assert warnings[1]["details"] == {"operation": "macro_rates", "provider": "bis"}


def test_macro_rates_result_aliasing_rejects_raw_provider_fields() -> None:
    payload = map_macro_rates_result(
        DigitalOracleMacroRatesResult(
            query="rates",
            series=(
                DigitalOracleMacroRatesSeries(
                    provider="treasury",
                    family="yield_curve",
                    series_id="UST-2Y",
                    label="US Treasury 2Y par yield",
                    country="US",
                    currency="USD",
                    unit="percent",
                    date=date(2026, 1, 2),
                    value=Decimal("3.95"),
                    tenor="2Y",
                    source_url="https://home.treasury.gov/",
                ),
            ),
        )
    ).model_dump(mode="json", by_alias=True)

    assert payload["toolKey"] == MACRO_RATES_LOOKUP_TOOL_KEY
    series = cast(list[dict[str, object]], payload["series"])
    assert series[0] == {
        "provider": "treasury",
        "family": "yield_curve",
        "seriesId": "UST-2Y",
        "label": "US Treasury 2Y par yield",
        "country": "US",
        "currency": "USD",
        "unit": "percent",
        "date": "2026-01-02",
        "value": "3.95",
        "tenor": "2Y",
        "sourceUrl": "https://home.treasury.gov/",
    }
    serialized = json.dumps(payload)
    assert "rawPayload" not in serialized
    assert "requestConfig" not in serialized


def test_macro_rates_runtime_registry_dispatch_and_disabled_extension_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleMacroRatesProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-3M",
                label="US Treasury 3M bill rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.01"),
                tenor="3M",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_macro_rates.create_macro_rates_providers",
        lambda: (provider,),
    )
    registry = RuntimeToolRegistry([MACRO_RATES_LOOKUP_TOOL_SPEC])
    payload = registry.dispatch(
        name=MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps({"sources": ["treasury"], "families": ["yield_curve"]}),
        granted_tool_keys={MACRO_RATES_LOOKUP_TOOL_KEY},
        context=_runtime_context(fail_on_session=True),
    )

    assert provider.calls[0].families == ("yield_curve",)
    assert payload["toolKey"] == MACRO_RATES_LOOKUP_TOOL_KEY
    assert len(cast(list[dict[str, object]], payload["series"])) == 1
    with pytest.raises(RuntimeToolError) as denied_error:
        _ = registry.dispatch(
            name=MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=_runtime_context(fail_on_session=True),
        )
    assert denied_error.value.code == "agent_execution_access_denied"
    assert denied_error.value.message == DIGITAL_ORACLE_DENIED_MESSAGES[MACRO_RATES_LOOKUP_TOOL_KEY]


def test_market_sentiment_runtime_tool_spec_uses_approved_parameters_schema() -> None:
    assert (
        MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME
        == "signaldeck_digital_oracle_market_sentiment_lookup"
    )
    assert MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.key == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert (
        MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.openai_function_name
        == MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.parser is parse_market_sentiment_lookup_arguments
    assert MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.executor is execute_market_sentiment_lookup

    schema = MARKET_SENTIMENT_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    indicator_property = cast(dict[str, object], properties["indicator"])
    assert schema["required"] == ["indicator"]
    assert set(properties) == {"indicator", "asOfDate"}
    assert indicator_property["enum"] == ["fear_greed"]


def test_market_sentiment_parser_normalizes_indicator_and_as_of_date() -> None:
    arguments = parse_market_sentiment_lookup_arguments(
        json.dumps({"indicator": " Fear_Greed ", "asOfDate": "2026-01-02"})
    )

    assert arguments == {"indicator": "fear_greed", "as_of_date": date(2026, 1, 2)}

    with pytest.raises(RuntimeToolError) as invalid_indicator:
        _ = parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "social_sentiment"}))
    assert invalid_indicator.value.message == (
        "signaldeck_digital_oracle_market_sentiment_lookup indicator must use: fear_greed."
    )

    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_market_sentiment_lookup_arguments(
            json.dumps({"indicator": "fear_greed", "symbol": "NVDA"})
        )


def test_fear_greed_provider_maps_snapshot_to_normalized_market_sentiment() -> None:
    client = _FakeFearGreedJsonClient(
        {
            "fear_and_greed": {
                "score": 72.4,
                "rating": "Greed",
                "timestamp": "2026-01-02T03:04:05Z",
                "previous_close": 70.1,
                "previous_1_week": "64",
                "previous_1_month": 55.4,
                "previous_1_year": 41,
            }
        }
    )
    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )

    assert client.calls[0]["timeout"] == 2.5
    assert client.calls[0]["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert result.provider == "fear_greed"
    assert result.score == 72
    assert result.label == "greed"
    assert result.as_of_date == date(2026, 1, 2)
    assert result.previous_close == 70
    assert result.week_ago == 64
    assert result.month_ago == 55
    assert result.year_ago == 41
    assert result.source_url == MARKET_SENTIMENT_SOURCE_URL
    assert result.warnings == ()


def test_fear_greed_provider_warns_for_sparse_history_without_inventing_values() -> None:
    client = _FakeFearGreedJsonClient(
        {
            "fear_and_greed": {
                "score": 18,
                "timestamp": 1767225600000,
                "previous_close": 21,
                "previous_1_week": 30,
                "previous_1_month": 44,
            }
        }
    )
    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )

    assert result.score == 18
    assert result.label == "extreme_fear"
    assert result.as_of_date == date(2026, 1, 1)
    assert result.year_ago is None
    assert result.warnings == (
        RuntimeToolWarning(
            code="market_sentiment_sparse_history",
            message=(
                "Fear & Greed history is incomplete for the requested market sentiment snapshot."
            ),
            details={
                "operation": "market_sentiment",
                "provider": "fear_greed",
                "missingFields": "yearAgo",
            },
        ),
    )


@pytest.mark.parametrize(
    ("score", "expected_label"),
    [
        (24, "extreme_fear"),
        (25, "fear"),
        (44, "fear"),
        (45, "neutral"),
        (55, "neutral"),
        (74, "greed"),
        (75, "extreme_greed"),
    ],
)
def test_fear_greed_provider_derives_missing_rating_with_required_thresholds(
    score: int,
    expected_label: str,
) -> None:
    client = _FakeFearGreedJsonClient(
        {
            "fear_and_greed": {
                "score": score,
                "timestamp": "2026-01-02",
                "previous_close": 70,
                "previous_1_week": 64,
                "previous_1_month": 55,
                "previous_1_year": 41,
            }
        }
    )

    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )

    assert result.label == expected_label
    assert result.score == score
    assert result.source_url == MARKET_SENTIMENT_SOURCE_URL
    assert result.warnings == ()


def test_market_sentiment_runtime_executor_returns_normalized_fear_greed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=79,
            label="extreme_greed",
            as_of_date=date(2026, 1, 2),
            previous_close=74,
            week_ago=66,
            month_ago=58,
            year_ago=42,
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )

    payload = execute_market_sentiment_lookup(
        _runtime_context(fail_on_session=True),
        parse_market_sentiment_lookup_arguments(
            json.dumps({"indicator": "fear_greed", "asOfDate": "2026-01-02"})
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].indicator == "fear_greed"
    assert provider.calls[0].as_of_date == date(2026, 1, 2)
    assert provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert payload == {
        "toolKey": MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        "indicator": "fear_greed",
        "asOfDate": "2026-01-02",
        "provider": "fear_greed",
        "score": 79,
        "label": "extreme_greed",
        "previousClose": 74,
        "weekAgo": 66,
        "monthAgo": 58,
        "yearAgo": 42,
        "sourceUrl": MARKET_SENTIMENT_SOURCE_URL,
        "warnings": [],
    }


def test_market_sentiment_runtime_executor_returns_empty_warning_for_empty_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleMarketSentimentProvider(
        DigitalOracleMarketSentimentProviderResult(provider="fear_greed")
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )

    payload = execute_market_sentiment_lookup(
        _runtime_context(fail_on_session=True),
        parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "fear_greed"})),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert payload["score"] is None
    assert payload["label"] is None
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_empty",
            "message": "No market_sentiment data returned from fear_greed.",
            "details": {"operation": "market_sentiment", "provider": "fear_greed"},
        }
    ]


def test_market_sentiment_service_degrades_malformed_payload_to_warning() -> None:
    client = _FakeFearGreedJsonClient({"unexpected": {}})
    provider = FearGreedMarketSentimentProvider(http_client=client)
    service = DigitalOraclePhase1Service(market_sentiment_provider=provider)

    payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert client.calls[0]["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["score"] is None
    assert payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_provider_error",
            "message": "Fear & Greed provider returned malformed market sentiment data",
            "details": {"operation": "market_sentiment", "provider": "fear_greed"},
        }
    ]


def test_market_sentiment_runtime_executor_preserves_upstream_failure_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeDigitalOracleMarketSentimentProvider(
        failure=DigitalOracleProviderError(
            "Fear & Greed endpoint failed with token=sk-runtime-secret",
            code="provider_unavailable",
            details={"token": "sk-runtime-secret", "request_id": "fg-123"},
        )
    )
    monkeypatch.setattr(
        "app.extensions.signaldeck_digital_oracle.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )

    payload = execute_market_sentiment_lookup(
        _runtime_context(fail_on_session=True),
        parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "fear_greed"})),
    )

    assert provider.calls[0].indicator == "fear_greed"
    assert payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["score"] is None
    assert payload["label"] is None
    assert payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_provider_unavailable",
            "message": "Fear & Greed endpoint failed with token=<redacted>",
            "details": {
                "operation": "market_sentiment",
                "provider": "fear_greed",
                "requestId": "fg-123",
            },
        }
    ]
