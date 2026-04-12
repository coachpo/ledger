from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol, TypedDict, cast

# pyright: reportMissingImports=false
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai import OpenAI
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.backtest import TradeDecision

_FIXED_BUY_QUANTITY = 1
_TOOL_ENABLED_MAX_TURNS = 12
_POSITION_LINE_RE = re.compile(r"^-\s*(?P<symbol>[^:]+):\s*(?P<quantity>[^\s]+)\s+shares\s+@\s+.+$")
BacktestExecutionMode = Literal["structured_output", "tool_enabled"]


@dataclass(frozen=True)
class HeldPosition:
    symbol: str
    quantity_text: str
    quantity: Decimal


@dataclass(frozen=True)
class LangGraphSymbolAnalysis:
    label: str
    summary: str


@dataclass(frozen=True)
class PositionAnalysis:
    position: HeldPosition
    analysis: LangGraphSymbolAnalysis


@dataclass(frozen=True, init=False)
class BacktestLangGraphCapabilityInputs:
    tool_ids: tuple[str, ...]
    bundle_keys: tuple[str, ...]
    connector_ids: tuple[str, ...]

    def __init__(
        self,
        tool_ids: tuple[str, ...] = (),
        bundle_keys: tuple[str, ...] = (),
        connector_ids: tuple[str, ...] = (),
    ) -> None:
        object.__setattr__(self, "tool_ids", tool_ids)
        object.__setattr__(self, "bundle_keys", bundle_keys)
        object.__setattr__(self, "connector_ids", connector_ids)


@dataclass(frozen=True, init=False)
class BacktestLangGraphToolAdapter:
    tool_id: str
    description: str
    parameters_schema: dict[str, Any]
    invoke: Callable[[dict[str, Any]], Any]
    approval_required: bool
    approval_granted: bool
    approval_metadata: dict[str, Any]

    def __init__(
        self,
        *,
        tool_id: str,
        description: str,
        parameters_schema: dict[str, Any],
        invoke: Callable[[dict[str, Any]], Any],
        approval_required: bool = False,
        approval_granted: bool = True,
        approval_metadata: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "parameters_schema", parameters_schema)
        object.__setattr__(self, "invoke", invoke)
        object.__setattr__(self, "approval_required", approval_required)
        object.__setattr__(self, "approval_granted", approval_granted)
        object.__setattr__(self, "approval_metadata", dict(approval_metadata or {}))


@dataclass(frozen=True, init=False)
class BacktestLangGraphToolRuntime:
    adapters: tuple[BacktestLangGraphToolAdapter, ...]

    def __init__(self, adapters: tuple[BacktestLangGraphToolAdapter, ...] = ()) -> None:
        tool_ids = tuple(adapter.tool_id for adapter in adapters)
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("tool_runtime adapters must use unique tool_ids")
        object.__setattr__(self, "adapters", adapters)

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return tuple(adapter.tool_id for adapter in self.adapters)


@dataclass(frozen=True, init=False)
class BacktestLangGraphRequest:
    backtest_id: int
    cycle_date: date
    prompt_report_slug: str
    prompt_report: str
    authored_entry_prompt_body: str
    compiled_entry_prompt_body: str
    execution_context_body: str
    full_user_prompt: str
    resolved_mentions: tuple[dict[str, Any], ...]
    orchestration_pattern_key: str
    mentioned_target_outputs: tuple[str, ...]
    execution_mode: BacktestExecutionMode
    resolved_capability_inputs: BacktestLangGraphCapabilityInputs
    tool_runtime: BacktestLangGraphToolRuntime

    def __init__(
        self,
        backtest_id: int,
        cycle_date: date,
        prompt_report_slug: str,
        prompt_report: str,
        authored_entry_prompt_body: str = "",
        compiled_entry_prompt_body: str = "",
        execution_context_body: str = "",
        full_user_prompt: str = "",
        resolved_mentions: tuple[dict[str, Any], ...] = (),
        orchestration_pattern_key: str = "",
        mentioned_target_outputs: tuple[str, ...] = (),
        execution_mode: BacktestExecutionMode = "structured_output",
        resolved_capability_inputs: BacktestLangGraphCapabilityInputs | None = None,
        tool_runtime: BacktestLangGraphToolRuntime | None = None,
    ) -> None:
        if execution_mode not in {"structured_output", "tool_enabled"}:
            raise ValueError(f"Unsupported execution mode: {execution_mode}")
        if resolved_capability_inputs is None:
            if execution_mode == "tool_enabled":
                raise ValueError("tool_enabled execution mode requires resolved_capability_inputs")
            resolved_capability_inputs = BacktestLangGraphCapabilityInputs()
        if tool_runtime is None:
            if execution_mode == "tool_enabled":
                raise ValueError("tool_enabled execution mode requires tool_runtime")
            tool_runtime = BacktestLangGraphToolRuntime()
        if execution_mode == "tool_enabled" and tool_runtime.tool_ids != (
            *resolved_capability_inputs.tool_ids,
            *resolved_capability_inputs.connector_ids,
        ):
            raise ValueError(
                "tool_enabled tool_runtime must match resolved_capability_inputs "
                "tool_ids + connector_ids"
            )

        object.__setattr__(self, "backtest_id", backtest_id)
        object.__setattr__(self, "cycle_date", cycle_date)
        object.__setattr__(self, "prompt_report_slug", prompt_report_slug)
        object.__setattr__(self, "prompt_report", prompt_report)
        object.__setattr__(self, "authored_entry_prompt_body", authored_entry_prompt_body)
        object.__setattr__(self, "compiled_entry_prompt_body", compiled_entry_prompt_body)
        object.__setattr__(self, "execution_context_body", execution_context_body)
        object.__setattr__(self, "full_user_prompt", full_user_prompt)
        object.__setattr__(self, "resolved_mentions", resolved_mentions)
        object.__setattr__(self, "orchestration_pattern_key", orchestration_pattern_key)
        object.__setattr__(self, "mentioned_target_outputs", mentioned_target_outputs)
        object.__setattr__(self, "execution_mode", execution_mode)
        object.__setattr__(self, "resolved_capability_inputs", resolved_capability_inputs)
        object.__setattr__(self, "tool_runtime", tool_runtime)


@dataclass(frozen=True)
class BacktestLangGraphResult:
    report_content: str
    decisions: list[TradeDecision]
    tool_call_trace: list[dict[str, Any]] = field(default_factory=list)
    approval_trace: Any = "not_required"


class BacktestLangGraphToolExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        tool_call_trace: list[dict[str, Any]],
        approval_trace: Any = "not_required",
    ) -> None:
        super().__init__(message)
        self.tool_call_trace = list(tool_call_trace)
        self.approval_trace = approval_trace


class BacktestSymbolAnalyzer(Protocol):
    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_text: str,
        position_quantity: str,
    ) -> LangGraphSymbolAnalysis: ...


class ToolEnabledResponsesAnalyzer(Protocol):
    def create_tool_enabled_response(
        self,
        *,
        input_items: list[dict[str, object]],
        tools: list[dict[str, object]],
        previous_response_id: str | None,
        parallel_tool_calls: bool,
        text_format: dict[str, object],
    ) -> Any: ...

    def extract_responses_output_text(self, response: Any) -> str: ...


class _LiveAnalysisResponse(BaseModel):
    label: Literal["BUY", "SELL", "HOLD", "OVERWEIGHT", "UNDERWEIGHT"] = Field(
        description="Normalized portfolio action label."
    )
    summary: str = Field(min_length=1, description="Concise symbol-specific reasoning.")

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class _ToolEnabledAnalysisResponseItem(BaseModel):
    symbol: str = Field(min_length=1)
    label: Literal["BUY", "SELL", "HOLD", "OVERWEIGHT", "UNDERWEIGHT"] = Field(
        description="Normalized portfolio action label."
    )
    summary: str = Field(min_length=1, description="Concise symbol-specific reasoning.")

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol_value(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_symbol(value)
        return value

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label_value(cls, value: object) -> object:
        return _LiveAnalysisResponse.normalize_label(value)


class _ToolEnabledCycleResponse(BaseModel):
    analyses: list[_ToolEnabledAnalysisResponseItem] = Field(default_factory=list)


class RunnerState(TypedDict):
    backtest_id: int
    cycle_date: date
    prompt_report_slug: str
    prompt_report: str
    authored_entry_prompt_body: str
    compiled_entry_prompt_body: str
    execution_context_body: str
    full_user_prompt: str
    positions: list[HeldPosition]
    analyses: list[PositionAnalysis]
    report_content: str
    decisions: list[TradeDecision]


class BacktestLangGraphRunner:
    def __init__(
        self,
        *,
        analyzer: BacktestSymbolAnalyzer,
        topology_key: str | None = None,
        agent_keys: tuple[str, ...] = (),
        review_mode: Literal["none", "conservative"] = "none",
    ) -> None:
        self.analyzer = analyzer
        self.topology_key = topology_key
        self.agent_keys = agent_keys
        self.review_mode = review_mode
        self._graph = self._build_graph()

    def run_cycle(self, request: BacktestLangGraphRequest) -> BacktestLangGraphResult:
        if request.execution_mode == "tool_enabled":
            return self._run_tool_enabled_cycle(request)
        if request.execution_mode == "structured_output":
            return self._run_structured_output_cycle(request)
        raise ValueError(f"Unsupported execution mode: {request.execution_mode}")

    def _run_structured_output_cycle(
        self, request: BacktestLangGraphRequest
    ) -> BacktestLangGraphResult:
        return self._invoke_graph(request)

    def _run_tool_enabled_cycle(self, request: BacktestLangGraphRequest) -> BacktestLangGraphResult:
        prompt_text = (
            request.full_user_prompt if request.full_user_prompt.strip() else request.prompt_report
        )
        positions = self._extract_positions(prompt_text)
        if not positions:
            empty_state: RunnerState = {
                "backtest_id": request.backtest_id,
                "cycle_date": request.cycle_date,
                "prompt_report_slug": request.prompt_report_slug,
                "prompt_report": request.prompt_report,
                "authored_entry_prompt_body": request.authored_entry_prompt_body,
                "compiled_entry_prompt_body": request.compiled_entry_prompt_body,
                "execution_context_body": request.execution_context_body,
                "full_user_prompt": request.full_user_prompt,
                "positions": [],
                "analyses": [],
                "report_content": "",
                "decisions": [],
            }
            return BacktestLangGraphResult(
                report_content=self._render_analysis_report(empty_state),
                decisions=[],
                tool_call_trace=[],
                approval_trace=(
                    [] if request.resolved_capability_inputs.connector_ids else "not_required"
                ),
            )

        tool_call_trace: list[dict[str, Any]] = []
        approval_trace: Any = (
            [] if request.resolved_capability_inputs.connector_ids else "not_required"
        )
        try:
            analyses, tool_call_trace, approval_trace = self._execute_tool_enabled_analysis(
                request=request,
                positions=positions,
            )
            if self.review_mode == "conservative":
                analyses = self._review_position_analyses(analyses)
            analyzed_state: RunnerState = {
                "backtest_id": request.backtest_id,
                "cycle_date": request.cycle_date,
                "prompt_report_slug": request.prompt_report_slug,
                "prompt_report": request.prompt_report,
                "authored_entry_prompt_body": request.authored_entry_prompt_body,
                "compiled_entry_prompt_body": request.compiled_entry_prompt_body,
                "execution_context_body": request.execution_context_body,
                "full_user_prompt": request.full_user_prompt,
                "positions": positions,
                "analyses": analyses,
                "report_content": "",
                "decisions": [],
            }
            return BacktestLangGraphResult(
                report_content=self._render_analysis_report(analyzed_state),
                decisions=self._build_trade_decisions(analyses),
                tool_call_trace=tool_call_trace,
                approval_trace=approval_trace,
            )
        except BacktestLangGraphToolExecutionError:
            raise
        except Exception as exc:
            raise BacktestLangGraphToolExecutionError(
                str(exc),
                tool_call_trace=tool_call_trace,
                approval_trace=approval_trace,
            ) from exc

    def _invoke_graph(self, request: BacktestLangGraphRequest) -> BacktestLangGraphResult:
        result = self._graph.invoke(
            {
                "backtest_id": request.backtest_id,
                "cycle_date": request.cycle_date,
                "prompt_report_slug": request.prompt_report_slug,
                "prompt_report": request.prompt_report,
                "authored_entry_prompt_body": request.authored_entry_prompt_body,
                "compiled_entry_prompt_body": request.compiled_entry_prompt_body,
                "execution_context_body": request.execution_context_body,
                "full_user_prompt": request.full_user_prompt,
                "positions": [],
                "analyses": [],
                "report_content": "",
                "decisions": [],
            }
        )
        return BacktestLangGraphResult(
            report_content=result["report_content"],
            decisions=result["decisions"],
            tool_call_trace=[],
            approval_trace="not_required",
        )

    def _execute_tool_enabled_analysis(
        self,
        *,
        request: BacktestLangGraphRequest,
        positions: list[HeldPosition],
    ) -> tuple[list[PositionAnalysis], list[dict[str, Any]], Any]:
        responses_analyzer = self._get_tool_enabled_responses_analyzer()
        formatted_tools, adapters_by_name = self._build_tool_definitions(request.tool_runtime)
        response = responses_analyzer.create_tool_enabled_response(
            input_items=self._build_tool_enabled_input(request=request, positions=positions),
            tools=formatted_tools,
            previous_response_id=None,
            parallel_tool_calls=False,
            text_format=self._build_tool_enabled_output_format(),
        )
        tool_call_trace: list[dict[str, Any]] = []
        approval_trace: Any = (
            [] if request.resolved_capability_inputs.connector_ids else "not_required"
        )

        for _ in range(_TOOL_ENABLED_MAX_TURNS):
            function_calls = self._extract_response_function_calls(response)
            if not function_calls:
                response_text = responses_analyzer.extract_responses_output_text(response)
                return (
                    self._build_tool_enabled_position_analyses(
                        response_text=response_text,
                        positions=positions,
                    ),
                    tool_call_trace,
                    approval_trace,
                )
            if len(function_calls) != 1:
                raise BacktestLangGraphToolExecutionError(
                    "Tool-enabled execution expects serial tool calls",
                    tool_call_trace=tool_call_trace,
                    approval_trace=approval_trace,
                )

            function_call = function_calls[0]
            adapter = adapters_by_name.get(function_call["name"])
            if adapter is None:
                raise BacktestLangGraphToolExecutionError(
                    f"Tool-enabled execution requested unknown tool {function_call['name']!r}",
                    tool_call_trace=tool_call_trace,
                    approval_trace=approval_trace,
                )

            call_index = len(tool_call_trace)
            if adapter.approval_required:
                if isinstance(approval_trace, str):
                    approval_trace = []
                approval_trace.append(
                    self._build_approval_trace_entry(
                        call_index=call_index,
                        tool_id=adapter.tool_id,
                        status="approved" if adapter.approval_granted else "denied",
                        approval_metadata=adapter.approval_metadata,
                    )
                )
                if not adapter.approval_granted:
                    raise BacktestLangGraphToolExecutionError(
                        f"Connector {adapter.tool_id} is not approved for execution",
                        tool_call_trace=tool_call_trace,
                        approval_trace=approval_trace,
                    )

            arguments = self._parse_tool_call_arguments(function_call["arguments"])
            argument_hash = self._hash_payload(arguments)
            started = time.perf_counter()
            try:
                result = adapter.invoke(arguments)
            except Exception as exc:
                tool_call_trace.append(
                    self._build_tool_call_trace_entry(
                        call_index=call_index,
                        tool_id=adapter.tool_id,
                        status="error",
                        latency_ms=self._latency_ms(started),
                        argument_hash=argument_hash,
                        error_code=self._error_code_for_exception(exc),
                    )
                )
                raise BacktestLangGraphToolExecutionError(
                    f"Tool {adapter.tool_id} failed: {exc}",
                    tool_call_trace=tool_call_trace,
                    approval_trace=approval_trace,
                ) from exc

            tool_call_trace.append(
                self._build_tool_call_trace_entry(
                    call_index=call_index,
                    tool_id=adapter.tool_id,
                    status="success",
                    latency_ms=self._latency_ms(started),
                    argument_hash=argument_hash,
                    result_hash=self._hash_payload(result),
                )
            )
            response = responses_analyzer.create_tool_enabled_response(
                input_items=[
                    {
                        "type": "function_call_output",
                        "call_id": function_call["call_id"],
                        "output": self._stable_json_dumps(result),
                    }
                ],
                tools=formatted_tools,
                previous_response_id=self._extract_response_id(response),
                parallel_tool_calls=False,
                text_format=self._build_tool_enabled_output_format(),
            )

        raise BacktestLangGraphToolExecutionError(
            "Tool-enabled execution exceeded the maximum tool turns",
            tool_call_trace=tool_call_trace,
            approval_trace=approval_trace,
        )

    def _build_tool_enabled_position_analyses(
        self,
        *,
        response_text: str,
        positions: list[HeldPosition],
    ) -> list[PositionAnalysis]:
        payload = _ToolEnabledCycleResponse.model_validate(json.loads(response_text))
        analyses_by_symbol: dict[str, LangGraphSymbolAnalysis] = {}
        allowed_symbols = {position.symbol for position in positions}
        for item in payload.analyses:
            if item.symbol not in allowed_symbols:
                raise RuntimeError(f"Tool-enabled response returned unknown symbol {item.symbol!r}")
            if item.symbol in analyses_by_symbol:
                raise RuntimeError(
                    f"Tool-enabled response returned duplicate analysis for {item.symbol!r}"
                )
            analyses_by_symbol[item.symbol] = LangGraphSymbolAnalysis(
                label=item.label,
                summary=item.summary.strip(),
            )

        missing_symbols = [
            position.symbol for position in positions if position.symbol not in analyses_by_symbol
        ]
        if missing_symbols:
            raise RuntimeError(
                "Tool-enabled response omitted analyses for held symbols: "
                f"{', '.join(missing_symbols)}"
            )

        return [
            PositionAnalysis(position=position, analysis=analyses_by_symbol[position.symbol])
            for position in positions
        ]

    def _build_tool_definitions(
        self, tool_runtime: BacktestLangGraphToolRuntime
    ) -> tuple[list[dict[str, object]], dict[str, BacktestLangGraphToolAdapter]]:
        formatted_tools: list[dict[str, object]] = []
        adapters_by_name: dict[str, BacktestLangGraphToolAdapter] = {}
        for adapter in tool_runtime.adapters:
            tool_name = self._tool_name_for_id(adapter.tool_id)
            if tool_name in adapters_by_name:
                raise ValueError(f"Tool name collision for tool id {adapter.tool_id}")
            adapters_by_name[tool_name] = adapter
            formatted_tools.append(
                {
                    "type": "function",
                    "name": tool_name,
                    "description": adapter.description,
                    "parameters": adapter.parameters_schema,
                    "strict": True,
                }
            )
        return formatted_tools, adapters_by_name

    def _build_tool_enabled_input(
        self,
        *,
        request: BacktestLangGraphRequest,
        positions: list[HeldPosition],
    ) -> list[dict[str, object]]:
        position_lines = "\n".join(
            f"- {position.symbol}: {position.quantity_text} shares" for position in positions
        )
        execution_prompt = (
            request.full_user_prompt if request.full_user_prompt.strip() else request.prompt_report
        )
        messages = [
            (
                "system",
                "You analyze held portfolio positions for a historical backtest. "
                "Use only the execution prompt and approved read-only backend tools. "
                "Return JSON with an analyses array containing exactly one item per held symbol. "
                "Each item must include symbol, label, and summary. "
                "Allowed labels are BUY, SELL, HOLD, OVERWEIGHT, and UNDERWEIGHT.",
            ),
            (
                "user",
                f"Backtest ID: {request.backtest_id}\n"
                f"Cycle date: {request.cycle_date.isoformat()}\n"
                f"Prompt report slug: {request.prompt_report_slug}\n"
                "Held positions:\n"
                f"{position_lines}\n\n"
                "Execution prompt:\n"
                f"{execution_prompt}",
            ),
        ]
        return [
            {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": content}],
            }
            for role, content in messages
        ]

    def _build_tool_enabled_output_format(self) -> dict[str, object]:
        return {
            "format": {
                "type": "json_schema",
                "name": "backtest_tool_enabled_cycle_result",
                "schema": {
                    "type": "object",
                    "properties": {
                        "analyses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string"},
                                    "label": {
                                        "type": "string",
                                        "enum": [
                                            "BUY",
                                            "SELL",
                                            "HOLD",
                                            "OVERWEIGHT",
                                            "UNDERWEIGHT",
                                        ],
                                    },
                                    "summary": {"type": "string"},
                                },
                                "required": ["symbol", "label", "summary"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["analyses"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        }

    def _get_tool_enabled_responses_analyzer(self) -> ToolEnabledResponsesAnalyzer:
        if not hasattr(self.analyzer, "create_tool_enabled_response") or not hasattr(
            self.analyzer, "extract_responses_output_text"
        ):
            raise RuntimeError("Configured analyzer does not support tool-enabled execution")
        return cast(ToolEnabledResponsesAnalyzer, self.analyzer)

    def _extract_response_function_calls(self, response: Any) -> list[dict[str, str]]:
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return []

        function_calls: list[dict[str, str]] = []
        for item in output:
            item_type = getattr(item, "type", None)
            if item_type is None and isinstance(item, dict):
                item_type = item.get("type")
            if item_type != "function_call":
                continue

            name = getattr(item, "name", None)
            if name is None and isinstance(item, dict):
                name = item.get("name")
            arguments = getattr(item, "arguments", None)
            if arguments is None and isinstance(item, dict):
                arguments = item.get("arguments")
            call_id = getattr(item, "call_id", None)
            if call_id is None and isinstance(item, dict):
                call_id = item.get("call_id") or item.get("id")
            if not isinstance(name, str) or not isinstance(call_id, str):
                raise RuntimeError("Responses function call item was missing required name/call_id")
            function_calls.append(
                {
                    "name": name,
                    "arguments": arguments if isinstance(arguments, str) else "{}",
                    "call_id": call_id,
                }
            )
        return function_calls

    @staticmethod
    def _extract_response_id(response: Any) -> str:
        response_id = getattr(response, "id", None)
        if not isinstance(response_id, str) or not response_id.strip():
            raise RuntimeError("Responses API returned no response id for tool follow-up")
        return response_id

    @staticmethod
    def _parse_tool_call_arguments(raw_arguments: str) -> dict[str, Any]:
        if not raw_arguments.strip():
            return {}
        parsed = json.loads(raw_arguments)
        if not isinstance(parsed, dict):
            raise RuntimeError("Tool call arguments must decode to a JSON object")
        return parsed

    @staticmethod
    def _build_tool_call_trace_entry(
        *,
        call_index: int,
        tool_id: str,
        status: Literal["success", "error"],
        latency_ms: int,
        argument_hash: str,
        result_hash: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        trace_entry: dict[str, Any] = {
            "call_index": call_index,
            "tool_id": tool_id,
            "status": status,
            "latency_ms": latency_ms,
            "argument_hash": argument_hash,
        }
        if result_hash is not None:
            trace_entry["result_hash"] = result_hash
        if error_code is not None:
            trace_entry["error_code"] = error_code
        return trace_entry

    @staticmethod
    def _build_approval_trace_entry(
        *,
        call_index: int,
        tool_id: str,
        status: Literal["approved", "denied"],
        approval_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_entry: dict[str, Any] = {
            "call_index": call_index,
            "tool_id": tool_id,
            "status": status,
        }
        if approval_metadata:
            trace_entry.update(dict(approval_metadata))
        return trace_entry

    @staticmethod
    def _tool_name_for_id(tool_id: str) -> str:
        return "".join(char if char.isalnum() or char == "_" else "_" for char in tool_id)

    @staticmethod
    def _stable_json_dumps(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def _hash_payload(self, value: Any) -> str:
        return hashlib.sha256(self._stable_json_dumps(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _latency_ms(started: float) -> int:
        return max(0, int(round((time.perf_counter() - started) * 1000)))

    @staticmethod
    def _error_code_for_exception(exc: Exception) -> str:
        error_code = getattr(exc, "code", None)
        if isinstance(error_code, str) and error_code.strip():
            return error_code
        return re.sub(r"(?<!^)(?=[A-Z])", "_", exc.__class__.__name__).lower()

    def _build_graph(self) -> Any:
        workflow = StateGraph(RunnerState)
        workflow.add_node("parse_positions", self._parse_positions)
        workflow.add_node("analyze_positions", self._analyze_positions)
        workflow.add_node("compile_result", self._compile_result)
        workflow.add_edge(START, "parse_positions")
        workflow.add_edge("parse_positions", "analyze_positions")
        if self.review_mode == "conservative":
            workflow.add_node("review_analyses", self._review_analyses)
            workflow.add_edge("analyze_positions", "review_analyses")
            workflow.add_edge("review_analyses", "compile_result")
        else:
            workflow.add_edge("analyze_positions", "compile_result")
        workflow.add_edge("compile_result", END)
        return workflow.compile()

    def _parse_positions(self, state: RunnerState) -> RunnerState:
        return {**state, "positions": self._extract_positions(self._execution_prompt_text(state))}

    def _analyze_positions(self, state: RunnerState) -> RunnerState:
        prompt_text = self._execution_prompt_text(state)
        analyses = [
            PositionAnalysis(
                position=position,
                analysis=self.analyzer.analyze_symbol(
                    symbol=position.symbol,
                    cycle_date=state["cycle_date"],
                    prompt_text=prompt_text,
                    position_quantity=position.quantity_text,
                ),
            )
            for position in state["positions"]
        ]
        return {**state, "analyses": analyses}

    def _compile_result(self, state: RunnerState) -> RunnerState:
        report_content = self._render_analysis_report(state)
        decisions = self._build_trade_decisions(state["analyses"])
        return {
            **state,
            "report_content": report_content,
            "decisions": decisions,
        }

    def _review_analyses(self, state: RunnerState) -> RunnerState:
        return {**state, "analyses": self._review_position_analyses(state["analyses"])}

    def _review_position_analyses(self, analyses: list[PositionAnalysis]) -> list[PositionAnalysis]:
        reviewed: list[PositionAnalysis] = []
        for symbol_analysis in analyses:
            label = symbol_analysis.analysis.label.strip().upper()
            if label not in {"BUY", "OVERWEIGHT"}:
                reviewed.append(symbol_analysis)
                continue
            reviewed.append(
                PositionAnalysis(
                    position=symbol_analysis.position,
                    analysis=LangGraphSymbolAnalysis(
                        label="HOLD",
                        summary=(
                            f"{symbol_analysis.analysis.summary} "
                            f"Conservative review applied: {label} -> HOLD."
                        ),
                    ),
                )
            )
        return reviewed

    def _execution_prompt_text(self, state: RunnerState) -> str:
        if state["full_user_prompt"].strip():
            return state["full_user_prompt"]
        return state["prompt_report"]

    def _extract_positions(self, prompt_text: str) -> list[HeldPosition]:
        positions: list[HeldPosition] = []
        in_positions = False

        for raw_line in prompt_text.splitlines():
            line = raw_line.strip()
            if line == "Positions:":
                in_positions = True
                continue

            if not in_positions:
                continue

            if not line:
                continue

            if line == "- None":
                return []

            match = _POSITION_LINE_RE.match(line)
            if match is None:
                if line.startswith("-"):
                    continue
                break

            quantity_text = match.group("quantity")
            positions.append(
                HeldPosition(
                    symbol=normalize_symbol(match.group("symbol")),
                    quantity_text=self._normalize_quantity_text(quantity_text),
                    quantity=parse_decimal_string(quantity_text),
                )
            )

        return positions

    def _normalize_quantity_text(self, value: str) -> str:
        parsed = parse_decimal_string(value)
        if parsed == parsed.to_integral_value():
            return str(int(parsed))
        return format(parsed.normalize(), "f")

    def _render_analysis_report(self, state: RunnerState) -> str:
        lines = [
            "# LangGraph Analysis",
            "",
            f"- Backtest ID: {state['backtest_id']}",
            f"- Cycle date: {state['cycle_date'].isoformat()}",
            f"- Prompt report slug: {state['prompt_report_slug']}",
        ]

        if self.topology_key is not None:
            lines.append(f"- Topology: {self.topology_key}")
        if self.agent_keys:
            lines.append(f"- Agents: {', '.join(self.agent_keys)}")

        lines.append("")

        if not state["analyses"]:
            lines.append("No held symbols were found in the execution prompt.")
            return "\n".join(lines)

        for index, symbol_analysis in enumerate(state["analyses"]):
            if index:
                lines.append("")
            lines.extend(
                [
                    f"## {symbol_analysis.position.symbol}",
                    f"- Label: {symbol_analysis.analysis.label}",
                    f"- Held quantity: {symbol_analysis.position.quantity_text}",
                    f"- Summary: {symbol_analysis.analysis.summary}",
                ]
            )

        return "\n".join(lines)

    def _build_trade_decisions(self, analyses: list[PositionAnalysis]) -> list[TradeDecision]:
        decisions: list[TradeDecision] = []

        for symbol_analysis in analyses:
            action, quantity, note = self._translate_action(symbol_analysis)
            reasoning = f"{symbol_analysis.analysis.label}: {symbol_analysis.analysis.summary}"
            if note is not None:
                reasoning = f"{reasoning} {note}"
            decisions.append(
                TradeDecision(
                    symbol=symbol_analysis.position.symbol,
                    action=action,
                    quantity=quantity,
                    target_price=None,
                    reasoning=reasoning,
                )
            )

        return decisions

    def _translate_action(
        self, symbol_analysis: PositionAnalysis
    ) -> tuple[Literal["BUY", "SELL", "HOLD"], int | None, str | None]:
        label = symbol_analysis.analysis.label.strip().upper()
        if label in {"BUY", "OVERWEIGHT"}:
            return "BUY", _FIXED_BUY_QUANTITY, None
        if label in {"SELL", "UNDERWEIGHT"}:
            if (
                symbol_analysis.position.quantity
                != symbol_analysis.position.quantity.to_integral_value()
            ):
                return (
                    "HOLD",
                    None,
                    (
                        f"Fractional held quantity {symbol_analysis.position.quantity_text} is not "
                        "supported for SELL in phase 1."
                    ),
                )
            return "SELL", int(symbol_analysis.position.quantity), None
        return "HOLD", None, None


class LiveBacktestSymbolAnalyzer:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None,
        timeout_seconds: float,
        temperature: float,
        api_mode: Literal["auto", "responses", "chat_completions"] = "auto",
    ) -> None:
        self.model = model.strip()
        self.api_key = api_key.strip() if api_key is not None else None
        self.base_url = base_url.strip() if base_url is not None else None
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.api_mode = api_mode
        self._llm: ChatOpenAI | None = None
        self._openai_client: OpenAI | None = None

    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_text: str,
        position_quantity: str,
    ) -> LangGraphSymbolAnalysis:
        if not self.model:
            raise RuntimeError("BACKTEST_AGENT_MODEL is required for LangGraph backtests")

        messages = self._build_messages(
            symbol=symbol,
            cycle_date=cycle_date,
            prompt_text=prompt_text,
            position_quantity=position_quantity,
        )

        if self.api_mode == "responses":
            response = self._invoke_responses_json(messages)
            return LangGraphSymbolAnalysis(label=response.label, summary=response.summary.strip())

        if self.api_mode == "chat_completions":
            response = self._invoke_chat_json(messages)
            return LangGraphSymbolAnalysis(label=response.label, summary=response.summary.strip())

        response = self._invoke_chat_json(messages)
        return LangGraphSymbolAnalysis(label=response.label, summary=response.summary.strip())

    def _build_messages(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_text: str,
        position_quantity: str,
    ) -> list[tuple[str, str]]:
        return [
            (
                "system",
                "You analyze one held portfolio position for a historical backtest. "
                "Use only the information provided in the execution prompt. "
                "Do not invent data from after the cycle date. "
                "Return a normalized label and a concise summary. "
                'Respond as JSON with keys "label" and "summary".',
            ),
            (
                "user",
                f"Cycle date: {cycle_date.isoformat()}\n"
                f"Held symbol: {symbol}\n"
                f"Held quantity: {position_quantity}\n\n"
                "Execution prompt:\n"
                f"{prompt_text}",
            ),
        ]

    def _invoke_chat_json(self, messages: list[tuple[str, str]]) -> _LiveAnalysisResponse:
        try:
            return cast(
                _LiveAnalysisResponse,
                self._get_llm().with_structured_output(_LiveAnalysisResponse).invoke(messages),
            )
        except ValueError as exc:
            if "Structured Output response does not have" not in str(exc):
                raise
            return self._invoke_chat_json_fallback(messages)

    def _invoke_chat_json_fallback(self, messages: list[tuple[str, str]]) -> _LiveAnalysisResponse:
        raw_response = self._get_llm().invoke(messages)
        content = self._coerce_response_content(raw_response)
        if not content.strip():
            content = self._invoke_chat_completions_json(messages)
        return _LiveAnalysisResponse.model_validate(json.loads(content))

    def _invoke_chat_completions_json(self, messages: list[tuple[str, str]]) -> str:
        response = cast(
            Any,
            self._get_openai_client().chat.completions.create(
                model=self.model,
                response_format=cast(Any, {"type": "json_object"}),
                temperature=self.temperature,
                messages=cast(
                    Any,
                    [{"role": role, "content": content} for role, content in messages],
                ),
            ),
        )
        content = cast(str | None, response.choices[0].message.content)
        if content is None:
            raise RuntimeError("OpenAI-compatible fallback returned no content")
        return content

    def _invoke_responses_json(self, messages: list[tuple[str, str]]) -> _LiveAnalysisResponse:
        stream = cast(
            Any,
            self._get_openai_client().responses.create(
                model=self.model,
                reasoning=cast(Any, {"effort": "none"}),
                stream=cast(Any, True),
                text=cast(Any, {"format": {"type": "json_object"}}),
                input=cast(Any, self._build_responses_input(messages)),
            ),
        )
        content = self._extract_streamed_responses_output_text(stream)
        return _LiveAnalysisResponse.model_validate(json.loads(content))

    def create_tool_enabled_response(
        self,
        *,
        input_items: list[dict[str, object]],
        tools: list[dict[str, object]],
        previous_response_id: str | None,
        parallel_tool_calls: bool,
        text_format: dict[str, object],
    ) -> Any:
        return cast(
            Any,
            self._get_openai_client().responses.create(
                model=self.model,
                reasoning=cast(Any, {"effort": "none"}),
                input=cast(Any, input_items),
                tools=cast(Any, tools),
                previous_response_id=previous_response_id,
                parallel_tool_calls=cast(Any, parallel_tool_calls),
                text=cast(Any, text_format),
            ),
        )

    def extract_responses_output_text(self, response: Any) -> str:
        return self._extract_responses_output_text(response)

    def _build_responses_input(self, messages: list[tuple[str, str]]) -> list[dict[str, object]]:
        return [
            {
                "type": "message",
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": content,
                    }
                ],
            }
            for role, content in messages
        ]

    def _extract_streamed_responses_output_text(self, stream: Any) -> str:
        deltas: list[str] = []
        done_text: str | None = None
        response_id: str | None = None
        status: str | None = None

        for event in stream:
            event_type = getattr(event, "type", None)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if isinstance(delta, str) and delta:
                    deltas.append(delta)
                continue
            if event_type == "response.output_text.done":
                text = getattr(event, "text", None)
                if isinstance(text, str) and text.strip():
                    done_text = text
                continue
            if event_type == "response.completed":
                response = getattr(event, "response", None)
                response_id = getattr(response, "id", None)
                status = getattr(response, "status", None)

        if done_text is not None:
            return done_text
        if deltas:
            return "".join(deltas)

        raise RuntimeError(
            "Responses API stream returned no usable output text "
            f"(id={response_id}, status={status})"
        )

    def _extract_responses_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = getattr(response, "output", None)
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                content_blocks = getattr(item, "content", None)
                if content_blocks is None and isinstance(item, dict):
                    content_blocks = item.get("content")
                if not isinstance(content_blocks, list):
                    continue
                for block in content_blocks:
                    text = None
                    block_type = getattr(block, "type", None)
                    if block_type is None and isinstance(block, dict):
                        block_type = block.get("type")
                    if block_type in {"output_text", "text"}:
                        text = getattr(block, "text", None)
                        if text is None and isinstance(block, dict):
                            text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            if parts:
                return "\n".join(parts)

        response_id = getattr(response, "id", None)
        status = getattr(response, "status", None)
        usage = getattr(response, "usage", None)
        raise RuntimeError(
            "Responses API returned no usable output text "
            f"(id={response_id}, status={status}, usage={usage})"
        )

    def _coerce_response_content(self, response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self.model,
                api_key=SecretStr(self.api_key) if self.api_key is not None else None,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                temperature=self.temperature,
            )
        return self._llm

    def _get_openai_client(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        return self._openai_client
