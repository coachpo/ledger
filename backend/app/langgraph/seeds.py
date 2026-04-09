from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.langgraph.runner import BacktestLangGraphRunner, BacktestSymbolAnalyzer


@dataclass(frozen=True)
class SeededAgentSpec:
    key: str
    role: str
    system_prompt: str


@dataclass(frozen=True)
class SeededTopology:
    key: str
    description: str
    agent_order: tuple[str, ...]
    review_mode: Literal["none", "conservative"] = "none"


SEEDED_AGENT_SPECS: tuple[SeededAgentSpec, ...] = (
    SeededAgentSpec(
        key="position_analyst",
        role="Position Analyst",
        system_prompt=(
            "Analyze one held position using only the current prompt report and return a "
            "normalized action label plus concise summary."
        ),
    ),
    SeededAgentSpec(
        key="risk_reviewer",
        role="Risk Reviewer",
        system_prompt=(
            "Review candidate actions for execution safety and enforce conservative behavior "
            "when constraints are unclear."
        ),
    ),
    SeededAgentSpec(
        key="decision_writer",
        role="Decision Writer",
        system_prompt=(
            "Render the final backtest analysis report and translate reviewed analyses into "
            "Ledger trade decisions."
        ),
    ),
)


SEEDED_TOPOLOGY = SeededTopology(
    key="seeded_internal_backtest_v1",
    description="Sequential MVP topology for internal LangGraph backtest execution.",
    agent_order=("position_analyst", "decision_writer"),
)

ANALYST_REVIEWER_TOPOLOGY = SeededTopology(
    key="analyst_reviewer_v1",
    description="Analyst plus conservative reviewer workflow for internal LangGraph backtests.",
    agent_order=tuple(agent.key for agent in SEEDED_AGENT_SPECS),
    review_mode="conservative",
)

DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY = SEEDED_TOPOLOGY.key


def build_seeded_langgraph_runner(*, analyzer: BacktestSymbolAnalyzer) -> BacktestLangGraphRunner:
    return BacktestLangGraphRunner(
        analyzer=analyzer,
        topology_key=SEEDED_TOPOLOGY.key,
        agent_keys=SEEDED_TOPOLOGY.agent_order,
        review_mode=SEEDED_TOPOLOGY.review_mode,
    )


def build_analyst_reviewer_langgraph_runner(
    *, analyzer: BacktestSymbolAnalyzer
) -> BacktestLangGraphRunner:
    return BacktestLangGraphRunner(
        analyzer=analyzer,
        topology_key=ANALYST_REVIEWER_TOPOLOGY.key,
        agent_keys=ANALYST_REVIEWER_TOPOLOGY.agent_order,
        review_mode=ANALYST_REVIEWER_TOPOLOGY.review_mode,
    )


def is_supported_backtest_orchestration_pattern_key(pattern_key: str) -> bool:
    return pattern_key in {SEEDED_TOPOLOGY.key, ANALYST_REVIEWER_TOPOLOGY.key}


def build_backtest_langgraph_runner(
    *, pattern_key: str, analyzer: BacktestSymbolAnalyzer
) -> BacktestLangGraphRunner:
    if pattern_key == SEEDED_TOPOLOGY.key:
        return build_seeded_langgraph_runner(analyzer=analyzer)
    if pattern_key == ANALYST_REVIEWER_TOPOLOGY.key:
        return build_analyst_reviewer_langgraph_runner(analyzer=analyzer)
    raise ValueError(f"Unknown orchestration pattern: {pattern_key}")
