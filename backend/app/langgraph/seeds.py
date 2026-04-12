from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.langgraph.runner import BacktestLangGraphRunner, BacktestSymbolAnalyzer

PatternExecutionMode = Literal["structured_output", "tool_enabled"]
ConnectorLifecycle = Literal["placeholder", "approved"]


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


@dataclass(frozen=True)
class SeededBuiltinSpec:
    handle: str
    canonical_target_id: str
    display_name: str
    description: str
    revision: int
    capability_bundle_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternMentionPolicy:
    version: int
    allow_characters: bool
    allowed_builtin_handles: tuple[str, ...]


@dataclass(frozen=True)
class SeededToolSpec:
    tool_id: str
    display_name: str
    description: str
    revision: int


@dataclass(frozen=True)
class SeededCapabilityBundleSpec:
    bundle_key: str
    display_name: str
    description: str
    tool_ids: tuple[str, ...]
    revision: int
    connector_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeededConnectorSpec:
    connector_id: str
    display_name: str
    description: str
    revision: int
    transport: Literal["mcp"] = "mcp"
    lifecycle: ConnectorLifecycle = "placeholder"


@dataclass(frozen=True)
class BacktestPatternSpec:
    key: str
    description: str
    topology: SeededTopology
    mention_policy: PatternMentionPolicy
    execution_mode: PatternExecutionMode = "structured_output"
    default_tool_ids: tuple[str, ...] = ()
    allowed_bundle_keys: tuple[str, ...] = ()
    connector_ids: tuple[str, ...] = ()


_REPORT_LOOKUP_TOOL_ID = "ledger.report_lookup"
_ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID = "ledger.orchestration_catalog_lookup"
_CYCLE_CONTEXT_LOOKUP_TOOL_ID = "ledger.cycle_context_lookup"

_LIBRARIAN_CONTEXT_BUNDLE_KEY = "builtin.librarian_context"
_EXPLORE_CONTEXT_BUNDLE_KEY = "builtin.explore_context"

_MARKET_DATA_MCP_CONNECTOR_ID = "ledger.mcp.market_data"
_COMPANY_FILINGS_MCP_CONNECTOR_ID = "ledger.mcp.company_filings"


SEEDED_BUILTIN_SPECS: tuple[SeededBuiltinSpec, ...] = (
    SeededBuiltinSpec(
        handle="librarian",
        canonical_target_id="builtin:librarian",
        display_name="Librarian",
        description="Research and retrieve supporting context for a backtest analysis.",
        revision=1,
        capability_bundle_keys=(_LIBRARIAN_CONTEXT_BUNDLE_KEY,),
    ),
    SeededBuiltinSpec(
        handle="explore",
        canonical_target_id="builtin:explore",
        display_name="Explore",
        description="Inspect the current backtest context and summarize relevant findings.",
        revision=1,
        capability_bundle_keys=(_EXPLORE_CONTEXT_BUNDLE_KEY,),
    ),
)


SEEDED_BUILTIN_REGISTRY: dict[str, SeededBuiltinSpec] = {
    builtin.canonical_target_id: builtin for builtin in SEEDED_BUILTIN_SPECS
}


SEEDED_BUILTIN_HANDLE_REGISTRY: dict[str, SeededBuiltinSpec] = {
    builtin.handle: builtin for builtin in SEEDED_BUILTIN_SPECS
}


SEEDED_BUILTIN_RESERVED_TARGETS: frozenset[str] = frozenset(
    (*SEEDED_BUILTIN_HANDLE_REGISTRY, *SEEDED_BUILTIN_REGISTRY)
)


SEED_PATTERN_MENTION_POLICY = PatternMentionPolicy(
    version=1,
    allow_characters=False,
    allowed_builtin_handles=("librarian", "explore"),
)


ANALYST_REVIEWER_PATTERN_MENTION_POLICY = PatternMentionPolicy(
    version=1,
    allow_characters=True,
    allowed_builtin_handles=("librarian", "explore"),
)


def get_seeded_builtin_spec_for_handle(handle: str) -> SeededBuiltinSpec | None:
    return SEEDED_BUILTIN_HANDLE_REGISTRY.get(handle)


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

SEEDED_TOOL_SPECS: tuple[SeededToolSpec, ...] = (
    SeededToolSpec(
        tool_id=_REPORT_LOOKUP_TOOL_ID,
        display_name="Report Lookup",
        description="Read report content and metadata through ReportService-owned lookups.",
        revision=1,
    ),
    SeededToolSpec(
        tool_id=_ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID,
        display_name="Orchestration Catalog Lookup",
        description=(
            "Read orchestration catalog and seeded-target metadata through OrchestrationService."
        ),
        revision=1,
    ),
    SeededToolSpec(
        tool_id=_CYCLE_CONTEXT_LOOKUP_TOOL_ID,
        display_name="Cycle Context Lookup",
        description=(
            "Read prepared cycle prompt and runtime artifacts owned by BacktestCycleService."
        ),
        revision=1,
    ),
)

SEEDED_TOOL_REGISTRY: dict[str, SeededToolSpec] = {tool.tool_id: tool for tool in SEEDED_TOOL_SPECS}

SEEDED_CAPABILITY_BUNDLE_SPECS: tuple[SeededCapabilityBundleSpec, ...] = (
    SeededCapabilityBundleSpec(
        bundle_key=_LIBRARIAN_CONTEXT_BUNDLE_KEY,
        display_name="Builtin Librarian Context",
        description="Seed-owned bundle ref for librarian research context lookups.",
        tool_ids=(_REPORT_LOOKUP_TOOL_ID, _ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID),
        revision=1,
    ),
    SeededCapabilityBundleSpec(
        bundle_key=_EXPLORE_CONTEXT_BUNDLE_KEY,
        display_name="Builtin Explore Context",
        description="Seed-owned bundle ref for explore-oriented cycle context lookups.",
        tool_ids=(
            _ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID,
            _CYCLE_CONTEXT_LOOKUP_TOOL_ID,
        ),
        revision=1,
    ),
)

SEEDED_CAPABILITY_BUNDLE_REGISTRY: dict[str, SeededCapabilityBundleSpec] = {
    bundle.bundle_key: bundle for bundle in SEEDED_CAPABILITY_BUNDLE_SPECS
}

SEEDED_CONNECTOR_SPECS: tuple[SeededConnectorSpec, ...] = (
    SeededConnectorSpec(
        connector_id=_MARKET_DATA_MCP_CONNECTOR_ID,
        display_name="Trusted Market Data MCP",
        description="Phase-3 placeholder for a backend-owned market-data MCP connector.",
        revision=1,
    ),
    SeededConnectorSpec(
        connector_id=_COMPANY_FILINGS_MCP_CONNECTOR_ID,
        display_name="Trusted Company Filings MCP",
        description="Phase-3 placeholder for a backend-owned filings MCP connector.",
        revision=1,
    ),
)

SEEDED_CONNECTOR_REGISTRY: dict[str, SeededConnectorSpec] = {
    connector.connector_id: connector for connector in SEEDED_CONNECTOR_SPECS
}

SEEDED_PATTERN_SPEC = BacktestPatternSpec(
    key=SEEDED_TOPOLOGY.key,
    description=SEEDED_TOPOLOGY.description,
    topology=SEEDED_TOPOLOGY,
    mention_policy=SEED_PATTERN_MENTION_POLICY,
)

ANALYST_REVIEWER_PATTERN_SPEC = BacktestPatternSpec(
    key=ANALYST_REVIEWER_TOPOLOGY.key,
    description=ANALYST_REVIEWER_TOPOLOGY.description,
    topology=ANALYST_REVIEWER_TOPOLOGY,
    mention_policy=ANALYST_REVIEWER_PATTERN_MENTION_POLICY,
)

SEEDED_TOOL_ENABLED_PATTERN_SPEC = BacktestPatternSpec(
    key="seeded_internal_backtest_tool_enabled_v1",
    description=(
        "Tool-enabled internal backtest workflow with the seeded topology and Ledger-native "
        "read-only capability metadata."
    ),
    topology=SEEDED_TOPOLOGY,
    mention_policy=SEED_PATTERN_MENTION_POLICY,
    execution_mode="tool_enabled",
    default_tool_ids=(
        _REPORT_LOOKUP_TOOL_ID,
        _ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID,
        _CYCLE_CONTEXT_LOOKUP_TOOL_ID,
    ),
    allowed_bundle_keys=(_LIBRARIAN_CONTEXT_BUNDLE_KEY, _EXPLORE_CONTEXT_BUNDLE_KEY),
)

ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC = BacktestPatternSpec(
    key="analyst_reviewer_tool_enabled_v1",
    description=(
        "Tool-enabled reviewer workflow that preserves conservative review while enabling "
        "Ledger-native read-only capability metadata."
    ),
    topology=ANALYST_REVIEWER_TOPOLOGY,
    mention_policy=ANALYST_REVIEWER_PATTERN_MENTION_POLICY,
    execution_mode="tool_enabled",
    default_tool_ids=(
        _REPORT_LOOKUP_TOOL_ID,
        _ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID,
        _CYCLE_CONTEXT_LOOKUP_TOOL_ID,
    ),
    allowed_bundle_keys=(_LIBRARIAN_CONTEXT_BUNDLE_KEY, _EXPLORE_CONTEXT_BUNDLE_KEY),
)

BACKTEST_PATTERN_SPECS: tuple[BacktestPatternSpec, ...] = (
    SEEDED_PATTERN_SPEC,
    ANALYST_REVIEWER_PATTERN_SPEC,
    SEEDED_TOOL_ENABLED_PATTERN_SPEC,
    ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC,
)

BACKTEST_PATTERN_REGISTRY: dict[str, BacktestPatternSpec] = {
    pattern.key: pattern for pattern in BACKTEST_PATTERN_SPECS
}

SUPPORTED_BACKTEST_ORCHESTRATION_PATTERN_KEYS: tuple[str, ...] = tuple(
    pattern.key for pattern in BACKTEST_PATTERN_SPECS
)

DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY = SEEDED_TOPOLOGY.key


def get_seeded_tool_spec(tool_id: str) -> SeededToolSpec | None:
    return SEEDED_TOOL_REGISTRY.get(tool_id)


def get_seeded_capability_bundle_spec(bundle_key: str) -> SeededCapabilityBundleSpec | None:
    return SEEDED_CAPABILITY_BUNDLE_REGISTRY.get(bundle_key)


def get_seeded_connector_spec(connector_id: str) -> SeededConnectorSpec | None:
    return SEEDED_CONNECTOR_REGISTRY.get(connector_id)


def get_backtest_pattern_spec(pattern_key: str) -> BacktestPatternSpec | None:
    return BACKTEST_PATTERN_REGISTRY.get(pattern_key)


def list_supported_backtest_orchestration_pattern_keys() -> tuple[str, ...]:
    return SUPPORTED_BACKTEST_ORCHESTRATION_PATTERN_KEYS


def _build_langgraph_runner_for_pattern(
    *,
    pattern_key: str,
    topology: SeededTopology,
    analyzer: BacktestSymbolAnalyzer,
) -> BacktestLangGraphRunner:
    return BacktestLangGraphRunner(
        analyzer=analyzer,
        topology_key=pattern_key,
        agent_keys=topology.agent_order,
        review_mode=topology.review_mode,
    )


def build_seeded_langgraph_runner(*, analyzer: BacktestSymbolAnalyzer) -> BacktestLangGraphRunner:
    return _build_langgraph_runner_for_pattern(
        pattern_key=SEEDED_TOPOLOGY.key,
        topology=SEEDED_TOPOLOGY,
        analyzer=analyzer,
    )


def build_analyst_reviewer_langgraph_runner(
    *, analyzer: BacktestSymbolAnalyzer
) -> BacktestLangGraphRunner:
    return _build_langgraph_runner_for_pattern(
        pattern_key=ANALYST_REVIEWER_TOPOLOGY.key,
        topology=ANALYST_REVIEWER_TOPOLOGY,
        analyzer=analyzer,
    )


def is_supported_backtest_orchestration_pattern_key(pattern_key: str) -> bool:
    return get_backtest_pattern_spec(pattern_key) is not None


def build_backtest_langgraph_runner(
    *, pattern_key: str, analyzer: BacktestSymbolAnalyzer
) -> BacktestLangGraphRunner:
    pattern_spec = get_backtest_pattern_spec(pattern_key)
    if pattern_spec is None:
        raise ValueError(f"Unknown orchestration pattern: {pattern_key}")

    return _build_langgraph_runner_for_pattern(
        pattern_key=pattern_spec.key,
        topology=pattern_spec.topology,
        analyzer=analyzer,
    )
