from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol, TypedDict, cast

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from openai import OpenAI
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.backtest import TradeDecision

_FIXED_BUY_QUANTITY = 1
_POSITION_LINE_RE = re.compile(r"^-\s*(?P<symbol>[^:]+):\s*(?P<quantity>[^\s]+)\s+shares\s+@\s+.+$")


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


@dataclass(frozen=True)
class BacktestLangGraphRequest:
    backtest_id: int
    cycle_date: date
    prompt_report_slug: str
    prompt_report: str


@dataclass(frozen=True)
class BacktestLangGraphResult:
    report_content: str
    decisions: list[TradeDecision]


class BacktestSymbolAnalyzer(Protocol):
    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_report: str,
        position_quantity: str,
    ) -> LangGraphSymbolAnalysis: ...


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


class RunnerState(TypedDict):
    backtest_id: int
    cycle_date: date
    prompt_report_slug: str
    prompt_report: str
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
        result = self._graph.invoke(
            {
                "backtest_id": request.backtest_id,
                "cycle_date": request.cycle_date,
                "prompt_report_slug": request.prompt_report_slug,
                "prompt_report": request.prompt_report,
                "positions": [],
                "analyses": [],
                "report_content": "",
                "decisions": [],
            }
        )
        return BacktestLangGraphResult(
            report_content=result["report_content"],
            decisions=result["decisions"],
        )

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
        return {**state, "positions": self._extract_positions(state["prompt_report"])}

    def _analyze_positions(self, state: RunnerState) -> RunnerState:
        analyses = [
            PositionAnalysis(
                position=position,
                analysis=self.analyzer.analyze_symbol(
                    symbol=position.symbol,
                    cycle_date=state["cycle_date"],
                    prompt_report=state["prompt_report"],
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
        reviewed: list[PositionAnalysis] = []

        for symbol_analysis in state["analyses"]:
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

        return {**state, "analyses": reviewed}

    def _extract_positions(self, prompt_report: str) -> list[HeldPosition]:
        positions: list[HeldPosition] = []
        in_positions = False

        for raw_line in prompt_report.splitlines():
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
            lines.append("No held symbols were found in the prompt report.")
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
        prompt_report: str,
        position_quantity: str,
    ) -> LangGraphSymbolAnalysis:
        if not self.model:
            raise RuntimeError("BACKTEST_AGENT_MODEL is required for LangGraph backtests")

        messages = self._build_messages(
            symbol=symbol,
            cycle_date=cycle_date,
            prompt_report=prompt_report,
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
        prompt_report: str,
        position_quantity: str,
    ) -> list[tuple[str, str]]:
        return [
            (
                "system",
                "You analyze one held portfolio position for a historical backtest. "
                "Use only the information provided in the prompt report. "
                "Do not invent data from after the cycle date. "
                "Return a normalized label and a concise summary. "
                'Respond as JSON with keys "label" and "summary".',
            ),
            (
                "user",
                f"Cycle date: {cycle_date.isoformat()}\n"
                f"Held symbol: {symbol}\n"
                f"Held quantity: {position_quantity}\n\n"
                "Full prompt report:\n"
                f"{prompt_report}",
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
