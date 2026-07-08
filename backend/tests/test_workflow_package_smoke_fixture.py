from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo"

EXPECTED_AGENT_KEYS = {
    "market_analyst",
    "sentiment_analyst",
    "news_analyst",
    "fundamentals_analyst",
    "bull_researcher",
    "bear_researcher",
    "research_manager",
    "trader",
    "aggressive_risk_analyst",
    "neutral_risk_analyst",
    "conservative_risk_analyst",
    "portfolio_manager",
}
EXPECTED_OUTPUT_SCHEMA_KEYS = {
    "analyst_report",
    "investment_debate_transition",
    "research_plan",
    "trader_proposal",
    "risk_debate_transition",
    "portfolio_decision",
}
EXPECTED_TOOL_KEYS = {
    "signaldeck.finance.market_data.quote_lookup",
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
    "signaldeck.finance.indicators.lookup",
    "signaldeck.finance.fundamentals.lookup",
    "signaldeck.finance.news.lookup",
    "signaldeck.finance.social_sentiment.lookup",
    "signaldeck.finance.insider_data.lookup",
    "signaldeck.finance.reports.lookup",
}
FORBIDDEN_EXPORT_FIELDS = {
    "secretPayload",
    "encrypted",
    "modelConnectionId",
    "outputSchemaId",
    "capabilityId",
    "mcpServerId",
}


def _fixture_source() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _profile_tool_keys(package_definition: dict[str, object]) -> set[str]:
    spec = cast(dict[str, object], package_definition["spec"])
    return {
        tool_key
        for profile in cast(list[dict[str, object]], spec["capabilityProfiles"])
        for tool_key in cast(list[str], profile["toolKeys"])
    }


def _compiled_operation_ids(compiled_plan: dict[str, object]) -> set[str]:
    return {
        str(operation["operationKey"])
        for workflow in cast(list[dict[str, object]], compiled_plan["workflows"])
        for step in cast(list[dict[str, object]], workflow["steps"])
        for operation in cast(list[dict[str, object]], step.get("operations", []))
    }


def test_tradingagents_advisory_research_fixture_compiles_and_exports_cleanly() -> None:
    source = _fixture_source()
    parsed = parse_workflow_package_manifest(source)

    assert parsed.diagnostics == []
    assert parsed.manifest is not None
    assert parsed.manifest.metadata.key == "tradingagents_advisory_research"

    compiled = compile_workflow_package_manifest(source)
    assert "modelConnection: tradingagents_primary_model" in source
    assert "tradingagents_advisory_research" in source
    assert "advisory_research" in source

    serialized = _canonical_json(compiled) + source
    for forbidden_field in FORBIDDEN_EXPORT_FIELDS:
        assert forbidden_field not in serialized
    assert "secretRefs" not in serialized
    assert "requiredBindings" not in serialized

    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    spec = cast(dict[str, object], package_definition["spec"])
    workflows = cast(list[dict[str, object]], compiled_plan["workflows"])
    workflow = workflows[0]
    compiled_graph = cast(dict[str, object], workflow["compiledGraph"])
    compiled_nodes = cast(list[dict[str, object]], compiled_graph["nodes"])

    assert compiled_plan["packageKey"] == "tradingagents_advisory_research"
    assert [workflow["key"] for workflow in workflows] == [
        "advisory_research",
        "fundamentals_research",
        "market_research",
        "news_research",
    ]
    assert compiled_graph["rootNodeId"] == "root_sequence"
    assert compiled_nodes[0]["kind"] == "sequence"
    assert workflow["outputSpec"] == {"kind": "slot", "stepIndex": 17, "slot": "portfolio_decision"}
    assert {
        agent["key"] for agent in cast(list[dict[str, object]], spec["agents"])
    } == EXPECTED_AGENT_KEYS
    assert {
        schema["key"] for schema in cast(list[dict[str, object]], spec["outputSchemas"])
    } == EXPECTED_OUTPUT_SCHEMA_KEYS
    assert cast(list[dict[str, object]], spec["mcpServers"]) == []
    assert {str(agent["key"]): agent for agent in cast(list[dict[str, object]], spec["agents"])}
    assert _profile_tool_keys(package_definition) == EXPECTED_TOOL_KEYS

    compiled_agents = cast(list[dict[str, object]], compiled_plan["agents"])
    assert {agent["key"] for agent in compiled_agents} == EXPECTED_AGENT_KEYS
    assert {agent["modelConnection"] for agent in compiled_agents} == {
        "tradingagents_primary_model"
    }
    assert {str(agent["key"]): agent for agent in compiled_agents}
    assert any(cast(list[str], agent["capabilityProfiles"]) for agent in compiled_agents)


def test_tradingagents_fixture_declares_report_lookup_profile() -> None:
    compiled = compile_workflow_package_manifest(_fixture_source())
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    assert cast(list[str], profiles_by_key["report_context_tools"]["toolKeys"]) == [
        "signaldeck.finance.reports.lookup"
    ]


def test_demo_fixture_variants_lock_tool_ownership_and_private_operations() -> None:
    expectations: dict[str, tuple[set[str], set[str]]] = {
        "tradingagents_advisory_research.yaml": (EXPECTED_TOOL_KEYS, set()),
    }

    for filename, (expected_tool_keys, expected_http_ids) in expectations.items():
        compiled = compile_workflow_package_manifest((DEMO_ROOT / filename).read_text())
        package_definition = cast(dict[str, object], compiled["packageDefinition"])
        compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
        spec = cast(dict[str, object], package_definition["spec"])
        mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
        operation_ids = _compiled_operation_ids(compiled_plan)

        assert _profile_tool_keys(package_definition) == expected_tool_keys
        assert expected_http_ids <= operation_ids
        assert mcp_servers == []
        assert not operation_ids
