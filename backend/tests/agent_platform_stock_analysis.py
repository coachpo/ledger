from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS = (
    "financials_analyst",
    "news_analyst",
    "market_analyst",
    "industry_analyst",
    "economy_analyst",
    "price_analyst",
    "position_reader",
    "history_reader",
)
STOCK_ANALYSIS_SYNTHESIZER_KEY = "decision_synthesizer"
STOCK_ANALYSIS_NOTE_SCHEMA_KEY = "stock_analysis_note"
TRADING_DECISION_SCHEMA_KEY = "trading_decision"
STOCK_ANALYSIS_SKILL_KEY = "stock_analysis_tools"
STOCK_ANALYSIS_MCP_SERVER_KEY = "stock_analysis_data"
STOCK_ANALYSIS_REFERENCE_MCP_COMMAND = (
    "python3 -m app.agents.mcp.stock_analysis_reference_server"
)
STOCK_ANALYSIS_REFERENCE_TOOL_KEYS = (
    "ledger.stock_analysis.market_snapshot",
    "ledger.stock_analysis.price_history",
    "ledger.stock_analysis.position_inventory",
    "ledger.stock_analysis.report_lookup",
    "ledger.stock_analysis.market_context",
)

_STOCK_ANALYSIS_SIGNAL_BY_AGENT = {
    "financials_analyst": "bullish",
    "news_analyst": "bullish",
    "market_analyst": "bullish",
    "industry_analyst": "bullish",
    "economy_analyst": "cautious",
    "price_analyst": "bullish",
    "position_reader": "supportive",
    "history_reader": "supportive",
}


def stock_analysis_workflow_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "horizon_days": {"type": "integer"},
        },
        "required": ["ticker", "horizon_days"],
        "additionalProperties": False,
    }


def stock_analysis_note_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "signal": {"type": "string"},
        },
        "required": ["summary", "signal"],
        "additionalProperties": False,
    }


def trading_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
            "price_targets": {"type": "array", "items": {"type": "number"}},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action", "confidence", "rationale", "price_targets", "risks"],
        "additionalProperties": False,
    }


def stock_analysis_synthesizer_input_schema(
    *, optional_agents: Iterable[str] = ()
) -> dict[str, Any]:
    optional_keys = set(optional_agents)
    return {
        "type": "object",
        "properties": {
            key: stock_analysis_note_schema() for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
        },
        "required": [
            key for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS if key not in optional_keys
        ],
        "additionalProperties": False,
    }


def stock_analysis_step_one_wiring() -> dict[str, dict[str, str]]:
    return {
        "ticker": {"from": "input", "path": "ticker"},
        "horizon_days": {"from": "input", "path": "horizon_days"},
    }


def stock_analysis_agent_payload(
    key: str,
    *,
    budget_usd: str = "0.05000000",
) -> dict[str, Any]:
    return {
        "key": key,
        "name": key.replace("_", " ").title(),
        "description": f"Stub stock-analysis agent for {key}.",
        "model": "openai:gpt-5.4-mini",
        "systemPrompt": f"Return the deterministic stub analysis for {key}.",
        "inputSchema": stock_analysis_workflow_input_schema(),
        "outputSchemaKey": STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
        "skills": [{"skillKey": STOCK_ANALYSIS_SKILL_KEY}],
        "mcpServers": [{"mcpServerKey": STOCK_ANALYSIS_MCP_SERVER_KEY}],
        "budgetUsd": budget_usd,
        "streaming": False,
    }


def stock_analysis_synthesizer_payload(
    *,
    optional_agents: Iterable[str] = (),
    budget_usd: str = "0.10000000",
) -> dict[str, Any]:
    return {
        "key": STOCK_ANALYSIS_SYNTHESIZER_KEY,
        "name": "Decision Synthesizer",
        "description": "Combines the stub analyses into a TradingDecision.",
        "model": "openai:gpt-5.4-mini",
        "systemPrompt": "Combine the wired analyses into a deterministic TradingDecision.",
        "inputSchema": stock_analysis_synthesizer_input_schema(optional_agents=optional_agents),
        "outputSchemaKey": TRADING_DECISION_SCHEMA_KEY,
        "skills": [{"skillKey": STOCK_ANALYSIS_SKILL_KEY}],
        "mcpServers": [{"mcpServerKey": STOCK_ANALYSIS_MCP_SERVER_KEY}],
        "budgetUsd": budget_usd,
        "streaming": False,
    }


def stock_analysis_workflow_payload(*, optional_agents: Iterable[str] = ()) -> dict[str, Any]:
    optional_keys = set(optional_agents)
    return {
        "key": "stock_analysis",
        "name": "Stock Analysis",
        "description": "Stub stock-analysis workflow acceptance path.",
        "inputSchema": stock_analysis_workflow_input_schema(),
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": key,
                        "slot": key,
                        "wiring": stock_analysis_step_one_wiring(),
                        "optional": key in optional_keys,
                    }
                    for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
                ],
            }
        ],
        "outputSpec": {
            "kind": "agent",
            "agentKey": STOCK_ANALYSIS_SYNTHESIZER_KEY,
            "wiring": {
                key: {"from": "step", "stepIndex": 1, "slot": key}
                for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
            },
        },
    }


def build_stock_analysis_note(
    *, agent_key: str, ticker: str, horizon_days: int
) -> dict[str, Any]:
    return {
        "summary": f"{agent_key} stub summary for {ticker} over {horizon_days}d",
        "signal": _STOCK_ANALYSIS_SIGNAL_BY_AGENT[agent_key],
    }


def build_trading_decision(
    analyses: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    bullish_signals = sum(
        1
        for analysis in analyses.values()
        if analysis.get("signal") in {"bullish", "supportive"}
    )
    action = "buy" if bullish_signals >= 5 else "hold"
    ordered_summaries = [analyses[key]["summary"] for key in sorted(analyses)]
    return {
        "action": action,
        "confidence": 0.82 if action == "buy" else 0.58,
        "rationale": " | ".join(ordered_summaries),
        "price_targets": [125.0, 140.0],
        "risks": ["macro slowdown", "earnings miss"],
    }


def make_stock_analysis_stub_invoke(
    *,
    failing_agents: Iterable[str] = (),
    cost_by_agent: Mapping[str, str] | None = None,
) -> Callable[..., Any]:
    failures = set(failing_agents)
    costs = dict(cost_by_agent or {})

    async def fake_invoke(self: Any, **kwargs: Any) -> dict[str, Any]:
        step_index = int(kwargs["step_index"])
        slot = str(kwargs["slot"])
        resolved_input = dict(kwargs["resolved_input"])
        agent_key = str(kwargs["agent"].key)
        if step_index == 1:
            if agent_key in failures or slot in failures:
                raise RuntimeError(f"{agent_key} stub failure")
            return {
                "output": build_stock_analysis_note(
                    agent_key=agent_key,
                    ticker=str(resolved_input["ticker"]),
                    horizon_days=int(resolved_input["horizon_days"]),
                ),
                "tokens": 5,
                "costUsd": costs.get(agent_key, costs.get(slot, "0.01000000")),
                "durationMs": 4,
                "traceSpanId": f"step-1-{slot}",
            }
        return {
            "output": build_trading_decision(
                {
                    key: value
                    for key, value in resolved_input.items()
                    if key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
                }
            ),
            "tokens": 9,
            "costUsd": costs.get(agent_key, costs.get(slot, "0.02000000")),
            "durationMs": 6,
            "traceSpanId": f"step-2-{agent_key}",
        }

    return fake_invoke
