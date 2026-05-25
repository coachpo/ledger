from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import TracebackType
from typing import Any, cast, override

import pytest
from pydantic import ValidationError
from sqlalchemy import select
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
from app.agents.runtime_tools.memory import (
    MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MEMORY_LOOKUP_TOOL_KEY,
    MEMORY_LOOKUP_TOOL_SPEC,
    MEMORY_TOOL_ACCESS_DENIED_CODE,
    MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    MEMORY_WRITE_TOOL_KEY,
    MEMORY_WRITE_TOOL_SPEC,
    RuntimeMemoryLookupArguments,
    RuntimeMemoryWriteArguments,
    RuntimeMemoryWriteResult,
    parse_memory_lookup_arguments,
    parse_memory_write_arguments,
)
from app.agents.runtime_tools.types import RuntimeToolWarning
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.signaldeck_finance.grant_policy import (
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_GRANT_POLICY,
    REPORT_LOOKUP_GRANT_POLICY,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
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
    parse_fundamentals_lookup_arguments,
    parse_history_lookup_arguments,
    parse_indicators_lookup_arguments,
    parse_insider_data_lookup_arguments,
    parse_news_lookup_arguments,
    parse_ohlcv_lookup_arguments,
    parse_quote_lookup_arguments,
    parse_social_sentiment_lookup_arguments,
)
from app.extensions.signaldeck_finance.runtime_positions import (
    POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    POSITION_LOOKUP_TOOL_SPEC,
    parse_position_lookup_arguments,
)
from app.extensions.signaldeck_finance.runtime_reports import (
    REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    REPORT_LOOKUP_TOOL_SPEC,
    REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    REPORT_MEMORY_WRITE_TOOL_SPEC,
    parse_report_lookup_arguments,
    parse_report_memory_write_arguments,
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
    POSITION_LOOKUP_TOOL_KEY,
    REPORT_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_TOOL_KEY,
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
    RuntimeReportMemoryWriteResult,
    RuntimeSocialSentimentLookupResult,
    RuntimeSocialSentimentMetric,
    RuntimeSocialSentimentSourceBlock,
)
from app.models.agent_memory import AgentMemoryEntry, RunMemoryEvent
from app.models.capability import Capability
from app.models.report import Report
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.schemas.market_data import MarketHistoryPointRead, MarketHistorySeriesRead, MarketQuoteRead
from app.schemas.memory import (
    MemoryLifecycleStatus,
    MemoryProvenance,
    MemoryRevisionAction,
)
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.services.agent_execution_service import AgentExecutionService
from app.services.capability_service import (
    CapabilityService,
    RuntimeToolGrantError,
    RuntimeToolGrantPolicy,
)
from app.services.execution_ownership import PackageExecutionOwnership
from app.services.market_data_service import MarketDataService
from app.services.model_gateway_dto import ModelGatewayError, ModelToolCall
from app.services.model_gateway_tool_retry import ModelToolCallRetryState
from app.services.model_gateway_tool_strategy import build_model_tool_call
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
_RUNTIME_RUN_ID = 4242
_RUNTIME_RUN_STEP_ID = 5101
_RUNTIME_AGENT_INVOCATION_ID = 5201
_RUNTIME_OPERATION_INVOCATION_ID = 5301
_RUNTIME_TOOL_CALL_INVOCATION_ID = "tool-call-runtime-memory"
_RUNTIME_TRACE_SPAN_ID = "span-runtime-tools"

_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS = (
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
)
_GENERIC_PLATFORM_RUNTIME_TOOL_OPENAI_FUNCTION_NAMES_BY_KEY = {
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY: "signaldeck_market_data_ohlcv_lookup",
    INDICATORS_LOOKUP_TOOL_KEY: "signaldeck_indicators_lookup",
    FUNDAMENTALS_LOOKUP_TOOL_KEY: "signaldeck_fundamentals_lookup",
    NEWS_LOOKUP_TOOL_KEY: "signaldeck_news_lookup",
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY: "signaldeck_social_sentiment_lookup",
    INSIDER_DATA_LOOKUP_TOOL_KEY: "signaldeck_insider_data_lookup",
}
_EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS = {
    MEMORY_WRITE_TOOL_KEY,
    MEMORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    POSITION_LOOKUP_TOOL_KEY,
    REPORT_LOOKUP_TOOL_KEY,
}
_FORBIDDEN_REPORT_WRITE_MODEL_KEYS = {
    "reportId",
    "reportSlug",
    "reportName",
    "auditLinks",
    "url",
    "downloadUrl",
}
_FORBIDDEN_REPORT_WRITE_MODEL_FRAGMENTS = ("/reports/", "download")
_FORBIDDEN_CORE_MEMORY_MODEL_KEYS = _FORBIDDEN_REPORT_WRITE_MODEL_KEYS
_FORBIDDEN_CORE_MEMORY_MODEL_FRAGMENTS = ("/reports/", "download", "http://", "https://")


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
                tool_keys=list(tools),
            )
        )
        session.commit()


def _seed_runtime_run(
    session_factory: sessionmaker[Session],
    *,
    run_id: int = _RUNTIME_RUN_ID,
) -> None:
    with session_factory() as session:
        session.add(
            Run(
                id=run_id,
                target_kind="workflow",
                target_id=1,
                target_key="runtime_tool_test_workflow",
                target_version=1,
                input={},
                status="running",
            )
        )
        session.add(
            RunStep(
                id=_RUNTIME_RUN_STEP_ID,
                run_id=run_id,
                step_index=1,
                status="running",
            )
        )
        session.add(
            RunAgentInvocation(
                id=_RUNTIME_AGENT_INVOCATION_ID,
                run_step_id=_RUNTIME_RUN_STEP_ID,
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
                id=_RUNTIME_OPERATION_INVOCATION_ID,
                run_step_id=_RUNTIME_RUN_STEP_ID,
                run_id=run_id,
                step_index=1,
                slot="memory_dispatch",
                position=1,
                operation_key="memory_dispatch",
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


def _reports_write_arguments_json(
    analysis_overrides: dict[str, object] | None = None,
    root_overrides: dict[str, object] | None = None,
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
    payload: dict[str, object] = {"analysis": analysis}
    if root_overrides is not None:
        payload.update(root_overrides)
    return json.dumps(payload)


def _memory_write_arguments_json(
    overrides: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "kind": "research.note",
        "summary": "Durable model-safe memory.",
        "content": "Prior run found durable evidence.",
        "subjectRefs": [{"kind": "instrument", "id": "NVDA", "label": None, "attributes": None}],
        "attributes": {"tags": ["earnings"], "confidence": "high"},
        "scope": None,
        "idempotencyKey": "runtime-core-memory-write",
        "supersedesRevisionId": None,
    }
    if overrides is not None:
        payload.update(overrides)
    return json.dumps(payload)


def _runtime_package_ownership(*, package_key: str) -> PackageExecutionOwnership:
    return PackageExecutionOwnership(
        package_id=9001,
        package_key=package_key,
        manifest_hash=f"manifest-{package_key}",
        compiled_hash=f"compiled-{package_key}",
        workflow_key="platform_graph_daily_review",
    )


def _reports_write_runtime_context(
    session_factory: sessionmaker[Session],
    *,
    capability_key: str = "runtime_tool_test_capability",
    package_ownership: PackageExecutionOwnership | None = None,
) -> RuntimeToolContext:
    return _runtime_context(
        capability_references=[{"capabilityKey": capability_key, "capabilityVersion": 1}],
        session_factory_override=session_factory,
        run_id=_RUNTIME_RUN_ID,
        run_step_id=_RUNTIME_RUN_STEP_ID,
        run_agent_invocation_id=_RUNTIME_AGENT_INVOCATION_ID,
        run_operation_invocation_id=_RUNTIME_OPERATION_INVOCATION_ID,
        agent_key="portfolio_manager",
        agent_version=3,
        agent_name="Portfolio Manager",
        package_ownership=package_ownership,
        workflow_key="platform_graph_daily_review",
        workflow_version=5,
        step_id="portfolio_decision",
        slot="decision",
        trace_id="trace-runtime-tools",
        trace_span_id=_RUNTIME_TRACE_SPAN_ID,
        invocation_id=_RUNTIME_TOOL_CALL_INVOCATION_ID,
    )


def _reports_write_provenance() -> MemoryProvenance:
    return MemoryProvenance(
        run_id=4242,
        agent_key="portfolio_manager",
        agent_version=3,
        agent_name="Portfolio Manager",
        workflow_key="platform_graph_daily_review",
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


def _assert_retired_reports_write_payload_is_json_safe(payload: dict[str, object]) -> None:
    assert {"toolKey", "memoryId", "status", "action", "createdAt", "warnings"} <= set(payload)
    assert payload["toolKey"] == REPORT_MEMORY_WRITE_TOOL_KEY
    _assert_report_write_forbidden_keys_absent(payload, path="$")
    payload_json = json.dumps(payload, sort_keys=True)
    for fragment in _FORBIDDEN_REPORT_WRITE_MODEL_FRAGMENTS:
        assert fragment not in payload_json


def _assert_report_write_forbidden_keys_absent(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert key not in _FORBIDDEN_REPORT_WRITE_MODEL_KEYS, f"forbidden key at {path}.{key}"
            _assert_report_write_forbidden_keys_absent(nested_value, path=f"{path}.{key}")
        return

    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_report_write_forbidden_keys_absent(nested_value, path=f"{path}[{index}]")


def _assert_core_memory_payload_is_model_safe(payload: dict[str, object]) -> None:
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    _assert_core_memory_forbidden_keys_absent(payload, path="$")
    payload_json = json.dumps(payload, sort_keys=True)
    for fragment in _FORBIDDEN_CORE_MEMORY_MODEL_FRAGMENTS:
        assert fragment not in payload_json


def _assert_core_memory_forbidden_keys_absent(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert key not in _FORBIDDEN_CORE_MEMORY_MODEL_KEYS, f"forbidden key at {path}.{key}"
            _assert_core_memory_forbidden_keys_absent(nested_value, path=f"{path}.{key}")
        return

    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_core_memory_forbidden_keys_absent(nested_value, path=f"{path}[{index}]")


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
    assert all(
        tool_key.startswith("signaldeck.") for tool_key in NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS
    )
    assert set(_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS) <= set(NATIVE_RUNTIME_FINANCIAL_TOOL_KEYS)

    with pytest.raises(
        ValidationError, match="Native runtime tool keys must start with signaldeck"
    ):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "external.market_data.quote_lookup"})
    with pytest.raises(ValidationError, match="not registered as a financial tool result"):
        _ = RuntimeNativeToolResult.model_validate({"toolKey": "signaldeck.unregistered.lookup"})


def test_builtin_native_runtime_tool_catalog_and_specs_stay_aligned() -> None:
    runtime_spec_keys = {spec.key for spec in RUNTIME_TOOL_SPECS}
    server_declared_keys = {spec.key for spec in SERVER_DECLARED_TOOL_SPECS}
    runtime_function_names = {spec.openai_function_name for spec in RUNTIME_TOOL_SPECS}

    assert runtime_spec_keys == _EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS
    assert server_declared_keys == _EXPECTED_BUILT_IN_RUNTIME_TOOL_KEYS
    assert runtime_spec_keys == server_declared_keys
    assert {MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY} <= runtime_spec_keys
    assert {MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY} <= server_declared_keys
    assert MEMORY_WRITE_OPENAI_FUNCTION_NAME in runtime_function_names
    assert MEMORY_LOOKUP_OPENAI_FUNCTION_NAME in runtime_function_names


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
    assert quote_payload["toolKey"] == "signaldeck.market_data.quote_lookup"
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
    assert history_payload["toolKey"] == "signaldeck.market_data.history_lookup"
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
    assert ohlcv_payload["toolKey"] == "signaldeck.market_data.ohlcv_lookup"
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
    assert indicator_payload["toolKey"] == "signaldeck.indicators.lookup"
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
    assert fundamentals_payload["toolKey"] == "signaldeck.fundamentals.lookup"
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
    assert news_payload["toolKey"] == "signaldeck.news.lookup"
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
    assert social_sentiment_payload["toolKey"] == "signaldeck.social_sentiment.lookup"
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
    assert insider_payload["toolKey"] == "signaldeck.insider_data.lookup"
    assert insider_payload["transactions"][0]["insiderName"] == "Ada Lovelace"
    assert insider_payload["transactions"][0]["transactionDate"] == "2026-01-02T03:04:05Z"
    assert insider_payload["transactions"][0]["filedAt"] == "2026-01-02T03:04:05Z"

    memory_payload = RuntimeReportMemoryWriteResult(
        memory_id="mem_7",
        status=MemoryLifecycleStatus.PENDING,
        action="created",
        created_at=_NOW,
        provenance=_reports_write_provenance(),
        warnings=[
            {
                "code": "memory_reused",
                "message": "Existing memory was reused.",
                "details": {"memoryId": "mem_7"},
            }
        ],
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(memory_payload)
    _assert_retired_reports_write_payload_is_json_safe(memory_payload)
    assert memory_payload == {
        "toolKey": "signaldeck.reports.write",
        "memoryId": "mem_7",
        "status": "pending",
        "action": "created",
        "createdAt": "2026-01-02T03:04:05Z",
        "provenance": {
            "runId": 4242,
            "agentKey": "portfolio_manager",
            "agentVersion": 3,
            "agentName": "Portfolio Manager",
            "workflowKey": "platform_graph_daily_review",
            "workflowVersion": 5,
            "stepId": "portfolio_decision",
            "slot": "decision",
            "traceId": "trace-runtime-tools",
            "createdByType": "agent",
        },
        "warnings": [
            {
                "code": "memory_reused",
                "message": "Existing memory was reused.",
                "details": {"memoryId": "mem_7"},
            }
        ],
    }

    core_memory_payload = RuntimeMemoryWriteResult(
        memory_id="memory_7",
        revision_id="revision_7",
        status=MemoryLifecycleStatus.PENDING,
        revision_action=MemoryRevisionAction.CREATED,
        created_at=_NOW,
        provenance=_reports_write_provenance(),
    ).model_dump(mode="json", by_alias=True)
    _assert_core_memory_payload_is_model_safe(core_memory_payload)
    assert core_memory_payload["toolKey"] == MEMORY_WRITE_TOOL_KEY
    assert core_memory_payload["memoryId"] == "memory_7"
    assert core_memory_payload["revisionId"] == "revision_7"
    assert core_memory_payload["revisionAction"] == "created"
    assert "action" not in core_memory_payload


def test_news_lookup_contract_remains_news_only_and_backward_compatible() -> None:
    parameters = NEWS_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], parameters["properties"])

    assert NEWS_LOOKUP_TOOL_SPEC.key == NEWS_LOOKUP_TOOL_KEY
    assert NEWS_LOOKUP_TOOL_SPEC.openai_function_name == NEWS_LOOKUP_OPENAI_FUNCTION_NAME
    assert list(properties) == ["symbols", "query", "startDate", "endDate", "itemLimit"]
    assert parameters["required"] == ["symbols", "query", "startDate", "endDate", "itemLimit"]
    assert "sources" not in properties
    assert "sourceBlocks" not in properties

    parsed = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": [" nvda ", "NVDA"],
                "query": " earnings ",
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        )
    )
    assert parsed == {
        "symbols": ["NVDA"],
        "query": "earnings",
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
    assert "sourceBlocks" not in payload
    assert "metrics" not in payload


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
        (["NVDA"], "earnings", start_date.astimezone(UTC), end_date.astimezone(UTC), 3)
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


def test_report_lookup_source_schema_includes_agent() -> None:
    parameters = REPORT_LOOKUP_TOOL_SPEC.parameters_schema
    properties = cast(dict[str, object], parameters["properties"])
    source_property = cast(dict[str, object], properties["source"])
    assert source_property["enum"] == ["compiled", "uploaded", "external", "agent", None]


def test_report_lookup_accepts_agent_source() -> None:
    parsed = parse_report_lookup_arguments('{"source":"agent"}')
    assert parsed["source"] == "agent"


def test_runtime_tool_spec_is_frozen_and_separates_display_metadata_from_execution_fields() -> None:
    assert MEMORY_WRITE_TOOL_KEY == "signaldeck.memory.write"
    assert MEMORY_WRITE_OPENAI_FUNCTION_NAME == "signaldeck_memory_write"
    assert MEMORY_WRITE_TOOL_SPEC.key == MEMORY_WRITE_TOOL_KEY
    assert MEMORY_WRITE_TOOL_SPEC.openai_function_name == MEMORY_WRITE_OPENAI_FUNCTION_NAME
    assert MEMORY_WRITE_TOOL_SPEC.display_name == "Memory Write"
    assert MEMORY_WRITE_TOOL_SPEC.owner_extension_key is None
    assert MEMORY_LOOKUP_TOOL_KEY == "signaldeck.memory.lookup"
    assert MEMORY_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_memory_lookup"
    assert MEMORY_LOOKUP_TOOL_SPEC.key == MEMORY_LOOKUP_TOOL_KEY
    assert MEMORY_LOOKUP_TOOL_SPEC.openai_function_name == MEMORY_LOOKUP_OPENAI_FUNCTION_NAME
    assert MEMORY_LOOKUP_TOOL_SPEC.display_name == "Memory Lookup"
    assert MEMORY_LOOKUP_TOOL_SPEC.owner_extension_key is None

    assert REPORT_LOOKUP_TOOL_KEY == "signaldeck.reports.lookup"
    assert REPORT_LOOKUP_OPENAI_FUNCTION_NAME == "signaldeck_reports_lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key == REPORT_LOOKUP_TOOL_KEY
    assert REPORT_LOOKUP_TOOL_SPEC.openai_function_name == REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    assert REPORT_LOOKUP_TOOL_SPEC.display_name == "Report Lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.description

    assert REPORT_MEMORY_WRITE_TOOL_KEY == "signaldeck.reports.write"
    assert REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME == "signaldeck_reports_write"
    assert REPORT_MEMORY_WRITE_TOOL_SPEC.key == REPORT_MEMORY_WRITE_TOOL_KEY
    assert (
        REPORT_MEMORY_WRITE_TOOL_SPEC.openai_function_name
        == REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME
    )
    assert REPORT_MEMORY_WRITE_TOOL_SPEC.display_name == "Retired Report Memory Write"
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
            [spec, replace(spec, openai_function_name="signaldeck_test_lookup_alt")]
        )

    with pytest.raises(ValueError, match="Duplicate runtime tool OpenAI function name"):
        _ = RuntimeToolRegistry([spec, replace(spec, key="signaldeck.test.lookup.alt")])


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
        "Read persisted SignalDeck reports by ticker, tag, review type, portfolio slug, source, "
        "limit, and offset."
    )
    assert tools[1]["description"] == (
        "Read persisted SignalDeck positions for a portfolio slug, optionally filtered by symbol, "
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
        "agent",
        None,
    ]
    position_parameters = cast(dict[str, object], tools[1]["parameters"])
    position_properties = cast(dict[str, object], position_parameters["properties"])
    assert position_parameters["required"] == ["portfolioSlug", "symbol", "limit", "offset"]
    position_limit_property = cast(dict[str, object], position_properties["limit"])
    assert position_limit_property["maximum"] == 200

    position_only_tools = registry.get_openai_tools({POSITION_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in position_only_tools] == [POSITION_LOOKUP_OPENAI_FUNCTION_NAME]


def test_runtime_tool_registry_returns_signaldeck_declarations_in_sort_order() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC, REPORT_LOOKUP_TOOL_SPEC])

    declarations = registry.get_tool_declarations(
        {POSITION_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}
    )

    assert [declaration.tool_key for declaration in declarations] == [
        REPORT_LOOKUP_TOOL_KEY,
        POSITION_LOOKUP_TOOL_KEY,
    ]
    assert [declaration.model_name for declaration in declarations] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert {declaration.kind for declaration in declarations} == {"native_runtime"}
    assert all(declaration.strict for declaration in declarations)
    report_schema = cast(dict[str, object], declarations[0].input_schema)
    assert report_schema["required"] == [
        "ticker",
        "tag",
        "reviewType",
        "portfolioSlug",
        "source",
        "limit",
        "offset",
    ]


def test_default_runtime_tool_registry_exposes_financial_runtime_specs() -> None:
    registry = get_default_runtime_tool_registry()

    spec_by_key = {spec.key: spec for spec in registry.list_specs()}
    assert spec_by_key[MEMORY_WRITE_TOOL_KEY].openai_function_name == (
        MEMORY_WRITE_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MEMORY_LOOKUP_TOOL_KEY].openai_function_name == (
        MEMORY_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[REPORT_LOOKUP_TOOL_KEY].openai_function_name == (
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert REPORT_MEMORY_WRITE_TOOL_KEY not in spec_by_key
    assert spec_by_key[MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY].openai_function_name == (
        MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert spec_by_key[SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY].openai_function_name == (
        SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME
    )
    tools = registry.get_openai_tools(
        {
            REPORT_LOOKUP_TOOL_KEY,
            REPORT_MEMORY_WRITE_TOOL_KEY,
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


def test_runtime_tool_registry_hides_disabled_extension_tools_and_dispatches_typed_error() -> None:
    registry = RuntimeToolRegistry(RUNTIME_TOOL_SPECS, enabled_extension_keys=set())
    context = _runtime_context(fail_on_session=True)

    assert registry.get_openai_tools({REPORT_LOOKUP_TOOL_KEY}) == []
    assert registry.get_guidance({REPORT_LOOKUP_TOOL_KEY}) == ""
    core_tools = registry.get_openai_tools({MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in core_tools] == [
        MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    assert "signaldeck_memory_lookup" in registry.get_guidance({MEMORY_LOOKUP_TOOL_KEY})

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"limit":50}',
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            context=context,
        )

    assert exc_info.value.code == "extension_disabled"
    assert exc_info.value.message == "Extension is disabled"
    assert exc_info.value.details == [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": f"runtime.tool.{REPORT_LOOKUP_TOOL_KEY}",
        }
    ]


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
            REPORT_MEMORY_WRITE_TOOL_KEY,
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
    assert REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME not in {
        cast(str, tool["name"]) for tool in all_native_financial
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
        "When you need persisted SignalDeck report context, call the "
        "signaldeck_reports_lookup tool instead of inventing report content.\n\n"
        "When you need persisted SignalDeck position context, call the "
        "signaldeck_positions_lookup tool instead of inventing portfolio holdings."
    )
    assert registry.get_guidance(set()) == ""


def test_generic_platform_runtime_guidance_discloses_provider_limitations() -> None:
    registry = get_default_runtime_tool_registry()

    guidance = registry.get_guidance(set(_GENERIC_PLATFORM_RUNTIME_TOOL_KEYS))

    assert "call signaldeck_market_data_ohlcv_lookup" in guidance
    assert "call signaldeck_indicators_lookup" in guidance
    assert "call signaldeck_fundamentals_lookup" in guidance
    assert "instead of inventing metrics" in guidance
    assert "call signaldeck_news_lookup" in guidance
    assert "instead of inventing articles" in guidance
    assert "call signaldeck_social_sentiment_lookup" in guidance
    assert "instead of treating news as social data" in guidance
    assert "call signaldeck_insider_data_lookup" in guidance
    assert "Disclose warnings or empty results as data quality" in guidance
    assert guidance.count("data quality or provider limitations") >= 6
    assert "do not claim unavailable coverage" in guidance
    assert "do not present unsupported provider coverage" in guidance


def test_runtime_capability_service_resolves_stored_tool_keys_and_fails_closed(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_resolve_tool_keys"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[REPORT_LOOKUP_TOOL_KEY, POSITION_LOOKUP_TOOL_KEY],
    )
    capability_references: list[dict[str, object]] = [
        {"capabilityKey": capability_key, "capabilityVersion": 1}
    ]

    with session_factory() as session:
        service = CapabilityService(session, get_default_tool_catalog())
        assert service.resolve_granted_tool_keys(capability_references) == {
            REPORT_LOOKUP_TOOL_KEY,
            POSITION_LOOKUP_TOOL_KEY,
        }
        service.require_runtime_tool_grant(
            capability_references=capability_references,
            grant_policy=REPORT_LOOKUP_GRANT_POLICY,
        )
        service.require_runtime_tool_grant(
            capability_references=capability_references,
            grant_policy=POSITION_LOOKUP_GRANT_POLICY,
        )

        capability = session.scalar(select(Capability).where(Capability.key == capability_key))
        assert capability is not None
        capability.tool_keys = ["signaldeck.stale.lookup"]
        session.commit()

        with pytest.raises(RuntimeToolGrantError) as exc_info:
            service.require_runtime_tool_grant(
                capability_references=capability_references,
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
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as unknown_error:
        _ = registry.dispatch(
            name="signaldeck_unknown_lookup",
            arguments_json='{"portfolioSlug":"reference"}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert unknown_error.value.code == "agent_tool_call_unsupported"
    assert (
        unknown_error.value.message
        == "Agent requested unsupported server tool 'signaldeck_unknown_lookup'."
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


def test_agent_execution_native_to_mcp_fallback_only_for_unsupported_tool_calls() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)
    mcp_dispatcher = _RecordingMcpDispatcher()

    output = AgentExecutionService._dispatch_function_call(
        tool_call=ModelToolCall(
            tool_name="mcp_external_lookup",
            arguments_json='{"ticker":"NVDA"}',
            call_id="call-mcp",
        ),
        granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
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
                tool_name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
                arguments_json="not-json",
                call_id="call-denied",
            ),
            granted_tool_keys=set(),
            runtime_tool_registry=registry,
            runtime_tool_context=context,
            mcp_dispatcher=cast(Any, mcp_dispatcher),
        )

    assert exc_info.value.code == POSITION_LOOKUP_ACCESS_DENIED_CODE
    assert exc_info.value.message == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE
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
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            runtime_tool_registry=registry,
            runtime_tool_context=context,
            mcp_dispatcher=cast(Any, mcp_dispatcher),
        )

    assert native_unknown_error.value.code == "agent_tool_call_unsupported"
    assert native_unknown_error.value.retryable is False
    assert mcp_dispatcher.calls == [
        {"arguments_json": '{"ticker":"NVDA"}', "name": "mcp_external_lookup"}
    ]


def test_retired_reports_write_error_does_not_fall_through_to_mcp(
    session_factory: sessionmaker[Session],
) -> None:
    registry = get_default_runtime_tool_registry()
    context = _reports_write_runtime_context(session_factory)
    mcp_dispatcher = _RecordingMcpDispatcher()

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = AgentExecutionService._dispatch_function_call(
            tool_call=ModelToolCall(
                tool_name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
                arguments_json=_reports_write_arguments_json(),
                call_id="call-retired-report-write",
            ),
            granted_tool_keys=set(),
            runtime_tool_registry=registry,
            runtime_tool_context=context,
            mcp_dispatcher=cast(Any, mcp_dispatcher),
        )

    assert exc_info.value.code == "report_memory_write_retired"
    assert mcp_dispatcher.calls == []


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
            name="signaldeck_memory_lookup",
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
            name="signaldeck_memory_lookup",
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
        {"field": "arguments.extra", "issue": "Field is not allowed"},
        {"field": "arguments.ticker", "issue": "Expected string value"},
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
                    {"field": "arguments.extra", "issue": "Field is not allowed"},
                    {"field": "arguments.ticker", "issue": "Expected string value"},
                ],
            }
        ],
    }
    assert client.calls == []


def test_failure_taxonomy_auth_secret_extension_disabled_provider_network_classes_are_fatal() -> (
    None
):
    expected = {
        "agent_model_connection_api_key_missing": ToolFailureClass.SECRET_CONTEXT,
        "extension_disabled": ToolFailureClass.EXTENSION_DISABLED,
        "agent_execution_access_denied": ToolFailureClass.PERMISSION,
        "agent_provider_connection_error": ToolFailureClass.PROVIDER_NETWORK,
        "mcp_runtime_transport_unavailable": ToolFailureClass.MCP_TRANSPORT,
        "report_memory_write_retired": ToolFailureClass.UNSUPPORTED_TOOL,
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


def test_core_memory_runtime_tool_registry_denies_ungranted_before_parsing() -> None:
    registry = RuntimeToolRegistry([MEMORY_WRITE_TOOL_SPEC, MEMORY_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as write_error:
        _ = registry.dispatch(
            name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert write_error.value.code == MEMORY_TOOL_ACCESS_DENIED_CODE
    assert write_error.value.message == MEMORY_WRITE_ACCESS_DENIED_MESSAGE

    with pytest.raises(RuntimeToolError) as lookup_error:
        _ = registry.dispatch(
            name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert lookup_error.value.code == MEMORY_TOOL_ACCESS_DENIED_CODE
    assert lookup_error.value.message == MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE


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
    assert exc_info.value.message == "signaldeck_reports_write arguments failed validation."
    assert exc_info.value.details[0]["field"] == f"analysis.{field_name}"


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        ("{", "OpenAI response requested signaldeck_reports_write with invalid JSON arguments."),
        ("[]", "signaldeck_reports_write arguments must be a JSON object."),
        (
            '{"runId":42,"analysis":{}}',
            "signaldeck_reports_write arguments contained unsupported fields: runId",
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


def test_report_memory_write_rejects_created_by_argument() -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_report_memory_write_arguments(
            _reports_write_arguments_json(
                root_overrides={
                    "createdBy": {
                        "type": "agent",
                        "runId": 4242,
                        "agentKey": "portfolio_manager",
                        "agentVersion": 3,
                    }
                }
            )
        )

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert (
        exc_info.value.message
        == "signaldeck_reports_write arguments contained unsupported fields: createdBy"
    )


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        ("{", "OpenAI response requested signaldeck_memory_write with invalid JSON arguments."),
        ("[]", "signaldeck_memory_write arguments must be a JSON object."),
        (
            '{"summary":"Memory","content":"Body","reportId":"rpt_1"}',
            "signaldeck_memory_write arguments contained unsupported fields: reportId",
        ),
        ('{"summary":"Memory"}', "signaldeck_memory_write arguments failed validation."),
    ],
)
def test_memory_write_runtime_tool_parser_preserves_boundary_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_memory_write_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message


def test_memory_write_runtime_tool_parser_normalizes_happy_path() -> None:
    payload = cast(
        RuntimeMemoryWriteArguments,
        parse_memory_write_arguments(_memory_write_arguments_json())["payload"],
    )

    assert payload.kind == "research.note"
    assert payload.summary == "Durable model-safe memory."
    assert payload.content == "Prior run found durable evidence."
    assert payload.subject_refs[0].kind == "instrument"
    assert payload.scope is None
    assert payload.idempotency_key == "runtime-core-memory-write"


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        ("{", "OpenAI response requested signaldeck_memory_lookup with invalid JSON arguments."),
        ("[]", "signaldeck_memory_lookup arguments must be a JSON object."),
        (
            '{"unsupported":true}',
            "signaldeck_memory_lookup arguments contained unsupported fields: unsupported",
        ),
        ('{"limit":21}', "signaldeck_memory_lookup arguments failed validation."),
        ('{"maxCharacters":8001}', "signaldeck_memory_lookup arguments failed validation."),
    ],
)
def test_memory_lookup_runtime_tool_parser_enforces_boundary_and_budget_rules(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_memory_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message


def test_memory_lookup_runtime_tool_parser_defaults_to_current_context_fallback() -> None:
    payload = cast(
        RuntimeMemoryLookupArguments,
        parse_memory_lookup_arguments("{}")["payload"],
    )
    query = payload.to_query()

    assert query.scope_mode == "current-context-fallback"
    assert query.fallback_scope == "current-run-package-agent"
    assert query.limit == 5
    assert query.max_characters == 4000


def test_reports_write_runtime_tool_retirement_preempts_missing_write_grant(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_reports_write_without_service_grant"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[REPORT_LOOKUP_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])

    with pytest.raises(RuntimeToolError) as exc_info:
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
    assert exc_info.value.code == "report_memory_write_retired"
    assert reports == []


def test_reports_write_runtime_tool_fails_closed_for_core_memory_grant_only(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_reports_write_core_memory_key_only"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[MEMORY_WRITE_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])

    with pytest.raises(RuntimeToolError) as exc_info:
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
    assert exc_info.value.code == "report_memory_write_retired"
    assert reports == []


def test_reports_write_runtime_tool_fails_closed_after_retirement(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_tool_capability(
        session_factory,
        tools=[REPORT_MEMORY_WRITE_TOOL_KEY],
    )
    registry = RuntimeToolRegistry([REPORT_MEMORY_WRITE_TOOL_SPEC])
    context = _reports_write_runtime_context(session_factory)

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
            arguments_json=_reports_write_arguments_json(),
            granted_tool_keys={REPORT_MEMORY_WRITE_TOOL_KEY},
            context=context,
        )

    with session_factory() as session:
        reports = list(session.scalars(select(Report)))
        entries = list(session.scalars(select(AgentMemoryEntry)))

    assert exc_info.value.code == "report_memory_write_retired"
    assert exc_info.value.message == (
        "signaldeck_reports_write is retired; use signaldeck_memory_write for "
        "canonical platform memory writes."
    )
    assert reports == []
    assert entries == []


def test_memory_write_runtime_tool_creates_core_memory_without_reports(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_tool_capability(session_factory, tools=[MEMORY_WRITE_TOOL_KEY])
    _seed_runtime_run(session_factory)
    registry = RuntimeToolRegistry([MEMORY_WRITE_TOOL_SPEC], enabled_extension_keys=set())
    context = _reports_write_runtime_context(session_factory)

    first_payload = registry.dispatch(
        name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        arguments_json=_memory_write_arguments_json(),
        granted_tool_keys={MEMORY_WRITE_TOOL_KEY},
        context=context,
    )
    second_payload = registry.dispatch(
        name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        arguments_json=_memory_write_arguments_json(),
        granted_tool_keys={MEMORY_WRITE_TOOL_KEY},
        context=context,
    )

    _assert_core_memory_payload_is_model_safe(first_payload)
    _assert_core_memory_payload_is_model_safe(second_payload)
    assert first_payload["toolKey"] == MEMORY_WRITE_TOOL_KEY
    assert first_payload["memoryId"] == second_payload["memoryId"]
    assert str(first_payload["memoryId"]).startswith("memory_")
    assert str(first_payload["revisionId"]).startswith("revision_")
    assert first_payload["status"] == "pending"
    assert first_payload["revisionAction"] == "created"
    assert second_payload["revisionAction"] == "reused"
    assert "action" not in first_payload

    with session_factory() as session:
        reports = list(session.scalars(select(Report)))
        entries = list(session.scalars(select(AgentMemoryEntry)))
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))

    assert reports == []
    assert len(entries) == 1
    assert entries[0].memory_id == first_payload["memoryId"]
    assert [event.event_type for event in events] == ["written", "reused"]
    for event in events:
        assert event.run_id == _RUNTIME_RUN_ID
        assert event.run_step_id == _RUNTIME_RUN_STEP_ID
        assert event.run_agent_invocation_id == _RUNTIME_AGENT_INVOCATION_ID
        assert event.run_operation_invocation_id == _RUNTIME_OPERATION_INVOCATION_ID
        assert event.step_id == "portfolio_decision"
        assert event.invocation_id == _RUNTIME_TOOL_CALL_INVOCATION_ID
        assert event.trace_span_id == _RUNTIME_TRACE_SPAN_ID
        assert event.memory_id == first_payload["memoryId"]


def test_memory_lookup_runtime_tool_uses_current_context_with_finance_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_tool_capability(
        session_factory,
        tools=[MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY],
    )
    _seed_runtime_run(session_factory)
    registry = RuntimeToolRegistry(RUNTIME_TOOL_SPECS, enabled_extension_keys=set())
    context = _reports_write_runtime_context(session_factory)
    write_args = _memory_write_arguments_json(
        {
            "content": (
                "## Report [download](https://example.test/reports/1/download)\n"
                "- Keep this insight."
            ),
            "attributes": {"reportId": 7, "safe": "kept"},
        }
    )
    _ = registry.dispatch(
        name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        arguments_json=write_args,
        granted_tool_keys={MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY},
        context=context,
    )

    lookup_payload = registry.dispatch(
        name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "query": None,
                "scope": None,
                "subjectRefs": None,
                "kind": None,
                "status": "pending",
                "tags": None,
                "limit": None,
                "offset": None,
                "maxCharacters": None,
            }
        ),
        granted_tool_keys={MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY},
        context=context,
    )

    _assert_core_memory_payload_is_model_safe(lookup_payload)
    assert lookup_payload["toolKey"] == MEMORY_LOOKUP_TOOL_KEY
    assert lookup_payload["scopeMode"] == "current-context-fallback"
    assert lookup_payload["fallbackScope"] == "current-run-package-agent"
    assert lookup_payload["limit"] == 5
    assert lookup_payload["maxCharacters"] == 4000
    assert lookup_payload["count"] == 1
    memory = cast(list[dict[str, object]], lookup_payload["memories"])[0]
    assert memory["content"] == "Report [redacted]\nKeep this insight."
    assert memory["attributes"] == {}

    with session_factory() as session:
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))

    assert [event.event_type for event in events] == ["written", "retrieved", "injected"]
    retrieval_event = events[1]
    injected_event = events[2]
    assert retrieval_event.run_id == _RUNTIME_RUN_ID
    assert retrieval_event.run_step_id == _RUNTIME_RUN_STEP_ID
    assert retrieval_event.run_agent_invocation_id == _RUNTIME_AGENT_INVOCATION_ID
    assert retrieval_event.run_operation_invocation_id == _RUNTIME_OPERATION_INVOCATION_ID
    assert retrieval_event.step_id == "portfolio_decision"
    assert retrieval_event.invocation_id == _RUNTIME_TOOL_CALL_INVOCATION_ID
    assert retrieval_event.trace_span_id == _RUNTIME_TRACE_SPAN_ID
    assert retrieval_event.memory_id is None
    assert retrieval_event.budget == {"limit": 5, "offset": 0, "maxCharacters": 4000}
    assert retrieval_event.result_snapshot["resultCount"] == 1
    assert retrieval_event.result_snapshot["snippets"][0]["memoryId"] == memory["memoryId"]
    assert injected_event.run_id == _RUNTIME_RUN_ID
    assert injected_event.run_step_id == _RUNTIME_RUN_STEP_ID
    assert injected_event.run_agent_invocation_id == _RUNTIME_AGENT_INVOCATION_ID
    assert injected_event.run_operation_invocation_id == _RUNTIME_OPERATION_INVOCATION_ID
    assert injected_event.step_id == "portfolio_decision"
    assert injected_event.invocation_id == _RUNTIME_TOOL_CALL_INVOCATION_ID
    assert injected_event.trace_span_id == _RUNTIME_TRACE_SPAN_ID
    assert injected_event.memory_id is None
    assert injected_event.retrieval_mode == "runtime-tool"
    assert injected_event.budget == {"limit": 5, "offset": 0, "maxCharacters": 4000}
    assert injected_event.result_snapshot["resultCount"] == 1
    assert injected_event.result_snapshot["snippets"][0]["memoryId"] == memory["memoryId"]
    assert injected_event.status_snapshot == {"status": "injected"}
    assert injected_event.injected_text is not None
    assert "Keep this insight" in injected_event.injected_text


def test_memory_runtime_tools_reject_shared_namespace_without_trusted_runtime_source() -> None:
    registry = RuntimeToolRegistry(
        [MEMORY_WRITE_TOOL_SPEC, MEMORY_LOOKUP_TOOL_SPEC],
        enabled_extension_keys=set(),
    )
    context = _runtime_context(fail_on_session=True)
    namespace_payload = {"ownerPackageKey": "pkg_alpha", "namespaceKey": "shared_research"}

    with pytest.raises(RuntimeToolError) as write_denied:
        _ = registry.dispatch(
            name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
            arguments_json=_memory_write_arguments_json({"sharedNamespace": namespace_payload}),
            granted_tool_keys={MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY},
            context=context,
        )
    with pytest.raises(RuntimeToolError) as lookup_denied:
        _ = registry.dispatch(
            name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json=json.dumps(
                {
                    "query": "shared namespace runtime",
                    "scope": None,
                    "sharedNamespace": namespace_payload,
                    "subjectRefs": None,
                    "kind": None,
                    "status": "pending",
                    "tags": None,
                    "limit": None,
                    "offset": None,
                    "maxCharacters": None,
                }
            ),
            granted_tool_keys={MEMORY_WRITE_TOOL_KEY, MEMORY_LOOKUP_TOOL_KEY},
            context=context,
        )

    assert write_denied.value.code == "agent_tool_call_invalid"
    assert lookup_denied.value.code == "agent_tool_call_invalid"
    assert "sharedNamespace" in write_denied.value.message
    assert "sharedNamespace" in lookup_denied.value.message


def test_memory_lookup_runtime_tool_rejects_unscoped_call_without_context() -> None:
    registry = RuntimeToolRegistry([MEMORY_LOOKUP_TOOL_SPEC])

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = registry.dispatch(
            name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="{}",
            granted_tool_keys={MEMORY_LOOKUP_TOOL_KEY},
            context=_runtime_context(fail_on_session=True),
        )

    assert exc_info.value.code == "agent_tool_dependency_missing"
    assert exc_info.value.message == (
        "signaldeck_memory_lookup requires at least one explicit selector or "
        "current runtime context."
    )


def test_memory_lookup_runtime_tool_service_denies_missing_lookup_grant(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "runtime_memory_lookup_without_service_grant"
    _seed_runtime_tool_capability(
        session_factory,
        key=capability_key,
        tools=[MEMORY_WRITE_TOOL_KEY],
    )
    _seed_runtime_run(session_factory)
    registry = RuntimeToolRegistry([MEMORY_LOOKUP_TOOL_SPEC])

    with pytest.raises(RuntimeToolGrantError) as exc_info:
        _ = registry.dispatch(
            name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"kind":"research.note"}',
            granted_tool_keys={MEMORY_LOOKUP_TOOL_KEY},
            context=_reports_write_runtime_context(
                session_factory,
                capability_key=capability_key,
            ),
        )

    assert exc_info.value.code == MEMORY_TOOL_ACCESS_DENIED_CODE
    assert exc_info.value.message == MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE


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
            "OpenAI response requested signaldeck_reports_lookup with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_reports_lookup arguments must be a JSON object."),
        (
            '{"unsupported":true}',
            "signaldeck_reports_lookup arguments contained unsupported fields: unsupported",
        ),
        (
            '{"source":"manual"}',
            (
                "signaldeck_reports_lookup source must be one of compiled, uploaded, "
                "external, or agent."
            ),
        ),
        (
            '{"source":"agent"}',
            None,
        ),
        ('{"ticker":123}', "signaldeck_reports_lookup string arguments must be strings."),
        ('{"limit":51}', "signaldeck_reports_lookup limit must be at most 50."),
        ('{"offset":-1}', "signaldeck_reports_lookup offset must be at least 0."),
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
            "OpenAI response requested signaldeck_positions_lookup with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_positions_lookup arguments must be a JSON object."),
        (
            '{"portfolioSlug":"reference","unsupported":true}',
            "signaldeck_positions_lookup arguments contained unsupported fields: unsupported",
        ),
        ("{}", "signaldeck_positions_lookup portfolioSlug is required."),
        ('{"portfolioSlug":123}', "signaldeck_positions_lookup portfolioSlug must be a string."),
        (
            '{"portfolioSlug":"reference","limit":"1"}',
            "signaldeck_positions_lookup limit must be an integer.",
        ),
        (
            '{"portfolioSlug":"reference","limit":201}',
            "signaldeck_positions_lookup limit must be at most 200.",
        ),
        (
            '{"portfolioSlug":"reference","offset":-1}',
            "signaldeck_positions_lookup offset must be at least 0.",
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
            "OpenAI response requested signaldeck_market_data_quote_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_market_data_quote_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_market_data_quote_lookup arguments contained "
                "unsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_market_data_quote_lookup symbols is required."),
        (
            '{"symbols":"NVDA"}',
            "signaldeck_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[123]}',
            "signaldeck_market_data_quote_lookup symbols must be an array of strings.",
        ),
        (
            '{"symbols":[""]}',
            "signaldeck_market_data_quote_lookup symbols must not contain empty values.",
        ),
        (
            '{"symbols":["NVDA"],"baseCurrency":"US"}',
            "signaldeck_market_data_quote_lookup baseCurrency must be a 3-letter ISO code.",
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
            "OpenAI response requested signaldeck_market_data_history_lookup "
            + "with invalid JSON arguments.",
        ),
        ("[]", "signaldeck_market_data_history_lookup arguments must be a JSON object."),
        (
            '{"symbols":["NVDA"],"unsupported":true}',
            (
                "signaldeck_market_data_history_lookup arguments contained "
                "unsupported fields: unsupported"
            ),
        ),
        ("{}", "signaldeck_market_data_history_lookup symbols is required."),
        (
            '{"symbols":["NVDA"],"range":"10y"}',
            "signaldeck_market_data_history_lookup range must be one of 1mo, 3mo, ytd, 1y, or max.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":"2"}',
            "signaldeck_market_data_history_lookup pointLimit must be an integer.",
        ),
        (
            '{"symbols":["NVDA"],"pointLimit":251}',
            "signaldeck_market_data_history_lookup pointLimit must be at most 250.",
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
                    "smaWindows": [20, 5, 20],
                    "rowLimit": None,
                }
            ),
            {
                "symbol": "NVDA",
                "current_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "start_date": datetime(2026, 1, 1, tzinfo=UTC),
                "end_date": datetime(2026, 1, 3, 16, tzinfo=UTC),
                "sma_windows": (20, 5),
                "row_limit": 250,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            json.dumps(
                {
                    "symbol": " nvda ",
                    "statementTypes": [" Income_Statement ", "cash_flow", "cash_flow"],
                    "periods": ["ANNUAL", "trailing_twelve_months"],
                    "statementLimit": 2,
                }
            ),
            {
                "symbol": "NVDA",
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
                "smaWindows": [2],
                "rowLimit": 3,
            },
        ),
        (
            parse_fundamentals_lookup_arguments,
            FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            {
                "symbol": "NVDA",
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
            "signaldeck_market_data_ohlcv_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["A", "B", "C", "D", "E", "F"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 3,
            },
            "signaldeck_market_data_ohlcv_lookup symbols must contain at most 5 symbols.",
        ),
        (
            parse_ohlcv_lookup_arguments,
            {
                "symbols": ["NVDA"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "rowLimit": 501,
            },
            "signaldeck_market_data_ohlcv_lookup rowLimit must be at most 500.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-02",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "smaWindows": [2],
                "rowLimit": 3,
            },
            "signaldeck_indicators_lookup endDate cannot be after currentDate.",
        ),
        (
            parse_indicators_lookup_arguments,
            {
                "symbol": "NVDA",
                "currentDate": "2026-01-03",
                "startDate": "2026-01-01",
                "endDate": "2026-01-03",
                "smaWindows": [2],
                "rowLimit": 501,
            },
            "signaldeck_indicators_lookup rowLimit must be at most 500.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "statementTypes": ["statement"],
                "periods": None,
                "statementLimit": 3,
            },
            "signaldeck_fundamentals_lookup statementTypes must use: "
            + "balance_sheet, cash_flow, income_statement.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "statementTypes": None,
                "periods": ["daily"],
                "statementLimit": 3,
            },
            "signaldeck_fundamentals_lookup periods must use: "
            + "annual, quarterly, trailing_twelve_months.",
        ),
        (
            parse_fundamentals_lookup_arguments,
            {
                "symbol": "NVDA",
                "statementTypes": None,
                "periods": None,
                "statementLimit": 13,
            },
            "signaldeck_fundamentals_lookup statementLimit must be at most 12.",
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
            "signaldeck_news_lookup startDate must be before or equal to endDate.",
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
            "signaldeck_news_lookup symbols must contain at most 5 symbols.",
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
            "signaldeck_news_lookup itemLimit must be at most 50.",
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
            "signaldeck_social_sentiment_lookup sources must use: reddit, stocktwits.",
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
            "signaldeck_social_sentiment_lookup itemLimit must be at most 50.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "transactionLimit": 2,
            },
            "signaldeck_insider_data_lookup startDate must be before or equal to endDate.",
        ),
        (
            parse_insider_data_lookup_arguments,
            {
                "symbol": "NVDA",
                "startDate": None,
                "endDate": None,
                "transactionLimit": 101,
            },
            "signaldeck_insider_data_lookup transactionLimit must be at most 100.",
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
            POSITION_LOOKUP_TOOL_SPEC,
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
    assert report_error.value.message == "signaldeck_reports_lookup limit must be at most 50."

    with pytest.raises(RuntimeToolError) as position_error:
        _ = registry.dispatch(
            name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"portfolioSlug":"reference","limit":201}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert position_error.value.message == "signaldeck_positions_lookup limit must be at most 200."

    with pytest.raises(RuntimeToolError) as quote_error:
        _ = registry.dispatch(
            name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"unsupported":true}',
            granted_tool_keys={MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert quote_error.value.message == (
        "signaldeck_market_data_quote_lookup arguments contained unsupported fields: unsupported"
    )

    with pytest.raises(RuntimeToolError) as history_error:
        _ = registry.dispatch(
            name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbols":["NVDA"],"pointLimit":251}',
            granted_tool_keys={MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert history_error.value.message == (
        "signaldeck_market_data_history_lookup pointLimit must be at most 250."
    )

    with pytest.raises(RuntimeToolError) as social_error:
        _ = registry.dispatch(
            name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"symbol":"NVDA","unsupported":true}',
            granted_tool_keys={SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert social_error.value.message == (
        "signaldeck_social_sentiment_lookup arguments contained unsupported fields: unsupported"
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
        portfolio_slug: str | None = None,
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
            "grant_policy": REPORT_LOOKUP_GRANT_POLICY,
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


def test_position_runtime_tool_dispatches_to_position_service_with_defaults_and_output_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_positions(
        self: PositionService,
        *,
        capability_references: list[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
        portfolio_slug: str,
        symbol: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PositionRead]:
        captured_calls.append(
            {
                "capability_references": capability_references,
                "grant_policy": grant_policy,
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
        "grant_policy": POSITION_LOOKUP_GRANT_POLICY,
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
                "smaWindows": [2, 5],
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
    assert rows[0]["values"] == [
        {"name": "close", "value": "119.75", "nullReason": None},
        {"name": "sma_2", "value": None, "nullReason": "warmup"},
        {"name": "sma_5", "value": None, "nullReason": "insufficient_history"},
    ]
    assert rows[1]["values"] == [
        {"name": "close", "value": "120.00", "nullReason": None},
        {"name": "sma_2", "value": "119.875", "nullReason": None},
        {"name": "sma_5", "value": None, "nullReason": "insufficient_history"},
    ]
    assert rows[2]["values"] == [
        {"name": "close", "value": "120.25", "nullReason": None},
        {"name": "sma_2", "value": "120.125", "nullReason": None},
        {"name": "sma_5", "value": None, "nullReason": "insufficient_history"},
    ]
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
    assert metrics == [
        {
            "name": "market_cap",
            "value": "1000000.50",
            "currency": "USD",
            "period": "ttm",
            "asOf": "2026-01-02T02:00:00Z",
        }
    ]
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
                "startDate": "2026-01-01T19:00:00-05:00",
                "endDate": "2026-01-02T19:00:00-05:00",
                "itemLimit": 2,
            }
        ),
        granted_tool_keys={NEWS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [
        (
            ["NVDA", "AAPL"],
            "earnings",
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
            "details": {"limit": "2"},
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
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            }
        ),
        granted_tool_keys={NEWS_LOOKUP_TOOL_KEY},
        context=_runtime_context(
            session_factory_override=session_factory,
            quote_provider=quote_provider,
        ),
    )

    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert quote_provider.news_calls == [(["NVDA"], "earnings", None, None, 3)]
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
