from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class TradingAgentsAnalysis:
    label: str
    summary: str


class TradingAgentsAdapter(Protocol):
    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_report: str,
        position_quantity: str,
    ) -> TradingAgentsAnalysis: ...


class LiveTradingAgentsAdapter:
    def __init__(self) -> None:
        self._graph: Any | None = None

    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_report: str,
        position_quantity: str,
    ) -> TradingAgentsAnalysis:
        _ = (prompt_report, position_quantity)
        graph = self._get_graph()
        final_state, decision = graph.propagate(symbol, cycle_date.isoformat())
        return self._coerce_analysis(decision, final_state=final_state)

    def _get_graph(self) -> Any:
        if self._graph is None:
            try:
                default_config_module = importlib.import_module("tradingagents.default_config")
                trading_graph_module = importlib.import_module("tradingagents.graph.trading_graph")
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "TradingAgents is not installed. Install the TradingAgents package to use "
                    "the worker adapter."
                ) from exc

            default_config = self._build_config(default_config_module.DEFAULT_CONFIG)
            graph_cls = trading_graph_module.TradingAgentsGraph
            self._graph = graph_cls(debug=False, config=default_config)

        return self._graph

    def _build_config(self, default_config: Any) -> dict[str, Any]:
        if not isinstance(default_config, dict):
            raise RuntimeError("TradingAgents DEFAULT_CONFIG must be a dictionary")

        config = default_config.copy()
        overrides = {
            "llm_provider": os.getenv("TRADINGAGENTS_LLM_PROVIDER"),
            "backend_url": os.getenv("TRADINGAGENTS_BACKEND_URL"),
            "quick_think_llm": os.getenv("TRADINGAGENTS_QUICK_THINK_LLM"),
            "deep_think_llm": os.getenv("TRADINGAGENTS_DEEP_THINK_LLM"),
        }
        for key, value in overrides.items():
            if value is not None and value.strip():
                config[key] = value.strip()
        return config

    def _coerce_analysis(
        self, decision: Any, *, final_state: Any | None = None
    ) -> TradingAgentsAnalysis:
        label = self._extract_field(decision, "label", "decision", "action", "signal")
        summary = self._extract_field(
            final_state,
            "final_trade_decision",
            "summary",
            "reasoning",
            "rationale",
            "analysis",
        )
        if summary is None:
            summary = self._extract_field(
                decision,
                "summary",
                "reasoning",
                "rationale",
                "analysis",
            )

        resolved_label = str(label or "HOLD").strip().upper()
        if summary is None:
            if isinstance(decision, str):
                resolved_summary = decision.strip()
            else:
                resolved_summary = json.dumps(decision, default=str, sort_keys=True)
        else:
            resolved_summary = str(summary).strip()

        if not resolved_summary:
            resolved_summary = resolved_label

        return TradingAgentsAnalysis(label=resolved_label, summary=resolved_summary)

    def _extract_field(self, decision: Any, *names: str) -> Any | None:
        if isinstance(decision, dict):
            for name in names:
                if name in decision and decision[name] is not None:
                    return decision[name]
            return None

        for name in names:
            value = getattr(decision, name, None)
            if value is not None:
                return value

        if isinstance(decision, str):
            return decision

        return None
