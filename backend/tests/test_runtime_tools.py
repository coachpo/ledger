from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import TracebackType
from typing import cast, override

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import (
    MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    POSITION_LOOKUP_TOOL_SPEC,
    REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    REPORT_LOOKUP_TOOL_SPEC,
    REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    REPORT_MEMORY_WRITE_TOOL_SPEC,
    RUNTIME_TOOL_SPECS,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolRegistry,
    RuntimeToolSpec,
    get_default_runtime_tool_registry,
)
from app.agents.runtime_tools.market_data import (
    parse_history_lookup_arguments,
    parse_quote_lookup_arguments,
)
from app.agents.runtime_tools.positions import parse_position_lookup_arguments
from app.agents.runtime_tools.reports import (
    parse_report_lookup_arguments,
    parse_report_memory_write_arguments,
)
from app.agents.runtime_tools.types import (
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS,
    NEWS_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_TOOL_KEY,
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
    RuntimeReportMemoryWriteResult,
    RuntimeToolWarning,
)
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.models.capability import Capability
from app.models.report import Report
from app.schemas.market_data import MarketHistoryPointRead, MarketHistorySeriesRead, MarketQuoteRead
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.services.capability_service import (
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_TOOL_KEY,
    REPORT_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    RuntimeToolGrantError,
)
from app.services.market_data_service import MarketDataService
from app.services.position_service import PositionService
from app.services.quote_provider import (
    ProviderFinancialStatement,
    ProviderFinancialStatementLine,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderNewsItem,
    ProviderNewsResult,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProvider,
    QuoteProviderError,
    QuoteProviderMissingKeyError,
    QuoteProviderTimeoutError,
)
from app.services.report_service import ReportService

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


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


def _runtime_context(
    *,
    capability_references: Sequence[dict[str, object]] | None = None,
    fail_on_session: bool = False,
    session_factory_override: sessionmaker[Session] | None = None,
    quote_provider: QuoteProvider | None = None,
    run_id: int | None = None,
    agent_key: str | None = None,
    agent_version: int | None = None,
    agent_name: str | None = None,
    workflow_key: str | None = None,
    workflow_version: int | None = None,
    step_id: str | None = None,
    slot: str | None = None,
    trace_id: str | None = None,
) -> RuntimeToolContext:
    selected_session_factory = session_factory_override or (
        _failing_session_factory if fail_on_session else _session_factory
    )
    return RuntimeToolContext(
        session_factory=cast(sessionmaker[Session], selected_session_factory),
        capability_references=list(
            capability_references
            or [
                {
                    "capabilityKey": "runtime_tool_test_capability",
                    "capabilityVersion": 1,
                }
            ]
        ),
        quote_provider=quote_provider,
        run_id=run_id,
        agent_key=agent_key,
        agent_version=agent_version,
        agent_name=agent_name,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        step_id=step_id,
        slot=slot,
        trace_id=trace_id,
    )


def _seed_runtime_tool_capability(
    session_factory: sessionmaker[Session],
    *,
    tools: Sequence[str],
    key: str = "runtime_tool_test_capability",
) -> None:
    with session_factory() as session:
        session.add(
            Capability(
                key=key,
                version=1,
                status="published",
                name=f"{key} v1",
                description="Runtime tool test capability.",
                tool_grants=[{"tool": tool} for tool in tools],
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
    key: str = "ledger.test.lookup",
    openai_function_name: str = "ledger_test_lookup",
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


def _reports_write_arguments_json(
    analysis_overrides: dict[str, object] | None = None,
) -> str:
    analysis: dict[str, object] = {
        "ticker": " nvda ",
        "portfolioSlug": " core_us ",
        "horizonDays": 30,
        "confidence": " high ",
        "decisionSummary": " Durable earnings setup. ",
        "decision": {
            "action": "buy",
            "rationale": "Accelerating demand supports upside.",
            "riskSummary": "Position sizing should respect valuation risk.",
            "executionPlan": "Scale in over two sessions.",
        },
    }
    if analysis_overrides is not None:
        analysis.update(analysis_overrides)
    return json.dumps({"analysis": analysis})


def _reports_write_runtime_context(
    session_factory: sessionmaker[Session],
    *,
    capability_key: str = "runtime_tool_test_capability",
) -> RuntimeToolContext:
    return _runtime_context(
        capability_references=[{"capabilityKey": capability_key, "capabilityVersion": 1}],
        session_factory_override=session_factory,
        run_id=4242,
        agent_key="portfolio_manager",
        agent_version=3,
        agent_name="Portfolio Manager",
        workflow_key="tradingagents_daily_review",
        workflow_version=5,
        step_id="portfolio_decision",
        slot="decision",
        trace_id="trace-runtime-tools",
    )


def _assert_strict_openai_tool_schema(tool: dict[str, object]) -> None:
    assert "displayName" not in tool
    assert "display_name" not in tool
    assert tool["type"] == "function"
    assert tool["strict"] is True
    parameters = cast(dict[str, object], tool["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == list(properties)


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


def _position_read() -> PositionRead:
    return PositionRead.model_validate(
        {
            "id": 11,
            "portfolio_id": 5,
            "symbol": "NVDA",
            "name": "NVIDIA Corporation",
            "quantity": Decimal("12.00000000"),
            "average_cost": Decimal("101.50000000"),
            "currency": "USD",
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
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del symbols, query, start_date, end_date, limit
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
            tuple[list[str], str | None, datetime | None, datetime | None, int]
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
                )
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
                )
            ],
        )

    @override
    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, start_date, end_date, limit))
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


def test_native_runtime_financial_tool_result_keys_are_ledger_prefixed_and_contract_only() -> None:
    assert NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS == (
        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
        MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
        MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
        INDICATORS_LOOKUP_TOOL_KEY,
        FUNDAMENTALS_LOOKUP_TOOL_KEY,
        NEWS_LOOKUP_TOOL_KEY,
        INSIDER_DATA_LOOKUP_TOOL_KEY,
        REPORT_MEMORY_WRITE_TOOL_KEY,
    )
    assert all(tool_key.startswith("ledger.") for tool_key in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS)
    assert {spec.key for spec in RUNTIME_TOOL_SPECS} == {
        MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
        MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
        REPORT_LOOKUP_TOOL_KEY,
        REPORT_MEMORY_WRITE_TOOL_KEY,
        POSITION_LOOKUP_TOOL_KEY,
    }

    server_declared_keys = {spec.key for spec in SERVER_DECLARED_TOOL_SPECS}
    assert MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY in server_declared_keys
    assert MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY in server_declared_keys
    assert REPORT_MEMORY_WRITE_TOOL_KEY in server_declared_keys

    with pytest.raises(ValidationError, match="Native runtime tool keys must start with ledger"):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "external.market_data.quote_lookup"})
    with pytest.raises(ValidationError, match="not registered as a financial tool result"):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "ledger.unregistered.lookup"})


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
    assert quote_payload["toolKey"] == "ledger.market_data.quote_lookup"
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
    assert history_payload["toolKey"] == "ledger.market_data.history_lookup"
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
    assert ohlcv_payload["toolKey"] == "ledger.market_data.ohlcv_lookup"
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
    assert indicator_payload["toolKey"] == "ledger.indicators.lookup"
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
    assert fundamentals_payload["toolKey"] == "ledger.fundamentals.lookup"
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
    assert news_payload["toolKey"] == "ledger.news.lookup"
    assert news_payload["items"][0]["publishedAt"] == "2026-01-02T03:04:05Z"

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
    assert insider_payload["toolKey"] == "ledger.insider_data.lookup"
    assert insider_payload["transactions"][0]["insiderName"] == "Ada Lovelace"
    assert insider_payload["transactions"][0]["transactionDate"] == "2026-01-02T03:04:05Z"
    assert insider_payload["transactions"][0]["filedAt"] == "2026-01-02T03:04:05Z"

    memory_payload = RuntimeReportMemoryWriteResult(
        report_id=7,
        report_slug="nvda_agent_memory_2026_01_02",
        report_name="NVDA Agent Memory 2026-01-02",
        created_at=_NOW,
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(memory_payload)
    assert memory_payload == {
        "toolKey": "ledger.reports.write",
        "reportId": 7,
        "reportSlug": "nvda_agent_memory_2026_01_02",
        "reportName": "NVDA Agent Memory 2026-01-02",
        "action": "created",
        "createdAt": "2026-01-02T03:04:05Z",
        "warnings": [],
    }


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
    assert payload["toolKey"] == FUNDAMENTALS_LOOKUP_TOOL_KEY
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
        (["NVDA"], "earnings", start_date.astimezone(UTC), end_date.astimezone(UTC), 3)
    ]
    assert payload["toolKey"] == NEWS_LOOKUP_TOOL_KEY
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
            "details": {"limit": "2"},
        }
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
    assert payload["toolKey"] == INSIDER_DATA_LOOKUP_TOOL_KEY
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
            sma_windows=(2,),
            row_limit=3,
        )

    assert provider.ohlcv_calls == [("NVDA", start_date, current_date, "1d")]
    payload = result.model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == "ledger.indicators.lookup"
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
    assert rows[0]["values"] == [
        {"name": "close", "value": "119.75", "nullReason": None},
        {"name": "sma_2", "value": None, "nullReason": "warmup"},
    ]
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
            sma_windows=(5,),
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
            )
        with pytest.raises(QuoteProviderError, match="endDate cannot be after currentDate"):
            _ = service.get_indicator_snapshot(
                "nvda",
                current_date=datetime(2026, 1, 2, tzinfo=UTC),
                start_date=datetime(2026, 1, 1, tzinfo=UTC),
                end_date=datetime(2026, 1, 3, tzinfo=UTC),
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
                sma_windows=(2,),
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


def test_runtime_tool_spec_is_frozen_and_separates_display_metadata_from_execution_fields() -> None:
    assert REPORT_LOOKUP_TOOL_SPEC.key == REPORT_LOOKUP_TOOL_KEY
    assert REPORT_LOOKUP_TOOL_SPEC.openai_function_name == REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    assert REPORT_LOOKUP_TOOL_SPEC.display_name == "Report Lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.description

    assert REPORT_MEMORY_WRITE_TOOL_SPEC.key == REPORT_MEMORY_WRITE_TOOL_KEY
    assert (
        REPORT_MEMORY_WRITE_TOOL_SPEC.openai_function_name
        == REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME
    )
    assert REPORT_MEMORY_WRITE_TOOL_SPEC.display_name == "Report Memory Write"
    assert REPORT_MEMORY_WRITE_TOOL_SPEC.key != REPORT_MEMORY_WRITE_TOOL_SPEC.openai_function_name

    assert POSITION_LOOKUP_TOOL_SPEC.key == POSITION_LOOKUP_TOOL_KEY
    assert POSITION_LOOKUP_TOOL_SPEC.openai_function_name == POSITION_LOOKUP_OPENAI_FUNCTION_NAME
    assert POSITION_LOOKUP_TOOL_SPEC.display_name == "Position Lookup"
    assert POSITION_LOOKUP_TOOL_SPEC.key != POSITION_LOOKUP_TOOL_SPEC.openai_function_name
    assert POSITION_LOOKUP_TOOL_SPEC.display_name != POSITION_LOOKUP_TOOL_SPEC.openai_function_name
    assert POSITION_LOOKUP_TOOL_SPEC.display_name != POSITION_LOOKUP_TOOL_SPEC.description

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
        setattr(REPORT_LOOKUP_TOOL_SPEC, field_name, "ledger.changed")


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
    assert context.quote_provider is quote_provider
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
            [spec, replace(spec, openai_function_name="ledger_test_lookup_alt")]
        )

    with pytest.raises(ValueError, match="Duplicate runtime tool OpenAI function name"):
        _ = RuntimeToolRegistry([spec, replace(spec, key="ledger.test.lookup.alt")])


def test_runtime_tool_registry_returns_granted_strict_definitions_in_sort_order() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC, REPORT_LOOKUP_TOOL_SPEC])

    tools = registry.get_openai_tools({POSITION_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in tools] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)
    assert tools[0]["description"] == (
        "Read persisted Ledger reports by ticker, tag, review type, portfolio slug, source, "
        "limit, and offset."
    )
    assert tools[1]["description"] == (
        "Read persisted Ledger positions for a portfolio slug, optionally filtered by symbol, "
        "limit, and offset."
    )

    report_parameters = cast(dict[str, object], tools[0]["parameters"])
    report_properties = cast(dict[str, object], report_parameters["properties"])
    assert report_parameters["required"] == [
        "ticker",
        "tag",
        "reviewType",
        "portfolioSlug",
        "source",
        "limit",
        "offset",
    ]
    source_property = cast(dict[str, object], report_properties["source"])
    assert source_property["enum"] == [
        "compiled",
        "uploaded",
        "external",
        None,
    ]
    position_parameters = cast(dict[str, object], tools[1]["parameters"])
    position_properties = cast(dict[str, object], position_parameters["properties"])
    assert position_parameters["required"] == ["portfolioSlug", "symbol", "limit", "offset"]
    position_limit_property = cast(dict[str, object], position_properties["limit"])
    assert position_limit_property["maximum"] == 200

    position_only_tools = registry.get_openai_tools({POSITION_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in position_only_tools] == [POSITION_LOOKUP_OPENAI_FUNCTION_NAME]


def test_default_runtime_tool_registry_exposes_financial_runtime_specs() -> None:
    registry = get_default_runtime_tool_registry()

    spec_by_key = {spec.key: spec for spec in registry.list_specs()}
    assert spec_by_key[REPORT_MEMORY_WRITE_TOOL_KEY].openai_function_name == (
        REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME
    )
    tools = registry.get_openai_tools(
        {
            REPORT_MEMORY_WRITE_TOOL_KEY,
            MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
        }
    )
    assert [tool["name"] for tool in tools] == [
        REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)


def test_financial_runtime_tool_exposure_follows_quote_history_and_report_write_grants() -> None:
    registry = get_default_runtime_tool_registry()

    quote_only = registry.get_openai_tools({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY})
    quote_history = registry.get_openai_tools(
        {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY}
    )
    all_native_financial = registry.get_openai_tools(
        {
            MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
            REPORT_MEMORY_WRITE_TOOL_KEY,
        }
    )

    assert [tool["name"] for tool in quote_only] == [MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME]
    assert [tool["name"] for tool in quote_history] == [
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert [tool["name"] for tool in all_native_financial] == [
        REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME not in {
        cast(str, tool["name"]) for tool in quote_history
    }


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
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC, REPORT_LOOKUP_TOOL_SPEC])

    assert registry.get_guidance({POSITION_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}) == (
        "When you need persisted Ledger report context, call the ledger_reports_lookup tool "
        "instead of inventing report content.\n\n"
        "When you need persisted Ledger position context, call the ledger_positions_lookup tool "
        "instead of inventing portfolio holdings."
    )
    assert registry.get_guidance(set()) == ""


def test_runtime_tool_registry_rejects_unknown_and_ungranted_names_before_parsing() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as unknown_error:
        _ = registry.dispatch(
            name="ledger_unknown_lookup",
            arguments_json='{"portfolioSlug":"reference"}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert unknown_error.value.code == "agent_tool_call_unsupported"
    assert (
        unknown_error.value.message
        == "Agent requested unsupported server tool 'ledger_unknown_lookup'."
    )

    with pytest.raises(RuntimeToolError) as ungranted_error:
        _ = registry.dispatch(
            name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert ungranted_error.value.code == POSITION_LOOKUP_ACCESS_DENIED_CODE
    assert ungranted_error.value.message == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE


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


def test_reports_write_runtime_tool_registry_denies_ungranted_before_parsing() -> None:
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )

    assert exc_info.value.code == REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE
    assert exc_info.value.message == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE


@pytest.mark.parametrize(
    "field_name",
    [
        "runId",
        "agentKey",
        "agentVersion",
        "agentName",
        "workflowKey",
        "workflowVersion",
        "stepId",
        "slot",
        "traceId",
        "resolvedStatus",
        "resolvedAt",
        "rawReturn",
        "benchmarkReturn",
        "alpha",
        "reflections",
        "returns",
    ],
)
def test_reports_write_runtime_tool_parser_rejects_spoofed_trusted_fields(
    field_name: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_report_memory_write_arguments(
            _reports_write_arguments_json({field_name: "spoofed"})
        )

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == "ledger_reports_write arguments failed validation."
    assert exc_info.value.details[0]["field"] == f"analysis.{field_name}"


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        ("{", "OpenAI response requested ledger_reports_write with invalid JSON arguments."),
        ("[]", "ledger_reports_write arguments must be a JSON object."),
        (
            '{"runId":42,"analysis":{}}',
            "ledger_reports_write arguments contained unsupported fields: runId",
        ),
    ],
)
def test_reports_write_runtime_tool_parser_preserves_boundary_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_report_memory_write_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message


def test_reports_write_runtime_tool_service_denies_missing_write_grant(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_reports_write_without_service_grant"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[REPORT_LOOKUP_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
            arguments_json=_reports_write_arguments_json(),
            granted_tool_keys={REPORT_MEMORY_WRITE_TOOL_KEY},
            context=_reports_write_runtime_context(
                session_factory,
                capability_key=capability_key,
            ),
        )

    with session_factory() as session:
        reports = list(session.scalars(select(Report)))
    assert exc_info.value.code == REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE
    assert exc_info.value.message == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert reports == []


def test_reports_write_runtime_tool_creates_pending_memory_from_context_and_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_tool_capability(
        session_factory,
        tools=[REPORT_MEMORY_WRITE_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])
    context = _reports_write_runtime_context(session_factory)

    first_payload = registry.dispatch(
        name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        arguments_json=_reports_write_arguments_json(),
        granted_tool_keys={REPORT_MEMORY_WRITE_TOOL_KEY},
        context=context,
    )
    second_payload = registry.dispatch(
        name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        arguments_json=_reports_write_arguments_json(),
        granted_tool_keys={REPORT_MEMORY_WRITE_TOOL_KEY},
        context=context,
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(first_payload)
    assert first_payload == second_payload
    assert first_payload["toolKey"] == REPORT_MEMORY_WRITE_TOOL_KEY
    assert first_payload["action"] == "created"

    with session_factory() as session:
        reports = list(session.scalars(select(Report)))

    assert len(reports) == 1
    report = reports[0]
    analysis = cast(dict[str, object], report.metadata_["analysis"])
    decision = cast(dict[str, object], analysis["decision"])
    assert first_payload["reportId"] == report.id
    assert first_payload["reportSlug"] == report.slug
    assert first_payload["reportName"] == report.name
    assert report.source == "external"
    assert analysis["reviewType"] == "agent_memory"
    assert analysis["versionGroup"] == "agent_memory/v1"
    assert analysis["ticker"] == "NVDA"
    assert analysis["portfolioSlug"] == "core_us"
    assert analysis["horizonDays"] == 30
    assert analysis["confidence"] == "high"
    assert analysis["decisionSummary"] == "Durable earnings setup."
    assert analysis["runId"] == 4242
    assert analysis["agentKey"] == "portfolio_manager"
    assert analysis["agentVersion"] == 3
    assert analysis["agentName"] == "Portfolio Manager"
    assert analysis["workflowKey"] == "tradingagents_daily_review"
    assert analysis["workflowVersion"] == 5
    assert analysis["stepId"] == "portfolio_decision"
    assert analysis["slot"] == "decision"
    assert analysis["traceId"] == "trace-runtime-tools"
    assert analysis["resolvedStatus"] == "pending"
    assert analysis["reflections"] == []
    assert "resolvedAt" not in analysis
    assert "rawReturn" not in analysis
    assert "alpha" not in analysis
    assert decision["action"] == "buy"


def test_market_data_quote_lookup_service_denies_missing_capability_reference_grant(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_market_data_quote_without_grant"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"baseCurrency":null}',
            granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            context=_runtime_context(
                capability_references=[{"capabilityKey": capability_key, "capabilityVersion": 1}],
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
    capability_key = "runtime_market_data_history_without_grant"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider()

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"range":"3mo","pointLimit":2}',
            granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            context=_runtime_context(
                capability_references=[{"capabilityKey": capability_key, "capabilityVersion": 1}],
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
            "OpenAI response requested ledger_reports_lookup with invalid JSON arguments.",
        ),
        ("[]", "ledger_reports_lookup arguments must be a JSON object."),
        (
            '{"unsupported":true}',
            "ledger_reports_lookup arguments contained unsupported fields: unsupported",
        ),
        (
            '{"source":"manual"}',
            "ledger_reports_lookup source must be one of compiled, uploaded, or external.",
        ),
        ('{"ticker":123}', "ledger_reports_lookup string arguments must be strings."),
        ('{"limit":51}', "ledger_reports_lookup limit must be at most 50."),
        ('{"offset":-1}', "ledger_reports_lookup offset must be at least 0."),
    ],
)
def test_report_runtime_tool_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
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
            "OpenAI response requested ledger_positions_lookup with invalid JSON arguments.",
        ),
        ("[]", "ledger_positions_lookup arguments must be a JSON object."),
        (
            '{"portfolioSlug":"reference","unsupported":true}',
            "ledger_positions_lookup arguments contained unsupported fields: unsupported",
        ),
        ("{}", "ledger_positions_lookup portfolioSlug is required."),
        ('{"portfolioSlug":123}', "ledger_positions_lookup portfolioSlug must be a string."),
        (
            '{"portfolioSlug":"reference","limit":"1"}',
            "ledger_positions_lookup limit must be an integer.",
        ),
        (
            '{"portfolioSlug":"reference","limit":201}',
            "ledger_positions_lookup limit must be at most 200.",
        ),
        (
            '{"portfolioSlug":"reference","offset":-1}',
            "ledger_positions_lookup offset must be at least 0.",
        ),
    ],
)
def test_position_runtime_tool_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_position_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested ledger_market_data_quote_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "ledger_market_data_quote_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            "ledger_market_data_quote_lookup arguments contained unsupported fields: unsupported",
        ),
        ("{}", "ledger_market_data_quote_lookup symbols is required."),
        (
            '{"symbols":"NVDA"}',
            "ledger_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[123]}',
            "ledger_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[""]}',
            "ledger_market_data_quote_lookup symbols must not contain empty values.",
        ),
        (
            '{"symbols":["NVDA"],"baseCurrency":"US"}',
            "ledger_market_data_quote_lookup baseCurrency must be a 3-letter ISO code.",
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
            "OpenAI response requested ledger_market_data_history_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "ledger_market_data_history_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            "ledger_market_data_history_lookup arguments contained unsupported fields: unsupported",
        ),
        ("{}", "ledger_market_data_history_lookup symbols is required."),
        (
            '{"symbols":["NVDA"],"range":"10y"}',
            "ledger_market_data_history_lookup range must be one of 1mo, 3mo, ytd, 1y, or max.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":"2"}',
            "ledger_market_data_history_lookup pointLimit must be an integer.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":251}',
            "ledger_market_data_history_lookup pointLimit must be at most 250.",
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


def test_registry_dispatch_rejects_invalid_arguments_before_service_execution() -> None:
    registry = RuntimeToolRegistry(
        [
            REPORT_LOOKUP_TOOL_SPEC,
            POSITION_LOOKUP_TOOL_SPEC,
            MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
            MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
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
    assert report_error.value.message == "ledger_reports_lookup limit must be at most 50."

    with pytest.raises(RuntimeToolError) as position_error:
        _ = registry.dispatch(
            name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"portfolioSlug":"reference","limit":201}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert position_error.value.message == "ledger_positions_lookup limit must be at most 200."

    with pytest.raises(RuntimeToolError) as quote_error:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"unsupported":true}',
            granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert quote_error.value.message == (
        "ledger_market_data_quote_lookup arguments contained unsupported fields: unsupported"
    )

    with pytest.raises(RuntimeToolError) as history_error:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"pointLimit":251}',
            granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert history_error.value.message == (
        "ledger_market_data_history_lookup pointLimit must be at most 250."
    )


def test_report_runtime_tool_dispatches_to_report_service_with_defaults_and_output_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_reports(
        self: ReportService,
        *,
        capability_references: Sequence[dict[str, object]],
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        del self
        captured_calls.append(
            {
                "capability_references": capability_references,
                "ticker": ticker,
                "tag": tag,
                "review_type": review_type,
                "portfolio_slug": portfolio_slug,
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
                    "capabilityKey": "runtime_tool_test_capability",
                    "capabilityVersion": 1,
                }
            ],
            "ticker": "NVDA",
            "tag": None,
            "review_type": None,
            "portfolio_slug": None,
            "source": None,
            "limit": 50,
            "offset": 0,
        }
    ]
    assert payload["count"] == 1
    reports = cast(list[dict[str, object]], payload["reports"])
    assert len(reports) == 1
    assert reports[0]["slug"] == "nvda_backend_lookup"
    assert reports[0]["metadata"] == {
        "author": None,
        "description": None,
        "tags": ["earnings"],
        "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
    }
    assert reports[0]["createdAt"] == "2026-01-02T03:04:05Z"


def test_position_runtime_tool_dispatches_to_position_service_with_defaults_and_output_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_positions(
        self: PositionService,
        *,
        capability_references: list[dict[str, object]],
        portfolio_slug: str,
        symbol: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PositionRead]:
        captured_calls.append(
            {
                "capability_references": capability_references,
                "portfolio_slug": portfolio_slug,
                "symbol": symbol,
                "limit": limit,
                "offset": offset,
                "quote_provider": self.quote_provider,
            }
        )
        if portfolio_slug == "unknown_portfolio":
            return []
        return [_position_read()]

    monkeypatch.setattr(PositionService, "lookup_positions", fake_lookup_positions)

    payload = registry.dispatch(
        name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"portfolioSlug":" position_lookup_reference ","symbol":" nvda "}',
        granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )

    assert captured_calls[0] == {
        "capability_references": [
            {"capabilityKey": "runtime_tool_test_capability", "capabilityVersion": 1}
        ],
        "portfolio_slug": "position_lookup_reference",
        "symbol": "NVDA",
        "limit": 50,
        "offset": 0,
        "quote_provider": None,
    }
    assert payload == {
        "count": 1,
        "portfolioSlug": "position_lookup_reference",
        "positions": [
            {
                "id": 11,
                "portfolioId": 5,
                "symbol": "NVDA",
                "name": "NVIDIA Corporation",
                "quantity": "12.00000000",
                "averageCost": "101.50000000",
                "currency": "USD",
                "createdAt": "2026-01-02T03:04:05Z",
                "updatedAt": "2026-01-02T03:04:05Z",
            }
        ],
    }

    empty_payload = registry.dispatch(
        name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"portfolioSlug":"unknown_portfolio","symbol":"NVDA","limit":10,"offset":0}',
        granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )
    assert empty_payload == {
        "count": 0,
        "portfolioSlug": "unknown_portfolio",
        "positions": [],
    }


def test_market_data_quote_lookup_dispatches_to_service_with_injected_provider(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_tool_capability(
        session_factory,
        tools=[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])
    quote_provider = _RecordingQuoteProvider(failing_symbols={"BAD"})

    payload = registry.dispatch(
        name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"symbols":[" nvda ","NVDA","bad"],"baseCurrency":null}',
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
    _seed_runtime_tool_capability(
        session_factory,
        tools=[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY],
    )
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
