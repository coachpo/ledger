from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConnectorLifecycle = Literal["placeholder", "approved"]


@dataclass(frozen=True)
class SeededAgentSpec:
    key: str
    role: str
    system_prompt: str


@dataclass(frozen=True)
class SeededBuiltinSpec:
    handle: str
    canonical_target_id: str
    display_name: str
    description: str
    revision: int
    capability_bundle_keys: tuple[str, ...] = ()


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


_REPORT_LOOKUP_TOOL_ID = "ledger.report_lookup"
_ORCHESTRATION_CATALOG_LOOKUP_TOOL_ID = "ledger.orchestration_catalog_lookup"
_CYCLE_CONTEXT_LOOKUP_TOOL_ID = "ledger.cycle_context_lookup"

_LIBRARIAN_CONTEXT_BUNDLE_KEY = "builtin.librarian_context"
_EXPLORE_CONTEXT_BUNDLE_KEY = "builtin.explore_context"

_MARKET_DATA_MCP_CONNECTOR_ID = "ledger.mcp.market_data"
_COMPANY_FILINGS_MCP_CONNECTOR_ID = "ledger.mcp.company_filings"


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
            "Render the final analysis report and translate reviewed analyses into "
            "Ledger trade decisions."
        ),
    ),
)


SEEDED_BUILTIN_SPECS: tuple[SeededBuiltinSpec, ...] = (
    SeededBuiltinSpec(
        handle="librarian",
        canonical_target_id="builtin:librarian",
        display_name="Librarian",
        description="Research and retrieve supporting context for runtime workflows.",
        revision=1,
        capability_bundle_keys=(_LIBRARIAN_CONTEXT_BUNDLE_KEY,),
    ),
    SeededBuiltinSpec(
        handle="explore",
        canonical_target_id="builtin:explore",
        display_name="Explore",
        description="Inspect the current runtime state and summarize relevant findings.",
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
        description="Read prepared cycle prompt and runtime artifacts for the current run.",
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


def get_seeded_builtin_spec_for_handle(handle: str) -> SeededBuiltinSpec | None:
    return SEEDED_BUILTIN_HANDLE_REGISTRY.get(handle)


def get_seeded_tool_spec(tool_id: str) -> SeededToolSpec | None:
    return SEEDED_TOOL_REGISTRY.get(tool_id)


def get_seeded_capability_bundle_spec(bundle_key: str) -> SeededCapabilityBundleSpec | None:
    return SEEDED_CAPABILITY_BUNDLE_REGISTRY.get(bundle_key)


def get_seeded_connector_spec(connector_id: str) -> SeededConnectorSpec | None:
    return SEEDED_CONNECTOR_REGISTRY.get(connector_id)


__all__ = [
    "ConnectorLifecycle",
    "SEEDED_AGENT_SPECS",
    "SEEDED_BUILTIN_HANDLE_REGISTRY",
    "SEEDED_BUILTIN_REGISTRY",
    "SEEDED_BUILTIN_RESERVED_TARGETS",
    "SEEDED_BUILTIN_SPECS",
    "SEEDED_CAPABILITY_BUNDLE_REGISTRY",
    "SEEDED_CAPABILITY_BUNDLE_SPECS",
    "SEEDED_CONNECTOR_REGISTRY",
    "SEEDED_CONNECTOR_SPECS",
    "SEEDED_TOOL_REGISTRY",
    "SEEDED_TOOL_SPECS",
    "SeededAgentSpec",
    "SeededBuiltinSpec",
    "SeededCapabilityBundleSpec",
    "SeededConnectorSpec",
    "SeededToolSpec",
    "get_seeded_builtin_spec_for_handle",
    "get_seeded_capability_bundle_spec",
    "get_seeded_connector_spec",
    "get_seeded_tool_spec",
]
