from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib import import_module
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.runtime_tools import get_default_runtime_tool_registry
from app.agents.runtime_tools.types import RuntimeToolWarning
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.signaldeck_digital_oracle.mappers import (
    map_cftc_positioning_result,
    map_crypto_derivatives_result,
    map_macro_rates_result,
    map_options_result,
)
from app.extensions.signaldeck_digital_oracle.ownership import (
    DIGITAL_ORACLE_EXTENSION_KEY,
    DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES,
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_digital_oracle.runtime_types import (
    NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS,
    RuntimeCftcPositioningLookupResult,
    RuntimeCryptoDerivativesLookupResult,
    RuntimeDigitalOracleUnavailableLookupResult,
    RuntimeMacroRatesLookupResult,
    RuntimeMarketSentimentLookupResult,
    RuntimeOptionsLookupResult,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFilingsLookupResult,
)
from app.extensions.signaldeck_digital_oracle.types import (
    DigitalOracleCftcPositioningReport,
    DigitalOracleCftcPositioningResult,
    DigitalOracleCftcPositioningRow,
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesOrderBookLevel,
    DigitalOracleCryptoDerivativesResult,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
    DigitalOracleMacroRatesResult,
    DigitalOracleMacroRatesSeries,
    DigitalOracleOptionContract,
    DigitalOracleOptionGreeks,
    DigitalOracleOptionsChain,
    DigitalOracleOptionsResult,
)
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)

_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS = (
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.crypto_derivatives.lookup",
    "signaldeck.digital_oracle.cftc_positioning.lookup",
    "signaldeck.digital_oracle.options.lookup",
)
_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_digital_oracle_prediction_markets_lookup",
    "signaldeck_digital_oracle_sec_filings_lookup",
    "signaldeck_digital_oracle_market_sentiment_lookup",
    "signaldeck_digital_oracle_macro_rates_lookup",
    "signaldeck_digital_oracle_crypto_derivatives_lookup",
    "signaldeck_digital_oracle_cftc_positioning_lookup",
    "signaldeck_digital_oracle_options_lookup",
)
_DIGITAL_ORACLE_TOOL_KEYS = set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS)
_FINANCE_PRICE_HISTORY_TOOL_KEYS = {
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
}
_FINANCE_INDICATOR_TOOL_KEYS = {"signaldeck.finance.indicators.lookup"}
_FINANCE_NEWS_TOOL_KEYS = {"signaldeck.finance.news.lookup"}
_REQUIRED_FINANCE_TOOL_KEYS = {
    "signaldeck.finance.market_data.quote_lookup",
    "signaldeck.finance.reports.lookup",
    *_FINANCE_INDICATOR_TOOL_KEYS,
    *_FINANCE_NEWS_TOOL_KEYS,
    *_FINANCE_PRICE_HISTORY_TOOL_KEYS,
}


def _valid_manifest_source() -> str:
    module = import_module("tests.test_workflow_package_manifest_parser")
    source_factory = cast(Callable[[], str], module.__dict__["_valid_package_manifest_source"])
    return source_factory().replace(
        "signaldeck.finance.market_data.quote_lookup",
        "signaldeck.finance.market_data.quote_lookup",
        1,
    )


def _api_tool_keys(client: TestClient) -> set[str]:
    response = client.get("/api/tools")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    return {str(item["key"]) for item in items}


def _warning_payload() -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="provider_unavailable",
        message="Fixture provider is unavailable.",
        details={"provider": "fixture", "operation": "contract_freeze"},
    )


def _assert_no_raw_provider_fields(payload: dict[str, object]) -> None:
    forbidden_keys = {
        "backendException",
        "headers",
        "rawPayload",
        "requestConfig",
        "secret",
        "secrets",
    }
    assert forbidden_keys.isdisjoint(payload)


def test_extension_tool_inventories_match_catalog_and_runtime() -> None:
    finance_server_declared_keys = {
        tool.key
        for tool in SERVER_DECLARED_TOOL_SPECS
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_server_declared_keys = {
        tool.key
        for tool in SERVER_DECLARED_TOOL_SPECS
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }
    core_server_declared_keys = {
        tool.key for tool in SERVER_DECLARED_TOOL_SPECS if tool.owner_extension_key is None
    }
    runtime_specs = get_default_runtime_tool_registry().list_specs()
    finance_runtime_keys = {
        tool.key
        for tool in runtime_specs
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_runtime_keys = {
        tool.key
        for tool in runtime_specs
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }
    core_runtime_keys = {tool.key for tool in runtime_specs if tool.owner_extension_key is None}
    finance_runtime_function_names = {
        tool.openai_function_name
        for tool in runtime_specs
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_runtime_function_names = {
        tool.openai_function_name
        for tool in runtime_specs
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }

    assert DIGITAL_ORACLE_RUNTIME_TOOL_KEYS == _EXPECTED_DIGITAL_ORACLE_TOOL_KEYS
    assert NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS == _EXPECTED_DIGITAL_ORACLE_TOOL_KEYS
    assert DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES == (_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES)
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_server_declared_keys
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_runtime_keys
    assert set(FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES) == finance_runtime_function_names
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= finance_server_declared_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= finance_runtime_keys
    assert _FINANCE_INDICATOR_TOOL_KEYS <= finance_server_declared_keys
    assert _FINANCE_INDICATOR_TOOL_KEYS <= finance_runtime_keys
    assert _FINANCE_NEWS_TOOL_KEYS <= finance_server_declared_keys
    assert _FINANCE_NEWS_TOOL_KEYS <= finance_runtime_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)
    assert _FINANCE_INDICATOR_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert _FINANCE_INDICATOR_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)
    assert _FINANCE_NEWS_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert _FINANCE_NEWS_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)
    assert set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS) == digital_oracle_server_declared_keys
    assert set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS) == digital_oracle_runtime_keys
    assert set(_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES) == (
        digital_oracle_runtime_function_names
    )
    assert core_server_declared_keys == set()
    assert core_runtime_keys == set()
    assert finance_server_declared_keys.isdisjoint(digital_oracle_server_declared_keys)


def test_digital_oracle_runtime_response_aliases_and_warnings_are_stable() -> None:
    warning = _warning_payload()
    as_of = datetime(2026, 6, 19, 14, 30, tzinfo=UTC)
    prediction_markets = RuntimePredictionMarketsLookupResult(
        query="election markets",
        events=[],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    sec_filings = RuntimeSecFilingsLookupResult(
        ticker="AAPL",
        filings=[],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    market_sentiment = RuntimeMarketSentimentLookupResult(
        indicator="fear_greed",
        as_of_date=date(2026, 6, 7),
        provider="fear_greed",
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    unavailable = RuntimeDigitalOracleUnavailableLookupResult(
        tool_key="signaldeck.digital_oracle.macro_rates.lookup",
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    macro_rates = map_macro_rates_result(
        DigitalOracleMacroRatesResult(
            query="fed funds",
            series=(
                DigitalOracleMacroRatesSeries(
                    provider="fred",
                    family="macro_indicators",
                    series_id="FEDFUNDS",
                    label="Effective Federal Funds Rate",
                    country="US",
                    currency="USD",
                    unit="percent",
                    date=date(2026, 6, 18),
                    value=Decimal("4.33"),
                    tenor=None,
                    source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    crypto_derivatives = map_crypto_derivatives_result(
        DigitalOracleCryptoDerivativesResult(
            assets=("BTC",),
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="CoinGeckoProvider",
                    symbol="BTC",
                    price=Decimal("64250.12"),
                    currency="USD",
                    as_of=as_of,
                ),
            ),
            global_metrics=(
                DigitalOracleCryptoDerivativesGlobalMetrics(
                    provider="CoinGeckoProvider",
                    symbol=None,
                    market_cap=Decimal("1260000000000"),
                    volume_24h=Decimal("42000000000"),
                    as_of=as_of,
                ),
            ),
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="DeribitProvider",
                    symbol="BTC",
                    expiry_date=date(2026, 9, 25),
                    instrument="BTC-PERPETUAL",
                    implied_volatility=Decimal("0.54"),
                    open_interest=Decimal("15123.5"),
                ),
            ),
            options=(
                DigitalOracleCryptoDerivativesOptionSummary(
                    provider="DeribitProvider",
                    symbol="BTC",
                    expiry_date=date(2026, 9, 25),
                    strike=Decimal("70000"),
                    option_type="call",
                    implied_volatility=Decimal("0.58"),
                    open_interest=Decimal("725.1"),
                ),
            ),
            order_books=(
                DigitalOracleCryptoDerivativesOrderBook(
                    provider="DeribitProvider",
                    symbol="BTC",
                    instrument="BTC-PERPETUAL",
                    bids=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64249.5"),
                            size=Decimal("12.4"),
                        ),
                    ),
                    asks=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64250.5"),
                            size=Decimal("10.8"),
                        ),
                    ),
                    depth_limit=1,
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    cftc_positioning = map_cftc_positioning_result(
        DigitalOracleCftcPositioningResult(
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="CftcCotProvider",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="Bitcoin",
                            contract_market_code="133741",
                            producer_long=Decimal("1200"),
                            producer_short=Decimal("900"),
                            swap_dealer_long=Decimal("450"),
                            swap_dealer_short=Decimal("510"),
                            managed_money_long=Decimal("7200"),
                            managed_money_short=Decimal("6800"),
                            open_interest=Decimal("18300"),
                        ),
                    ),
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    options = map_options_result(
        DigitalOracleOptionsResult(
            symbol="AAPL",
            chains=(
                DigitalOracleOptionsChain(
                    provider="YFinanceProvider",
                    symbol="AAPL",
                    expiry_date=date(2026, 7, 17),
                    calls=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717C00200000",
                            strike=Decimal("200"),
                            last_price=Decimal("6.25"),
                            bid=Decimal("6.2"),
                            ask=Decimal("6.3"),
                            volume=Decimal("1000"),
                            open_interest=Decimal("5000"),
                            greeks=DigitalOracleOptionGreeks(
                                delta=Decimal("0.61"),
                                gamma=Decimal("0.04"),
                                theta=Decimal("-0.03"),
                                vega=Decimal("0.18"),
                                rho=Decimal("0.05"),
                                implied_volatility=Decimal("0.32"),
                            ),
                        ),
                    ),
                    puts=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717P00200000",
                            strike=Decimal("200"),
                            last_price=Decimal("5.75"),
                            bid=Decimal("5.7"),
                            ask=Decimal("5.8"),
                            volume=Decimal("800"),
                            open_interest=Decimal("4200"),
                            greeks=DigitalOracleOptionGreeks(
                                delta=Decimal("-0.39"),
                                gamma=Decimal("0.04"),
                                theta=Decimal("-0.02"),
                                vega=Decimal("0.17"),
                                rho=Decimal("-0.04"),
                                implied_volatility=Decimal("0.31"),
                            ),
                        ),
                    ),
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)

    assert set(prediction_markets) == {"toolKey", "query", "events", "warnings"}
    assert prediction_markets["toolKey"] == "signaldeck.digital_oracle.prediction_markets.lookup"
    assert set(sec_filings) == {
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
    assert sec_filings["toolKey"] == "signaldeck.digital_oracle.sec_filings.lookup"
    assert set(market_sentiment) == {
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
    assert market_sentiment["toolKey"] == "signaldeck.digital_oracle.market_sentiment.lookup"
    assert set(unavailable) == {"toolKey", "warnings"}
    assert unavailable["toolKey"] == "signaldeck.digital_oracle.macro_rates.lookup"
    assert set(macro_rates) == {"toolKey", "query", "series", "warnings"}
    assert macro_rates["toolKey"] == "signaldeck.digital_oracle.macro_rates.lookup"
    assert cast(list[dict[str, object]], macro_rates["series"])[0] == {
        "provider": "fred",
        "family": "macro_indicators",
        "seriesId": "FEDFUNDS",
        "label": "Effective Federal Funds Rate",
        "country": "US",
        "currency": "USD",
        "unit": "percent",
        "date": "2026-06-18",
        "value": "4.33",
        "tenor": None,
        "sourceUrl": "https://fred.stlouisfed.org/series/FEDFUNDS",
    }
    assert set(crypto_derivatives) == {
        "toolKey",
        "assets",
        "spot",
        "globalMetrics",
        "termStructure",
        "options",
        "orderBooks",
        "warnings",
    }
    assert crypto_derivatives["toolKey"] == ("signaldeck.digital_oracle.crypto_derivatives.lookup")
    assert cast(list[dict[str, object]], crypto_derivatives["spot"])[0]["asOf"] == (
        "2026-06-19T14:30:00Z"
    )
    assert set(cftc_positioning) == {"toolKey", "reports", "warnings"}
    assert cftc_positioning["toolKey"] == ("signaldeck.digital_oracle.cftc_positioning.lookup")
    cftc_report = cast(list[dict[str, object]], cftc_positioning["reports"])[0]
    assert set(cftc_report) == {"provider", "reportType", "reportDate", "rows"}
    assert cast(list[dict[str, object]], cftc_report["rows"])[0]["managedMoneyLong"] == "7200"
    assert set(options) == {"toolKey", "symbol", "chains", "warnings"}
    assert options["toolKey"] == "signaldeck.digital_oracle.options.lookup"
    options_chain = cast(list[dict[str, object]], options["chains"])[0]
    assert set(options_chain) == {"provider", "symbol", "expiryDate", "calls", "puts"}
    call_contract = cast(list[dict[str, object]], options_chain["calls"])[0]
    assert cast(dict[str, object], call_contract["greeks"])["impliedVolatility"] == "0.32"
    for payload in (
        prediction_markets,
        sec_filings,
        market_sentiment,
        unavailable,
        macro_rates,
        crypto_derivatives,
        cftc_positioning,
        options,
    ):
        _assert_no_raw_provider_fields(payload)
        assert payload["warnings"] == [
            {
                "code": "provider_unavailable",
                "message": "Fixture provider is unavailable.",
                "details": {"provider": "fixture", "operation": "contract_freeze"},
            }
        ]


@pytest.mark.parametrize(
    ("schema", "payload"),
    (
        (
            RuntimeMacroRatesLookupResult,
            {
                "toolKey": "signaldeck.digital_oracle.macro_rates.lookup",
                "query": "fed funds",
                "series": [],
                "warnings": [],
            },
        ),
        (
            RuntimeCryptoDerivativesLookupResult,
            {
                "toolKey": "signaldeck.digital_oracle.crypto_derivatives.lookup",
                "symbol": "BTC",
                "spot": None,
                "globalMetrics": None,
                "termStructure": [],
                "options": [],
                "orderBook": None,
                "warnings": [],
            },
        ),
        (
            RuntimeCftcPositioningLookupResult,
            {
                "toolKey": "signaldeck.digital_oracle.cftc_positioning.lookup",
                "reports": [],
                "warnings": [],
            },
        ),
        (
            RuntimeOptionsLookupResult,
            {
                "toolKey": "signaldeck.digital_oracle.options.lookup",
                "symbol": "AAPL",
                "chains": [],
                "warnings": [],
            },
        ),
    ),
)
def test_digital_oracle_runtime_response_aliases_reject_raw_and_unknown_fields(
    schema: (
        type[RuntimeMacroRatesLookupResult]
        | type[RuntimeCryptoDerivativesLookupResult]
        | type[RuntimeCftcPositioningLookupResult]
        | type[RuntimeOptionsLookupResult]
    ),
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "rawPayload": {"provider": "secret"}})

    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "requestConfig": {"headers": {}}})

    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "unexpectedField": "denied"})


def test_default_tool_catalog_rejects_duplicate_and_unknown_keys() -> None:
    catalog = get_default_tool_catalog()

    with pytest.raises(ToolCatalogValidationError) as exc_info:
        _ = catalog.resolve_tool_keys(
            [
                "signaldeck.finance.reports.lookup",
                "signaldeck.finance.reports.lookup",
                "signaldeck.unknown.lookup",
            ]
        )

    assert exc_info.value.details == [
        {
            "field": "toolKeys.1",
            "issue": "Duplicate tool key 'signaldeck.finance.reports.lookup' is not allowed",
        },
        {
            "field": "toolKeys.2",
            "issue": "Unknown server-declared tool 'signaldeck.unknown.lookup'",
        },
    ]


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert {frozenset(item) for item in items} == {frozenset({"key", "displayName", "description"})}
    assert _REQUIRED_FINANCE_TOOL_KEYS <= set(tools_by_key)
    assert _DIGITAL_ORACLE_TOOL_KEYS <= set(tools_by_key)
    quote_tool = tools_by_key["signaldeck.finance.market_data.quote_lookup"]
    history_tool = tools_by_key["signaldeck.finance.market_data.history_lookup"]
    ohlcv_tool = tools_by_key["signaldeck.finance.market_data.ohlcv_lookup"]
    indicator_tool = tools_by_key["signaldeck.finance.indicators.lookup"]
    news_tool = tools_by_key["signaldeck.finance.news.lookup"]
    report_lookup_tool = tools_by_key["signaldeck.finance.reports.lookup"]
    prediction_markets_tool = tools_by_key["signaldeck.digital_oracle.prediction_markets.lookup"]
    sec_filings_tool = tools_by_key["signaldeck.digital_oracle.sec_filings.lookup"]
    market_sentiment_tool = tools_by_key["signaldeck.digital_oracle.market_sentiment.lookup"]
    macro_rates_tool = tools_by_key["signaldeck.digital_oracle.macro_rates.lookup"]
    crypto_derivatives_tool = tools_by_key["signaldeck.digital_oracle.crypto_derivatives.lookup"]
    cftc_positioning_tool = tools_by_key["signaldeck.digital_oracle.cftc_positioning.lookup"]
    options_tool = tools_by_key["signaldeck.digital_oracle.options.lookup"]
    assert quote_tool == {
        "key": "signaldeck.finance.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
    }
    assert history_tool == {
        "key": "signaldeck.finance.market_data.history_lookup",
        "displayName": "Market Data History Lookup",
        "description": "Read trusted historical market series from server-owned integrations.",
    }
    assert ohlcv_tool == {
        "key": "signaldeck.finance.market_data.ohlcv_lookup",
        "displayName": "OHLCV Lookup",
        "description": "Read server-owned OHLCV market data for supported symbols and ranges.",
    }
    assert indicator_tool == {
        "key": "signaldeck.finance.indicators.lookup",
        "displayName": "Indicators Lookup",
        "description": (
            "Read server-owned technical indicators, including moving averages, "
            "MACD, RSI, Bollinger bands, ATR, and VWMA."
        ),
    }
    assert news_tool == {
        "key": "signaldeck.finance.news.lookup",
        "displayName": "News Lookup",
        "description": (
            "Read Alpha Vantage/Yahoo-backed symbol, market, and global finance news "
            "with structured warnings for provider, empty, truncated, or bounded coverage."
        ),
    }
    assert report_lookup_tool == {
        "key": "signaldeck.finance.reports.lookup",
        "displayName": "Report Lookup",
        "description": "Read persisted SignalDeck reports through server-owned report lookups.",
    }
    assert prediction_markets_tool == {
        "key": "signaldeck.digital_oracle.prediction_markets.lookup",
        "displayName": "Prediction Markets Lookup",
        "description": (
            "Read normalized prediction-market signals from Digital Oracle market "
            "lookups, including optional orderbook depth, with structured warnings "
            "for partial coverage."
        ),
    }
    assert sec_filings_tool == {
        "key": "signaldeck.digital_oracle.sec_filings.lookup",
        "displayName": "SEC Filings Lookup",
        "description": (
            "Read normalized SEC filing summaries, EDGAR search hits, and Form 4 "
            "ownership summaries with structured warnings for partial coverage."
        ),
    }
    assert market_sentiment_tool == {
        "key": "signaldeck.digital_oracle.market_sentiment.lookup",
        "displayName": "Market Sentiment Lookup",
        "description": (
            "Read normalized market sentiment signals from Digital Oracle sentiment "
            "lookups with structured warnings for partial coverage."
        ),
    }
    assert macro_rates_tool == {
        "key": "signaldeck.digital_oracle.macro_rates.lookup",
        "displayName": "Macro Rates Lookup",
        "description": (
            "Read normalized macro, yield, policy-rate, and Fed-implied rates "
            "series with structured warnings for partial provider coverage."
        ),
    }
    assert crypto_derivatives_tool == {
        "key": "signaldeck.digital_oracle.crypto_derivatives.lookup",
        "displayName": "Crypto Derivatives Lookup",
        "description": (
            "Read normalized CoinGecko spot/global-market and Deribit futures, "
            "options, and orderbook data with structured warnings for partial coverage."
        ),
    }
    assert cftc_positioning_tool == {
        "key": "signaldeck.digital_oracle.cftc_positioning.lookup",
        "displayName": "CFTC Positioning Lookup",
        "description": (
            "Read normalized CFTC Commitment of Traders positioning reports with "
            "structured warnings for missing, stale, or malformed provider data."
        ),
    }
    assert options_tool == {
        "key": "signaldeck.digital_oracle.options.lookup",
        "displayName": "Options Lookup",
        "description": (
            "Read normalized Yahoo option-chain calls and puts through an optional "
            "yfinance-backed provider with structured warnings for unavailable coverage."
        ),
    }


def test_installed_extension_tools_are_static_in_catalog_and_runtime(
    client: TestClient,
) -> None:
    api_tool_keys = _api_tool_keys(client)
    catalog_keys = {tool.key for tool in get_default_tool_catalog().list_registered_tools()}
    runtime_registry = get_default_runtime_tool_registry()
    runtime_keys = {spec.key for spec in runtime_registry.list_specs()}
    descriptor_keys = {
        descriptor.tool_key
        for descriptor in runtime_registry.get_execution_descriptors(
            _DIGITAL_ORACLE_TOOL_KEYS | _REQUIRED_FINANCE_TOOL_KEYS
        )
    }

    assert _DIGITAL_ORACLE_TOOL_KEYS <= api_tool_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= api_tool_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= catalog_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= catalog_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= runtime_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= runtime_keys
    assert descriptor_keys == _DIGITAL_ORACLE_TOOL_KEYS | _REQUIRED_FINANCE_TOOL_KEYS


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    paths = cast(dict[str, object], openapi["paths"])
    schemas = cast(
        dict[str, dict[str, object]],
        cast(dict[str, object], openapi["components"])["schemas"],
    )
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}

    get_operation = cast(dict[str, object], tools_path["get"])
    get_responses = cast(dict[str, object], get_operation["responses"])
    ok_response = cast(dict[str, object], get_responses["200"])
    ok_content = cast(dict[str, object], ok_response["content"])
    ok_json = cast(dict[str, object], ok_content["application/json"])
    assert ok_json["schema"] == {"$ref": "#/components/schemas/ToolCatalogListRead"}
    assert set(cast(dict[str, object], schemas["ToolCatalogItemRead"]["properties"])) == {
        "key",
        "displayName",
        "description",
    }
    list_properties = cast(dict[str, object], schemas["ToolCatalogListRead"]["properties"])
    assert set(list_properties) == {"items"}
    assert cast(list[str], schemas["ToolCatalogListRead"]["required"]) == ["items"]


def test_tool_catalog_static_extension_tools_and_validation_stays_artifact_only(
    client: TestClient,
) -> None:
    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200, tools_response.json()
    tools_body = cast(dict[str, object], tools_response.json())
    visible_items = cast(list[dict[str, object]], tools_body["items"])
    visible_keys = {str(item["key"]) for item in visible_items}
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) <= visible_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= visible_keys
    assert _FINANCE_NEWS_TOOL_KEYS <= visible_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= visible_keys

    catalog_keys = {tool.key for tool in get_default_tool_catalog().list_registered_tools()}
    runtime_keys = {spec.key for spec in get_default_runtime_tool_registry().list_specs()}

    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= catalog_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= runtime_keys
    assert _FINANCE_NEWS_TOOL_KEYS <= catalog_keys
    assert _FINANCE_NEWS_TOOL_KEYS <= runtime_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= catalog_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= runtime_keys

    manifest_source = _valid_manifest_source()
    validation_response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": manifest_source},
    )
    assert validation_response.status_code == 200, validation_response.json()
    body = cast(dict[str, object], validation_response.json())
    metadata = cast(dict[str, object], body["metadata"])
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert diagnostics == []
    assert metadata["key"] == "tradingagents_research"
    assert body["packageDefinition"] is not None
    assert body["compiledPlan"] is not None

    created = client.post("/api/workflow-packages", json={"manifestSource": manifest_source})
    assert created.status_code == 201, created.json()
    preflight = client.post(
        f"/api/workflow-packages/{created.json()['id']}/preflight",
        json={"workflowKey": None, "parameters": {"ticker": "AAPL"}},
    )
    assert preflight.status_code == 200, preflight.json()
