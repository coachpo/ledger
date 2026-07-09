from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, cast

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
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.core.config import Settings, reset_settings_cache
from app.extensions.signaldeck_digital_oracle.config import (
    DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY,
    DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE,
    DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE,
    EDGAR_CONTACT_EMAIL_MISSING_CODE,
    EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
    EDGAR_CONTACT_EMAIL_SECRET,
    FRED_API_KEY_SECRET,
    MARKET_SENTIMENT_SOURCE_URL,
    DigitalOracleSettings,
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
    map_market_sentiment_result,
    map_prediction_markets_result,
    map_sec_filings_result,
)
from app.extensions.signaldeck_digital_oracle.ownership import (
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
    DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES,
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_digital_oracle.runtime_macro_rates import (
    MACRO_RATES_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_digital_oracle.runtime_market_sentiment import (
    MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_digital_oracle.runtime_prediction_markets import (
    PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_digital_oracle.runtime_sec_filings import (
    SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
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
)
from app.extensions.signaldeck_digital_oracle.service import DigitalOraclePhase1Service
from app.extensions.signaldeck_digital_oracle.types import (
    DigitalOracleMarketSentimentProviderResult,
    DigitalOracleMarketSentimentQuery,
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketOrderBook,
    DigitalOraclePredictionMarketOrderBookLevel,
    DigitalOraclePredictionMarketsQuery,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecOwnershipTransaction,
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
    RuntimeIndicatorLookupResult,
    RuntimeIndicatorValue,
    RuntimeNativeToolResult,
    RuntimeNewsItem,
    RuntimeNewsLookupResult,
    RuntimeOhlcvLookupResult,
    RuntimeOhlcvRow,
    RuntimeOhlcvSeries,
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
from tests.fixtures.fake_providers import (
    FakeDigitalOracleProvider,
    FakeDigitalOracleSecFilingsProvider,
    FakeFinanceProvider,
)
from tests.fixtures.workflow_manifests import base_manifest

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
                    manifest_source=base_manifest(package_key=package_key),
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

    polymarket_provider = FakeDigitalOracleProvider(
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
    kalshi_provider = FakeDigitalOracleProvider(
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
    sec_provider = FakeDigitalOracleSecFilingsProvider(
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
    sentiment_provider = FakeDigitalOracleProvider(
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
    prediction_provider = FakeDigitalOracleProvider(
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
    sec_provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    sentiment_provider = FakeDigitalOracleProvider(
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
    polymarket_provider = FakeDigitalOracleProvider(
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
    kalshi_provider = FakeDigitalOracleProvider(
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
    sec_provider = FakeDigitalOracleSecFilingsProvider(
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
    sentiment_provider = FakeDigitalOracleProvider(
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
    polymarket_provider = FakeDigitalOracleProvider(
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
    kalshi_provider = FakeDigitalOracleProvider(
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
    empty_sentiment_provider = FakeDigitalOracleProvider(
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
    quote_provider = FakeFinanceProvider()
    news_provider = FakeFinanceProvider(provider_name="runtime_news", news_count=3)
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
    quote_provider = FakeFinanceProvider()
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
    provider = FakeFinanceProvider()
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
    provider = FakeFinanceProvider()

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
    provider = FakeFinanceProvider(failing_symbols={"BAD"})

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
    provider = FakeFinanceProvider(provider_name="fundamentals_primary")

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
    failing_provider = FakeFinanceProvider(
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
    success_provider = FakeFinanceProvider(provider_name="fundamentals_secondary")

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
    missing_key_provider = FakeFinanceProvider(
        provider_name="fundamentals_missing_key",
        failure=QuoteProviderMissingKeyError("fundamentals API key is missing"),
    )
    failing_provider = FakeFinanceProvider(
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
    provider = FakeFinanceProvider(provider_name="news_primary", news_count=4)
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
    provider = FakeFinanceProvider(provider_name="global_news", news_count=4)
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
    provider = FakeFinanceProvider(provider_name="empty_global_news", news_count=0)

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
        FakeFinanceProvider(
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
    provider = FakeFinanceProvider(provider_name="insider_primary", insider_count=3)

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
    provider = FakeFinanceProvider()
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
    provider = FakeFinanceProvider()

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
    provider = FakeFinanceProvider()

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
    provider = FakeFinanceProvider()

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


def test_runtime_tool_context_carries_execution_identity_for_trusted_tools() -> None:
    capability_references: list[dict[str, object]] = [
        {"capabilityKey": "report_writer", "capabilityVersion": 3}
    ]
    quote_provider = FakeFinanceProvider()
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


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda spec: replace(
                spec,
                openai_function_name="signaldeck_test_lookup_alt",
            ),
            "Duplicate runtime tool key",
        ),
        (
            lambda spec: replace(spec, key="signaldeck.test.lookup.alt"),
            "Duplicate runtime tool OpenAI function name",
        ),
    ],
)
def test_runtime_tool_registry_rejects_duplicate_identifiers(
    mutator: Callable[[RuntimeToolSpec], RuntimeToolSpec],
    message: str,
) -> None:
    spec = _runtime_tool_spec()

    with pytest.raises(ValueError, match=message):
        _ = RuntimeToolRegistry([spec, mutator(spec)])


@pytest.mark.parametrize("surface", ["openai_and_signaldeck"])
def test_runtime_tool_registry_returns_catalog_surfaces_in_sort_order(surface: str) -> None:
    assert surface == "openai_and_signaldeck"
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC, MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC])
    tools = registry.get_openai_tools({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY})
    declarations = registry.get_tool_declarations(
        {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}
    )

    assert [tool["name"] for tool in tools] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)
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
    assert registry.get_guidance({MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}) == (
        "When you need persisted SignalDeck report context, call the "
        "signaldeck_finance_reports_lookup tool instead of inventing report content.\n\n"
        "When you need current or delayed market quotes, call the "
        "signaldeck_finance_market_data_quote_lookup tool instead of inventing prices. "
        "Disclose returned warnings or empty payloads as "
        "data quality or provider limitations."
    )
    assert registry.get_guidance(set()) == ""

    default_guidance = get_default_runtime_tool_registry().get_guidance(
        set(_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS)
    )
    for fragment in (
        "call signaldeck_finance_market_data_ohlcv_lookup",
        "call signaldeck_finance_indicators_lookup",
        "call signaldeck_finance_fundamentals_lookup",
        "instead of inventing metrics",
        "call signaldeck_finance_news_lookup",
        "instead of inventing articles",
        "call signaldeck_finance_social_sentiment_lookup",
        "instead of treating news as social data",
        "call signaldeck_finance_insider_data_lookup",
        "Disclose warnings or empty results as data quality",
        "do not claim unavailable coverage",
        "do not present unsupported provider coverage",
    ):
        assert fragment in default_guidance
    assert default_guidance.count("data quality or provider limitations") >= 6


@pytest.mark.parametrize("scenario", ["nested_closure", "openai_schema_deep_copy"])
def test_runtime_tool_registry_projects_strict_schemas_without_shared_mutation(
    scenario: str,
) -> None:
    if scenario == "nested_closure":
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
        return

    report_registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    tools = report_registry.get_openai_tools({REPORT_LOOKUP_TOOL_KEY})
    parameters = cast(dict[str, object], tools[0]["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    ticker_property = cast(dict[str, object], properties["ticker"])
    ticker_property["type"] = "mutated"

    fresh_tools = report_registry.get_openai_tools({REPORT_LOOKUP_TOOL_KEY})
    fresh_parameters = cast(dict[str, object], fresh_tools[0]["parameters"])
    fresh_properties = cast(dict[str, object], fresh_parameters["properties"])
    fresh_ticker_property = cast(dict[str, object], fresh_properties["ticker"])
    assert fresh_ticker_property["type"] == [
        "string",
        "null",
    ]


@pytest.mark.parametrize(
    ("granted_tool_keys", "expected_function_names"),
    [
        (
            {
                REPORT_LOOKUP_TOOL_KEY,
                MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
                MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
                SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
            },
            [
                REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
                MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
                MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
                SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            ],
        ),
        (
            {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            [MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME],
        ),
        (
            {MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY, MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            [
                MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
                MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            ],
        ),
        (
            {
                MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
                MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
                REPORT_LOOKUP_TOOL_KEY,
            },
            [
                REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
                MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
                MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            ],
        ),
    ],
)
def test_default_runtime_tool_registry_catalog_shape(
    granted_tool_keys: set[str],
    expected_function_names: list[str],
) -> None:
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

    tools = registry.get_openai_tools(granted_tool_keys)
    assert [tool["name"] for tool in tools] == expected_function_names
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
    quote_provider = FakeFinanceProvider()

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
    quote_provider = FakeFinanceProvider()

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


@pytest.mark.parametrize(
    ("spec", "tool_key", "function_name", "parser", "required", "property_names", "nested_check"),
    [
        (
            INDICATORS_LOOKUP_TOOL_SPEC,
            INDICATORS_LOOKUP_TOOL_KEY,
            INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_indicators_lookup_arguments,
            ["symbol", "currentDate", "startDate", "endDate", "indicators", "rowLimit"],
            {"symbol", "currentDate", "startDate", "endDate", "indicators", "rowLimit"},
            (
                ("indicators", "type"),
                [
                    "sma",
                    "ema",
                    "rsi",
                    "macd",
                    "bollinger_bands",
                    "atr",
                    "vwma",
                ],
            ),
        ),
        (
            FUNDAMENTALS_LOOKUP_TOOL_SPEC,
            FUNDAMENTALS_LOOKUP_TOOL_KEY,
            FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_fundamentals_lookup_arguments,
            ["symbol", "metricNames", "statementTypes", "periods", "statementLimit"],
            {"symbol", "metricNames", "statementTypes", "periods", "statementLimit"},
            (
                ("metricNames",),
                [
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
                ],
            ),
        ),
    ],
)
def test_market_data_runtime_tool_specs_preserve_business_selection_schemas(
    spec: RuntimeToolSpec,
    tool_key: str,
    function_name: str,
    parser: Callable[[str], dict[str, object]],
    required: list[str],
    property_names: set[str],
    nested_check: tuple[tuple[str, ...], list[str]],
) -> None:
    assert spec.key == tool_key
    assert spec.openai_function_name == function_name
    assert spec.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert spec.parser is parser

    schema = spec.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == required
    assert set(properties) == property_names

    path, expected_enum = nested_check
    property_schema = cast(dict[str, object], properties[path[0]])
    assert property_schema["type"] in ("array", ["array", "null"])
    item_schema = cast(dict[str, object], property_schema["items"])
    if len(path) == 2:
        item_properties = cast(dict[str, object], item_schema["properties"])
        enum_schema = cast(dict[str, object], item_properties[path[1]])
    else:
        enum_schema = item_schema
    assert enum_schema["enum"] == expected_enum


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
    quote_provider = FakeFinanceProvider(failing_symbols={"BAD"})

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
    quote_provider = FakeFinanceProvider(failing_symbols={"BAD"})

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
    quote_provider = FakeFinanceProvider()

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
    quote_provider = FakeFinanceProvider()

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
    quote_provider = FakeFinanceProvider(provider_name="fundamentals_primary")
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
    quote_provider = FakeFinanceProvider(provider_name="news_primary", news_count=4)

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
    quote_provider = FakeFinanceProvider(provider_name="insider_primary", insider_count=3)

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
    quote_provider = FakeFinanceProvider(
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
    quote_provider = FakeFinanceProvider(
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
    quote_provider = FakeFinanceProvider(
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


def _install_digital_oracle_runtime_tool_cases() -> None:
    from tests.fixtures import digital_oracle_runtime_tool_cases

    for case_name in dir(digital_oracle_runtime_tool_cases):
        if case_name.startswith("test_"):
            globals()[case_name] = getattr(digital_oracle_runtime_tool_cases, case_name)


_install_digital_oracle_runtime_tool_cases()
