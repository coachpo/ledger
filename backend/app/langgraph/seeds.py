from __future__ import annotations

from dataclasses import dataclass

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
    agent_order=tuple(agent.key for agent in SEEDED_AGENT_SPECS),
)


def build_seeded_langgraph_runner(*, analyzer: BacktestSymbolAnalyzer) -> BacktestLangGraphRunner:
    return BacktestLangGraphRunner(
        analyzer=analyzer,
        topology_key=SEEDED_TOPOLOGY.key,
        agent_keys=SEEDED_TOPOLOGY.agent_order,
    )
