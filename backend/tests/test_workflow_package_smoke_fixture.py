from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.output_schema import OutputSchema
from app.models.workflow import Workflow
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)

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
    "signaldeck.market_data.quote_lookup",
    "signaldeck.market_data.history_lookup",
    "signaldeck.market_data.ohlcv_lookup",
    "signaldeck.indicators.lookup",
    "signaldeck.fundamentals.lookup",
    "signaldeck.news.lookup",
    "signaldeck.social_sentiment.lookup",
    "signaldeck.insider_data.lookup",
    "signaldeck.positions.lookup",
    "signaldeck.reports.lookup",
    "signaldeck.reports.write",
}
FORBIDDEN_EXPORT_FIELDS = {
    "secretPayload",
    "encrypted",
    "modelConnectionId",
    "outputSchemaId",
    "capabilityId",
    "mcpServerId",
}
SPECIAL_CASE_RE = re.compile(
    "|".join(
        (
            r"tradingagents",
            r"TradingAgents",
            r"advisory_research",
            r"workflow_id\s*(?:==|=)\s*2",
            r"workflowId\s*(?:===|==|=)\s*2",
            r"workflow\.id\s*==\s*2",
        )
    )
)


def _fixture_source() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _table_count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_tradingagents_advisory_research_fixture_compiles_and_exports_cleanly() -> None:
    source = _fixture_source()
    parsed = parse_workflow_package_manifest(source)

    assert parsed.diagnostics == []
    assert parsed.manifest is not None
    assert parsed.manifest.metadata.key == "tradingagents_advisory_research"

    compiled = compile_workflow_package_manifest(source)
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)

    assert _canonical_json(compiled) == _canonical_json(recompiled)
    assert "modelConnection: tradingagents_primary_model" in roundtrip.source
    assert "tradingagents_advisory_research" in roundtrip.source
    assert "advisory_research" in roundtrip.source

    serialized = _canonical_json(compiled) + roundtrip.source
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
    assert [workflow["key"] for workflow in workflows] == ["advisory_research"]
    assert compiled_graph["rootNodeId"] == "root_sequence"
    assert compiled_nodes[0]["kind"] == "sequence"
    assert "kind: sequence\n            id: analyst_research" in roundtrip.source
    assert "kind: fanout" not in source
    assert workflow["outputSpec"] == {"kind": "slot", "stepIndex": 17, "slot": "portfolio_decision"}
    assert {
        agent["key"] for agent in cast(list[dict[str, object]], spec["agents"])
    } == EXPECTED_AGENT_KEYS
    assert {
        schema["key"] for schema in cast(list[dict[str, object]], spec["outputSchemas"])
    } == EXPECTED_OUTPUT_SCHEMA_KEYS
    assert cast(list[dict[str, object]], spec["mcpServers"]) == []
    assert "Authorization: Bearer exa-inline-token" not in roundtrip.source
    assert "exaApiKey: exa-inline-key" not in roundtrip.source
    assert {str(agent["key"]): agent for agent in cast(list[dict[str, object]], spec["agents"])}
    profile_tool_keys = {
        tool_key
        for profile in cast(list[dict[str, object]], spec["capabilityProfiles"])
        for tool_key in cast(list[str], profile["toolKeys"])
    }
    assert profile_tool_keys == EXPECTED_TOOL_KEYS

    compiled_agents = cast(list[dict[str, object]], compiled_plan["agents"])
    assert {agent["key"] for agent in compiled_agents} == EXPECTED_AGENT_KEYS
    assert {agent["modelConnection"] for agent in compiled_agents} == {
        "tradingagents_primary_model"
    }
    assert {str(agent["key"]): agent for agent in compiled_agents}
    assert any(cast(list[str], agent["capabilityProfiles"]) for agent in compiled_agents)


def test_tradingagents_fixture_keeps_report_lookup_and_write_in_memory_profile() -> None:
    compiled = compile_workflow_package_manifest(_fixture_source())
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    assert cast(list[str], profiles_by_key["report_context_tools"]["toolKeys"]) == [
        "signaldeck.reports.lookup"
    ]
    assert cast(list[str], profiles_by_key["memory_write_tools"]["toolKeys"]) == [
        "signaldeck.reports.lookup",
        "signaldeck.reports.write",
    ]


def test_fixture_compile_does_not_create_global_authoring_rows(
    session_factory: sessionmaker[Session],
) -> None:
    source = _fixture_source()
    global_models = [Agent, Workflow, Capability, McpServer, OutputSchema]

    with session_factory() as session:
        before_counts = {model: _table_count(session, model) for model in global_models}
        compiled = compile_workflow_package_manifest(source)
        roundtrip = decompile_workflow_package_manifest(compiled)
        _ = compile_workflow_package_manifest(roundtrip.source)
        after_counts = {model: _table_count(session, model) for model in global_models}

    assert before_counts == after_counts == {model: 0 for model in global_models}


def test_backend_implementation_does_not_special_case_tradingagents_or_old_workflow_id() -> None:
    backend_app = Path(__file__).parents[1] / "app"
    matches: list[str] = []
    for path in backend_app.rglob("*.py"):
        relative_path = path.relative_to(backend_app.parents[0])
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if SPECIAL_CASE_RE.search(line):
                matches.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert matches == []
