from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pytest


def test_runner_parses_positions_renders_report_and_builds_trade_decisions() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_text)
            self.calls.append((symbol, position_quantity))
            if symbol == "AAPL":
                return LangGraphSymbolAnalysis(label="BUY", summary="Momentum is improving.")
            return LangGraphSymbolAnalysis(label="UNDERWEIGHT", summary="Risk is elevated.")

    runner = BacktestLangGraphRunner(analyzer=FakeAnalyzer())

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=42,
            cycle_date=date(2024, 6, 17),
            prompt_report_slug="prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-06-17)\n\n"
                "## System\n"
                "Today is 2024-06-17.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Balances:\n"
                "- Cash: 10000.00 USD (DEPOSIT)\n"
                "Positions:\n"
                "- AAPL: 5 shares @ 180.00 USD\n"
                "- MSFT: 2 shares @ 410.00 USD\n\n"
                "Prior reports:\n"
                "- None"
            ),
            authored_entry_prompt_body="# authored entry prompt body",
            compiled_entry_prompt_body="# compiled entry prompt body",
            execution_context_body="# execution context body",
            full_user_prompt="",
        )
    )

    assert result.report_content == (
        "# LangGraph Analysis\n\n"
        "- Backtest ID: 42\n"
        "- Cycle date: 2024-06-17\n"
        "- Prompt report slug: prompt_report\n\n"
        "## AAPL\n"
        "- Label: BUY\n"
        "- Held quantity: 5\n"
        "- Summary: Momentum is improving.\n\n"
        "## MSFT\n"
        "- Label: UNDERWEIGHT\n"
        "- Held quantity: 2\n"
        "- Summary: Risk is elevated."
    )
    assert [
        (decision.symbol, decision.action, decision.quantity) for decision in result.decisions
    ] == [
        ("AAPL", "BUY", 1),
        ("MSFT", "SELL", 2),
    ]


def test_runner_rejects_missing_expanded_fields_by_default() -> None:
    from app.langgraph.runner import BacktestLangGraphCapabilityInputs, BacktestLangGraphRequest

    request = BacktestLangGraphRequest(
        backtest_id=1,
        cycle_date=date(2024, 1, 1),
        prompt_report_slug="slug",
        prompt_report="# report",
    )

    assert request.authored_entry_prompt_body == ""
    assert request.compiled_entry_prompt_body == ""
    assert request.execution_context_body == ""
    assert request.full_user_prompt == ""
    assert request.execution_mode == "structured_output"
    assert request.resolved_capability_inputs == BacktestLangGraphCapabilityInputs()


def test_tool_enabled_execution_mode_uses_serial_tool_loop_and_returns_ordered_trace() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphCapabilityInputs,
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        BacktestLangGraphToolAdapter,
        BacktestLangGraphToolRuntime,
        LangGraphSymbolAnalysis,
    )
    from app.langgraph.seeds import get_backtest_pattern_spec

    class FakeAnalyzer:
        def __init__(self) -> None:
            self.analyze_calls = 0
            self.tool_requests: list[dict[str, Any]] = []

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            self.analyze_calls += 1
            raise AssertionError(
                "tool-enabled execution should not use the structured analyzer path"
            )

        def create_tool_enabled_response(
            self,
            *,
            input_items: list[dict[str, object]],
            tools: list[dict[str, object]],
            previous_response_id: str | None,
            parallel_tool_calls: bool,
            text_format: dict[str, object],
        ) -> Any:
            self.tool_requests.append(
                {
                    "input_items": input_items,
                    "tools": tools,
                    "previous_response_id": previous_response_id,
                    "parallel_tool_calls": parallel_tool_calls,
                    "text_format": text_format,
                }
            )
            if previous_response_id is None:
                return SimpleNamespace(
                    id="resp_1",
                    output=[
                        {
                            "type": "function_call",
                            "name": "ledger_report_lookup",
                            "arguments": '{"slug":"report-123"}',
                            "call_id": "call_1",
                        }
                    ],
                )
            assert previous_response_id == "resp_1"
            assert input_items == [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": json.dumps(
                        {"slug": "report-123", "content": "Supporting report content."},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            ]
            return SimpleNamespace(
                id="resp_2",
                output=[],
                output_text=(
                    '{"analyses":[{"symbol":"NVDA","label":"BUY",'
                    '"summary":"Use the supporting report content."}]}'
                ),
            )

        def extract_responses_output_text(self, response: Any) -> str:
            return str(response.output_text)

    baseline_spec = get_backtest_pattern_spec("seeded_internal_backtest_v1")
    tool_enabled_spec = get_backtest_pattern_spec("seeded_internal_backtest_tool_enabled_v1")

    assert baseline_spec is not None
    assert tool_enabled_spec is not None

    resolved_tool_ids = tuple(sorted(set(tool_enabled_spec.default_tool_ids)))
    tool_runtime = BacktestLangGraphToolRuntime(
        adapters=(
            BacktestLangGraphToolAdapter(
                tool_id="ledger.cycle_context_lookup",
                description="Read prepared cycle context artifacts.",
                parameters_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                invoke=lambda arguments: (_ for _ in ()).throw(
                    AssertionError(f"unexpected cycle-context lookup: {arguments}")
                ),
            ),
            BacktestLangGraphToolAdapter(
                tool_id="ledger.orchestration_catalog_lookup",
                description="Read orchestration catalog data.",
                parameters_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                invoke=lambda arguments: (_ for _ in ()).throw(
                    AssertionError(f"unexpected orchestration lookup: {arguments}")
                ),
            ),
            BacktestLangGraphToolAdapter(
                tool_id="ledger.report_lookup",
                description="Read report content by exact slug.",
                parameters_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                invoke=lambda arguments: {
                    "slug": str(arguments["slug"]),
                    "content": "Supporting report content.",
                },
            ),
        )
    )

    request_kwargs = {
        "backtest_id": 77,
        "cycle_date": date(2024, 7, 1),
        "prompt_report_slug": "mode_prompt_report",
        "prompt_report": (
            "# Cycle Prompt (2024-07-01)\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Positions:\n"
            "- NVDA: 3 shares @ 1200.00 USD\n"
        ),
        "resolved_capability_inputs": BacktestLangGraphCapabilityInputs(tool_ids=resolved_tool_ids),
        "tool_runtime": tool_runtime,
    }
    analyzer = FakeAnalyzer()
    runner = BacktestLangGraphRunner(analyzer=analyzer)

    tool_enabled_result = runner.run_cycle(
        BacktestLangGraphRequest(
            **request_kwargs,
            execution_mode=tool_enabled_spec.execution_mode,
        )
    )

    assert baseline_spec.execution_mode == "structured_output"
    assert tool_enabled_spec.execution_mode == "tool_enabled"
    assert analyzer.analyze_calls == 0
    assert [request["parallel_tool_calls"] for request in analyzer.tool_requests] == [False, False]
    assert [decision.action for decision in tool_enabled_result.decisions] == ["BUY"]
    assert tool_enabled_result.report_content == (
        "# LangGraph Analysis\n\n"
        "- Backtest ID: 77\n"
        "- Cycle date: 2024-07-01\n"
        "- Prompt report slug: mode_prompt_report\n\n"
        "## NVDA\n"
        "- Label: BUY\n"
        "- Held quantity: 3\n"
        "- Summary: Use the supporting report content."
    )
    assert len(tool_enabled_result.tool_call_trace) == 1
    assert tool_enabled_result.tool_call_trace[0]["call_index"] == 0
    assert tool_enabled_result.tool_call_trace[0]["tool_id"] == "ledger.report_lookup"
    assert tool_enabled_result.tool_call_trace[0]["status"] == "success"
    assert tool_enabled_result.approval_trace == "not_required"
    assert isinstance(tool_enabled_result.tool_call_trace[0]["latency_ms"], int)
    assert len(tool_enabled_result.tool_call_trace[0]["argument_hash"]) == 64
    assert len(tool_enabled_result.tool_call_trace[0]["result_hash"]) == 64


def test_structured_output_patterns_ignore_tool_enabled_responses_surface() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class HybridAnalyzer:
        def __init__(self) -> None:
            self.analysis_calls: list[str] = []
            self.tool_calls = 0

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_text, position_quantity)
            self.analysis_calls.append(symbol)
            return LangGraphSymbolAnalysis(label="BUY", summary=f"Add to {symbol}.")

        def create_tool_enabled_response(
            self,
            *,
            input_items: list[dict[str, object]],
            tools: list[dict[str, object]],
            previous_response_id: str | None,
            parallel_tool_calls: bool,
            text_format: dict[str, object],
        ) -> Any:
            _ = (input_items, tools, previous_response_id, parallel_tool_calls, text_format)
            self.tool_calls += 1
            raise AssertionError("structured-output execution should not call tool-enabled APIs")

        def extract_responses_output_text(self, response: Any) -> str:
            _ = response
            raise AssertionError("structured-output execution should not extract tool responses")

    request = BacktestLangGraphRequest(
        backtest_id=78,
        cycle_date=date(2024, 7, 1),
        prompt_report_slug="structured_output_prompt_report",
        prompt_report=(
            "# Cycle Prompt (2024-07-01)\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Positions:\n"
            "- NVDA: 3 shares @ 1200.00 USD\n"
        ),
    )

    seeded_analyzer = HybridAnalyzer()
    seeded_result = build_backtest_langgraph_runner(
        pattern_key="seeded_internal_backtest_v1",
        analyzer=seeded_analyzer,
    ).run_cycle(request)
    reviewer_analyzer = HybridAnalyzer()
    reviewer_result = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=reviewer_analyzer,
    ).run_cycle(request)

    assert seeded_analyzer.analysis_calls == ["NVDA"]
    assert seeded_analyzer.tool_calls == 0
    assert reviewer_analyzer.analysis_calls == ["NVDA"]
    assert reviewer_analyzer.tool_calls == 0
    assert seeded_result.tool_call_trace == []
    assert reviewer_result.tool_call_trace == []
    assert seeded_result.approval_trace == "not_required"
    assert reviewer_result.approval_trace == "not_required"
    assert [(decision.action, decision.quantity) for decision in seeded_result.decisions] == [
        ("BUY", 1)
    ]
    assert [(decision.action, decision.quantity) for decision in reviewer_result.decisions] == [
        ("HOLD", None)
    ]
    assert "Topology: seeded_internal_backtest_v1" in seeded_result.report_content
    assert "Topology: analyst_reviewer_v1" in reviewer_result.report_content


def test_execution_mode_rejects_unknown_runtime_mode() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest

    with pytest.raises(ValueError, match="Unsupported execution mode"):
        BacktestLangGraphRequest(
            backtest_id=1,
            cycle_date=date(2024, 1, 1),
            prompt_report_slug="slug",
            prompt_report="# report",
            execution_mode=cast(Any, "invalid_mode"),
        )


def test_capability_payload_is_required_for_tool_enabled_execution_mode() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest

    with pytest.raises(ValueError, match="requires resolved_capability_inputs"):
        BacktestLangGraphRequest(
            backtest_id=1,
            cycle_date=date(2024, 1, 1),
            prompt_report_slug="slug",
            prompt_report="# report",
            execution_mode="tool_enabled",
        )


def test_tool_runtime_is_required_for_tool_enabled_execution_mode() -> None:
    from app.langgraph.runner import BacktestLangGraphCapabilityInputs, BacktestLangGraphRequest

    with pytest.raises(ValueError, match="requires tool_runtime"):
        BacktestLangGraphRequest(
            backtest_id=1,
            cycle_date=date(2024, 1, 1),
            prompt_report_slug="slug",
            prompt_report="# report",
            execution_mode="tool_enabled",
            resolved_capability_inputs=BacktestLangGraphCapabilityInputs(
                tool_ids=("ledger.report_lookup",)
            ),
        )


def test_tool_trace_failure_preserves_partial_trace_for_fail_closed_handling() -> None:
    from app.core.errors import business_rule_error
    from app.langgraph.runner import (
        BacktestLangGraphCapabilityInputs,
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        BacktestLangGraphToolAdapter,
        BacktestLangGraphToolExecutionError,
        BacktestLangGraphToolRuntime,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            raise AssertionError("tool-enabled execution should not use analyze_symbol")

        def create_tool_enabled_response(
            self,
            *,
            input_items: list[dict[str, object]],
            tools: list[dict[str, object]],
            previous_response_id: str | None,
            parallel_tool_calls: bool,
            text_format: dict[str, object],
        ) -> Any:
            _ = (input_items, tools, previous_response_id, parallel_tool_calls, text_format)
            return SimpleNamespace(
                id="resp_fail",
                output=[
                    {
                        "type": "function_call",
                        "name": "ledger_report_lookup",
                        "arguments": '{"slug":"missing-report"}',
                        "call_id": "call_fail",
                    }
                ],
            )

        def extract_responses_output_text(self, response: Any) -> str:
            _ = response
            raise AssertionError("tool failure path should not request final output text")

    runner = BacktestLangGraphRunner(analyzer=FakeAnalyzer())

    with pytest.raises(
        BacktestLangGraphToolExecutionError, match="Tool ledger.report_lookup failed"
    ) as exc:
        runner.run_cycle(
            BacktestLangGraphRequest(
                backtest_id=88,
                cycle_date=date(2024, 7, 1),
                prompt_report_slug="failed_prompt_report",
                prompt_report=(
                    "# Cycle Prompt (2024-07-01)\n\n"
                    "## User\n"
                    "Portfolio state:\n"
                    "Positions:\n"
                    "- NVDA: 3 shares @ 1200.00 USD\n"
                ),
                execution_mode="tool_enabled",
                resolved_capability_inputs=BacktestLangGraphCapabilityInputs(
                    tool_ids=("ledger.report_lookup",)
                ),
                tool_runtime=BacktestLangGraphToolRuntime(
                    adapters=(
                        BacktestLangGraphToolAdapter(
                            tool_id="ledger.report_lookup",
                            description="Read report content by exact slug.",
                            parameters_schema={
                                "type": "object",
                                "properties": {"slug": {"type": "string"}},
                                "required": ["slug"],
                                "additionalProperties": False,
                            },
                            invoke=lambda arguments: (_ for _ in ()).throw(
                                business_rule_error(
                                    "not_found", f"Report {arguments['slug']} not found"
                                )
                            ),
                        ),
                    )
                ),
            )
        )

    assert exc.value.tool_call_trace == [
        {
            "call_index": 0,
            "tool_id": "ledger.report_lookup",
            "status": "error",
            "latency_ms": exc.value.tool_call_trace[0]["latency_ms"],
            "argument_hash": exc.value.tool_call_trace[0]["argument_hash"],
            "error_code": "not_found",
        }
    ]
    assert exc.value.approval_trace == "not_required"
    assert isinstance(exc.value.tool_call_trace[0]["latency_ms"], int)
    assert len(exc.value.tool_call_trace[0]["argument_hash"]) == 64


def test_connector_execution_reuses_tool_runtime_and_records_ordered_approval_trace() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphCapabilityInputs,
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        BacktestLangGraphToolAdapter,
        BacktestLangGraphToolRuntime,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def __init__(self) -> None:
            self.tool_requests: list[dict[str, Any]] = []

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            raise AssertionError("connector-enabled execution should not use analyze_symbol")

        def create_tool_enabled_response(
            self,
            *,
            input_items: list[dict[str, object]],
            tools: list[dict[str, object]],
            previous_response_id: str | None,
            parallel_tool_calls: bool,
            text_format: dict[str, object],
        ) -> Any:
            self.tool_requests.append(
                {
                    "input_items": input_items,
                    "tools": tools,
                    "previous_response_id": previous_response_id,
                    "parallel_tool_calls": parallel_tool_calls,
                    "text_format": text_format,
                }
            )
            if previous_response_id is None:
                return SimpleNamespace(
                    id="resp_connector_1",
                    output=[
                        {
                            "type": "function_call",
                            "name": "ledger_mcp_market_data",
                            "arguments": '{"symbol":"NVDA"}',
                            "call_id": "call_connector_1",
                        }
                    ],
                )
            if previous_response_id == "resp_connector_1":
                assert input_items == [
                    {
                        "type": "function_call_output",
                        "call_id": "call_connector_1",
                        "output": json.dumps(
                            {
                                "market_data": {"close": "1200.00"},
                                "symbol": "NVDA",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                ]
                return SimpleNamespace(
                    id="resp_connector_2",
                    output=[
                        {
                            "type": "function_call",
                            "name": "ledger_report_lookup",
                            "arguments": '{"slug":"supporting-report"}',
                            "call_id": "call_connector_2",
                        }
                    ],
                )
            assert previous_response_id == "resp_connector_2"
            assert input_items == [
                {
                    "type": "function_call_output",
                    "call_id": "call_connector_2",
                    "output": json.dumps(
                        {"content": "Supporting report content.", "slug": "supporting-report"},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            ]
            return SimpleNamespace(
                id="resp_connector_3",
                output=[],
                output_text=(
                    '{"analyses":[{"symbol":"NVDA","label":"BUY",'
                    '"summary":"Connector and report context agree."}]}'
                ),
            )

        def extract_responses_output_text(self, response: Any) -> str:
            return str(response.output_text)

    runner = BacktestLangGraphRunner(analyzer=FakeAnalyzer())
    request = BacktestLangGraphRequest(
        backtest_id=90,
        cycle_date=date(2024, 7, 1),
        prompt_report_slug="connector_prompt_report",
        prompt_report=(
            "# Cycle Prompt (2024-07-01)\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Positions:\n"
            "- NVDA: 3 shares @ 1200.00 USD\n"
        ),
        execution_mode="tool_enabled",
        resolved_capability_inputs=BacktestLangGraphCapabilityInputs(
            tool_ids=("ledger.report_lookup",),
            connector_ids=("ledger.mcp.market_data",),
        ),
        tool_runtime=BacktestLangGraphToolRuntime(
            adapters=(
                BacktestLangGraphToolAdapter(
                    tool_id="ledger.report_lookup",
                    description="Read report content by exact slug.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"slug": {"type": "string"}},
                        "required": ["slug"],
                        "additionalProperties": False,
                    },
                    invoke=lambda arguments: {
                        "slug": str(arguments["slug"]),
                        "content": "Supporting report content.",
                    },
                ),
                BacktestLangGraphToolAdapter(
                    tool_id="ledger.mcp.market_data",
                    description="Read trusted market data connector output.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"symbol": {"type": "string"}},
                        "required": ["symbol"],
                        "additionalProperties": False,
                    },
                    invoke=lambda arguments: {
                        "symbol": str(arguments["symbol"]).upper(),
                        "market_data": {"close": "1200.00"},
                    },
                    approval_required=True,
                    approval_granted=True,
                    approval_metadata={"kind": "connector", "transport": "mcp"},
                ),
            )
        ),
    )

    result = runner.run_cycle(request)

    assert [entry["tool_id"] for entry in result.tool_call_trace] == [
        "ledger.mcp.market_data",
        "ledger.report_lookup",
    ]
    assert [entry["call_index"] for entry in result.tool_call_trace] == [0, 1]
    assert result.approval_trace == [
        {
            "call_index": 0,
            "tool_id": "ledger.mcp.market_data",
            "status": "approved",
            "kind": "connector",
            "transport": "mcp",
        }
    ]
    assert [decision.action for decision in result.decisions] == ["BUY"]


def test_connector_approval_failure_preserves_partial_approval_context() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphCapabilityInputs,
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        BacktestLangGraphToolAdapter,
        BacktestLangGraphToolExecutionError,
        BacktestLangGraphToolRuntime,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            raise AssertionError("connector-enabled execution should not use analyze_symbol")

        def create_tool_enabled_response(
            self,
            *,
            input_items: list[dict[str, object]],
            tools: list[dict[str, object]],
            previous_response_id: str | None,
            parallel_tool_calls: bool,
            text_format: dict[str, object],
        ) -> Any:
            _ = (input_items, tools, previous_response_id, parallel_tool_calls, text_format)
            return SimpleNamespace(
                id="resp_connector_fail",
                output=[
                    {
                        "type": "function_call",
                        "name": "ledger_mcp_market_data",
                        "arguments": '{"symbol":"NVDA"}',
                        "call_id": "call_connector_fail",
                    }
                ],
            )

        def extract_responses_output_text(self, response: Any) -> str:
            _ = response
            raise AssertionError("connector approval failure should not request final output text")

    runner = BacktestLangGraphRunner(analyzer=FakeAnalyzer())

    with pytest.raises(
        BacktestLangGraphToolExecutionError,
        match="Connector ledger.mcp.market_data is not approved for execution",
    ) as exc:
        runner.run_cycle(
            BacktestLangGraphRequest(
                backtest_id=91,
                cycle_date=date(2024, 7, 1),
                prompt_report_slug="connector_fail_prompt_report",
                prompt_report=(
                    "# Cycle Prompt (2024-07-01)\n\n"
                    "## User\n"
                    "Portfolio state:\n"
                    "Positions:\n"
                    "- NVDA: 3 shares @ 1200.00 USD\n"
                ),
                execution_mode="tool_enabled",
                resolved_capability_inputs=BacktestLangGraphCapabilityInputs(
                    connector_ids=("ledger.mcp.market_data",)
                ),
                tool_runtime=BacktestLangGraphToolRuntime(
                    adapters=(
                        BacktestLangGraphToolAdapter(
                            tool_id="ledger.mcp.market_data",
                            description="Read trusted market data connector output.",
                            parameters_schema={
                                "type": "object",
                                "properties": {"symbol": {"type": "string"}},
                                "required": ["symbol"],
                                "additionalProperties": False,
                            },
                            invoke=lambda arguments: (_ for _ in ()).throw(
                                AssertionError(
                                    "connector invoke should be blocked before "
                                    f"execution: {arguments}"
                                )
                            ),
                            approval_required=True,
                            approval_granted=False,
                            approval_metadata={"kind": "connector", "transport": "mcp"},
                        ),
                    )
                ),
            )
        )

    assert exc.value.tool_call_trace == []
    assert exc.value.approval_trace == [
        {
            "call_index": 0,
            "tool_id": "ledger.mcp.market_data",
            "status": "denied",
            "kind": "connector",
            "transport": "mcp",
        }
    ]


def test_runner_uses_full_user_prompt_as_authoritative_execution_input_when_present() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = cycle_date
            self.calls.append((symbol, prompt_text, position_quantity))
            return LangGraphSymbolAnalysis(label="HOLD", summary="Use the runtime handoff text.")

    analyzer = FakeAnalyzer()
    runner = BacktestLangGraphRunner(analyzer=analyzer)

    full_user_prompt = "# Runtime handoff\n\nPositions:\n- NVDA: 3 shares @ 1200.00 USD\n"

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=42,
            cycle_date=date(2024, 6, 17),
            prompt_report_slug="prompt_report",
            prompt_report=("Positions:\n- AAPL: 5 shares @ 180.00 USD\n"),
            authored_entry_prompt_body="# authored entry prompt body",
            compiled_entry_prompt_body="# compiled entry prompt body",
            execution_context_body="# execution context body",
            full_user_prompt=full_user_prompt,
        )
    )

    assert result.report_content == (
        "# LangGraph Analysis\n\n"
        "- Backtest ID: 42\n"
        "- Cycle date: 2024-06-17\n"
        "- Prompt report slug: prompt_report\n\n"
        "## NVDA\n"
        "- Label: HOLD\n"
        "- Held quantity: 3\n"
        "- Summary: Use the runtime handoff text."
    )
    assert [
        (decision.symbol, decision.action, decision.quantity) for decision in result.decisions
    ] == [("NVDA", "HOLD", None)]
    assert analyzer.calls == [("NVDA", full_user_prompt, "3")]


def test_seeded_runner_smoke_executes_seeded_agents_and_topology() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import (
        SEEDED_AGENT_SPECS,
        SEEDED_TOPOLOGY,
        build_seeded_langgraph_runner,
    )

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="HOLD", summary=f"Keep {symbol} unchanged.")

    runner = build_seeded_langgraph_runner(analyzer=FakeAnalyzer())

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=99,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="seeded_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## System\n"
                "Today is 2024-07-01.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert [agent.key for agent in SEEDED_AGENT_SPECS] == [
        "position_analyst",
        "risk_reviewer",
        "decision_writer",
    ]
    assert SEEDED_TOPOLOGY.key == "seeded_internal_backtest_v1"
    assert SEEDED_TOPOLOGY.agent_order == ("position_analyst", "decision_writer")
    assert "Topology: seeded_internal_backtest_v1" in result.report_content
    assert "Agents: position_analyst, decision_writer" in result.report_content
    assert [
        (decision.symbol, decision.action, decision.quantity) for decision in result.decisions
    ] == [("NVDA", "HOLD", None)]


def test_analyst_reviewer_pattern_applies_conservative_review_before_decisions() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="BUY", summary=f"Add to {symbol}.")

    runner = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    )

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=100,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="reviewer_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert "Topology: analyst_reviewer_v1" in result.report_content
    assert "Agents: position_analyst, risk_reviewer, decision_writer" in result.report_content
    assert "Conservative review applied: BUY -> HOLD" in result.report_content
    assert [
        (decision.symbol, decision.action, decision.quantity, decision.reasoning)
        for decision in result.decisions
    ] == [
        (
            "NVDA",
            "HOLD",
            None,
            "HOLD: Add to NVDA. Conservative review applied: BUY -> HOLD.",
        )
    ]


def test_seeded_and_reviewer_patterns_diverge_on_same_input() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="BUY", summary=f"Add to {symbol}.")

    request = BacktestLangGraphRequest(
        backtest_id=101,
        cycle_date=date(2024, 7, 1),
        prompt_report_slug="paired_prompt_report",
        prompt_report=(
            "# Cycle Prompt (2024-07-01)\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Positions:\n"
            "- NVDA: 3 shares @ 1200.00 USD\n"
        ),
    )

    seeded_result = build_backtest_langgraph_runner(
        pattern_key="seeded_internal_backtest_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(request)
    reviewer_result = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(request)

    assert [(decision.action, decision.quantity) for decision in seeded_result.decisions] == [
        ("BUY", 1)
    ]
    assert [(decision.action, decision.quantity) for decision in reviewer_result.decisions] == [
        ("HOLD", None)
    ]


def test_runner_configuration_stays_distinct_for_seeded_and_reviewer_patterns() -> None:
    from app.langgraph.runner import LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="HOLD", summary="No-op analyzer.")

    seeded_runner = build_backtest_langgraph_runner(
        pattern_key="seeded_internal_backtest_v1",
        analyzer=FakeAnalyzer(),
    )
    reviewer_runner = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    )

    assert seeded_runner.topology_key == "seeded_internal_backtest_v1"
    assert seeded_runner.agent_keys == ("position_analyst", "decision_writer")
    assert seeded_runner.review_mode == "none"

    assert reviewer_runner.topology_key == "analyst_reviewer_v1"
    assert reviewer_runner.agent_keys == (
        "position_analyst",
        "risk_reviewer",
        "decision_writer",
    )
    assert reviewer_runner.review_mode == "conservative"


def test_analyst_reviewer_pattern_converts_overweight_to_hold() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="OVERWEIGHT", summary="Build the position.")

    result = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(
        BacktestLangGraphRequest(
            backtest_id=102,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="overweight_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert [(decision.action, decision.quantity) for decision in result.decisions] == [
        ("HOLD", None)
    ]
    assert "Conservative review applied: OVERWEIGHT -> HOLD" in result.report_content


def test_live_analyzer_falls_back_when_structured_output_parser_is_incompatible(
    monkeypatch,
) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeStructuredInvoker:
        def invoke(self, messages):
            _ = messages
            raise ValueError(
                "Structured Output response does not have a 'parsed' field nor a 'refusal' field"
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            _ = schema
            return FakeStructuredInvoker()

        def invoke(self, messages):
            _ = messages
            return SimpleNamespace(content='{"label":"HOLD","summary":"Keep NVDA unchanged."}')

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
    )
    monkeypatch.setattr(analyzer, "_get_llm", lambda: FakeLLM())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_text="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "HOLD"
    assert analysis.summary == "Keep NVDA unchanged."


def test_live_analyzer_uses_responses_api_with_explicit_input_format(monkeypatch) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeStructuredInvoker:
        def invoke(self, messages):
            _ = messages
            raise ValueError(
                "Structured Output response does not have a 'parsed' field nor a 'refusal' field"
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            _ = schema
            return FakeStructuredInvoker()

        def invoke(self, messages):
            _ = messages
            return SimpleNamespace(content="")

    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta='{"label":"BUY",'),
                    SimpleNamespace(
                        type="response.output_text.delta", delta='"summary":"Add NVDA."}'
                    ),
                    SimpleNamespace(
                        type="response.output_text.done",
                        text='{"label":"BUY","summary":"Add NVDA."}',
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(id="resp_test", status="completed"),
                    ),
                ]
            )

    class FakeOpenAIClient:
        def __init__(self) -> None:
            self.responses = FakeResponsesAPI()

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
        api_mode="responses",
    )
    monkeypatch.setattr(analyzer, "_get_llm", lambda: FakeLLM())
    monkeypatch.setattr(analyzer, "_get_openai_client", lambda: FakeOpenAIClient())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_text="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "BUY"
    assert analysis.summary == "Add NVDA."
    assert captured["kwargs"] == {
        "model": "gpt-5.4-mini",
        "reasoning": {"effort": "none"},
        "stream": True,
        "text": {"format": {"type": "json_object"}},
        "input": [
            {
                "type": "message",
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You analyze one held portfolio position for a historical backtest. "
                            "Use only the information provided in the execution prompt. "
                            "Do not invent data from after the cycle date. "
                            "Return a normalized label and a concise summary. "
                            'Respond as JSON with keys "label" and "summary".'
                        ),
                    }
                ],
            },
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Cycle date: 2024-07-01\n"
                            "Held symbol: NVDA\n"
                            "Held quantity: 3\n\n"
                            "Execution prompt:\n"
                            "# Prompt"
                        ),
                    }
                ],
            },
        ],
    }


def test_live_analyzer_normalizes_lowercase_label_from_streamed_responses(monkeypatch) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeResponsesAPI:
        def create(self, **kwargs):
            _ = kwargs
            return iter(
                [
                    SimpleNamespace(
                        type="response.output_text.done",
                        text='{"label":"hold","summary":"Keep NVDA unchanged."}',
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(id="resp_test", status="completed"),
                    ),
                ]
            )

    class FakeOpenAIClient:
        def __init__(self) -> None:
            self.responses = FakeResponsesAPI()

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
        api_mode="responses",
    )
    monkeypatch.setattr(analyzer, "_get_openai_client", lambda: FakeOpenAIClient())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_text="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "HOLD"
    assert analysis.summary == "Keep NVDA unchanged."
