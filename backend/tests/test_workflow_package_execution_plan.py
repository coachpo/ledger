# pyright: reportMissingImports=false, reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportUnknownLambdaType=false
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from app.schemas.model_connection import default_model_connection_capabilities
from app.services.agent_execution_service import AgentExecutionService
from app.services.execution_plan import ExecutionPlanAgent, PackageResolvedModelBinding
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.fixtures.workflow_manifests import base_manifest
from tests.test_workflow_package_manifest_parser import (
    _valid_http_sse_package_manifest_source,
    _valid_package_manifest_source,
)

_DIGITAL_ORACLE_RESEARCHER_DEMO = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)


def _compiled_plan(source: str | None = None) -> dict[str, Any]:
    compiled = compile_workflow_package_manifest(source or _valid_package_manifest_source())
    return cast(dict[str, Any], compiled["compiledPlan"])


def _model_binding(key: str = "tradingagents_primary_model") -> PackageResolvedModelBinding:
    protocol_profile = "openai_responses"
    return PackageResolvedModelBinding(
        key=key,
        name="Package Model",
        protocol_profile=protocol_profile,
        base_url="https://api.openai.com/v1",
        model_id="gpt-5.4-mini",
        reasoning_effort="medium",
        capabilities=default_model_connection_capabilities(protocol_profile).model_dump(
            mode="json",
            by_alias=True,
        ),
        output_strategy_policy="prefer_strict_schema",
        parallel_tool_calls_policy="serialize",
        reasoning_policy="allow",
        streaming_policy="allow",
        probe_cache_ttl_seconds=900,
        api_style="responses",
        timeout_seconds=60,
        has_api_key=True,
    )


def test_execution_plan_agent_requires_package_runtime_spec() -> None:
    constructor = cast(Callable[..., ExecutionPlanAgent], ExecutionPlanAgent)
    with pytest.raises(TypeError):
        _ = constructor(
            slot="analysis",
            agent_id=1,
            agent_key="market_analyst",
            agent_version=1,
            output_schema_id=1,
            output_schema_version=1,
            wiring={},
        )


def test_package_execution_plan_builds_from_local_compiled_plan() -> None:
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(),
        "daily_research",
        model_bindings={"tradingagents_primary_model": _model_binding()},
    )

    assert plan.target.kind == "workflow_package"
    assert plan.target.id == 1
    assert plan.target.key == "daily_research"
    assert plan.target.version is None
    assert plan.input_schema["properties"]["ticker"] == {"type": "string"}
    assert len(plan.steps) == 1
    invocation = plan.steps[0].agents[0]
    assert invocation.agent_id == 1
    assert invocation.agent_key == "market_analyst"
    assert invocation.output_schema_id == 1
    assert invocation.wiring["ticker"].source == "input"
    assert invocation.wiring["ticker"].path == "ticker"
    assert plan.final_output.step_index == 1
    assert plan.final_output.slot == "decision"
    assert plan.package_workflow is not None
    runtime_agent = invocation.package_runtime_agent
    assert runtime_agent is not None
    assert runtime_agent.model_binding == _model_binding()
    assert runtime_agent.model_binding is not None
    assert runtime_agent.output_schema.key == "trading_decision"
    assert [profile.key for profile in runtime_agent.capability_profiles] == [
        "market_research_tools"
    ]
    assert [profile.tool_keys for profile in runtime_agent.capability_profiles] == [
        ("signaldeck.finance.market_data.quote_lookup",)
    ]
    assert [server.key for server in runtime_agent.mcp_servers] == ["research_context"]
    server = runtime_agent.mcp_servers[0]
    assert server.env == {"RESEARCH_CONTEXT_TOKEN": "local-token"}
    assert server.headers == {}
    assert server.query == {}


def test_package_execution_plan_threads_private_mcp_flat_maps_into_runtime_refs() -> None:
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(_valid_http_sse_package_manifest_source()),
        "daily_research",
        model_bindings={"tradingagents_primary_model": _model_binding()},
    )

    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    server = runtime_agent.mcp_servers[0]
    assert server.key == "research_context"
    assert server.command is None
    assert server.args == ()
    assert server.url == "https://mcp.example.test/sse"
    assert server.env == {}
    assert server.headers == {"Authorization": "Bearer test-token"}
    assert server.query == {"api_key": "test-api-key"}

    runtime_refs = AgentExecutionService._runtime_mcp_server_refs(runtime_agent)
    assert runtime_refs == [
        {
            "packagePrivate": True,
            "key": "research_context",
            "name": "Research Context",
            "description": "Local context server declaration.",
            "transport": "http-sse",
            "command": None,
            "args": [],
            "url": "https://mcp.example.test/sse",
            "env": {},
            "headers": {"Authorization": "Bearer test-token"},
            "query": {"api_key": "test-api-key"},
            "toolKeys": ["research_context.search"],
            "toolDescriptors": [],
        }
    ]


def test_package_execution_plan_supports_step_and_fanout_roots() -> None:
    step_root_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(),
        "daily_research",
        model_bindings={"tradingagents_primary_model": _model_binding()},
    )
    fanout_root_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(_fanout_root_package_manifest_source()),
        "advisory_research",
        model_bindings={"graph_model": _model_binding("graph_model")},
    )

    assert [agent.slot for agent in step_root_plan.steps[0].agents] == ["decision"]
    assert [step.index for step in fanout_root_plan.steps] == [1, 2]
    assert [[agent.slot for agent in step.agents] for step in fanout_root_plan.steps] == [
        ["market"],
        ["news"],
    ]
    assert fanout_root_plan.final_output.step_index == 1
    assert fanout_root_plan.final_output.slot == "market"


def _graph_package_manifest_source() -> str:
    return _graph_manifest_source(
        package_key="graph_package",
        package_name="Graph Package",
        agent_keys=("market_agent", "news_agent", "risk_agent", "decision_agent"),
        flow={
            "kind": "sequence",
            "id": "root_sequence",
            "nodes": [
                {
                    "kind": "fanout",
                    "id": "analyst_fanout",
                    "branches": [
                        {
                            "id": "market",
                            "node": {
                                "kind": "step",
                                "id": "market_analysis",
                                "slot": "market",
                                "uses": "market_agent",
                                "with": {"ticker": "${{ inputs.ticker }}"},
                            },
                        },
                        {
                            "id": "news",
                            "node": {
                                "kind": "step",
                                "id": "news_analysis",
                                "slot": "news",
                                "uses": "news_agent",
                                "with": {"ticker": "${{ inputs.ticker }}"},
                            },
                        },
                    ],
                },
                {
                    "kind": "loop",
                    "id": "review_loop",
                    "maxIterations": 2,
                    "sequence": {
                        "kind": "sequence",
                        "id": "review_sequence",
                        "nodes": [
                            {
                                "kind": "step",
                                "id": "risk_review",
                                "slot": "risk",
                                "uses": "risk_agent",
                                "with": {"ticker": "${{ inputs.ticker }}"},
                            }
                        ],
                    },
                },
                {
                    "kind": "step",
                    "id": "decision",
                    "slot": "final",
                    "uses": "decision_agent",
                    "with": {
                        "marketReport": "${{ nodes.analyst_fanout.outputs.market }}",
                        "newsReport": "${{ nodes.analyst_fanout.outputs.news }}",
                        "riskReport": "${{ nodes.review_loop.outputs.risk }}",
                    },
                },
            ],
        },
        output_reference="${{ nodes.root_sequence.outputs.final }}",
    )


def _fanout_root_package_manifest_source() -> str:
    return _graph_manifest_source(
        package_key="fanout_root_package",
        package_name="Fanout Root Package",
        agent_keys=("market_agent", "news_agent"),
        flow={
            "kind": "fanout",
            "id": "analyst_fanout",
            "branches": [
                {
                    "id": "market",
                    "node": {
                        "kind": "step",
                        "id": "market_analysis",
                        "slot": "market",
                        "uses": "market_agent",
                        "with": {"ticker": "${{ inputs.ticker }}"},
                    },
                },
                {
                    "id": "news",
                    "node": {
                        "kind": "step",
                        "id": "news_analysis",
                        "slot": "news",
                        "uses": "news_agent",
                        "with": {"ticker": "${{ inputs.ticker }}"},
                    },
                },
            ],
        },
        output_reference="${{ nodes.analyst_fanout.outputs.market }}",
    )


def _graph_manifest_source(
    *,
    package_key: str,
    package_name: str,
    agent_keys: tuple[str, ...],
    flow: dict[str, Any],
    output_reference: str,
) -> str:
    input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    }
    agent_names = {
        "market_agent": "Market Agent",
        "news_agent": "News Agent",
        "risk_agent": "Risk Agent",
        "decision_agent": "Decision Agent",
    }
    prompts = {
        "market_agent": "Return market output.",
        "news_agent": "Return news output.",
        "risk_agent": "Return risk output.",
        "decision_agent": "Return final output.",
    }
    return base_manifest(
        package_key=package_key,
        package_name=package_name,
        package_description=None,
        input_schema=input_schema,
        capability_profiles=[
            {
                "key": "graph_tools",
                "name": "Graph Tools",
                "toolKeys": ["signaldeck.finance.market_data.quote_lookup"],
            }
        ],
        output_schema_key="graph_note",
        output_schemas=[
            {
                "key": "graph_note",
                "name": "Graph Note",
                "jsonSchema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                },
            }
        ],
        mcp_servers=[
            {
                "key": "graph_context",
                "name": "Graph Context",
                "transport": "stdio",
                "command": "python",
                "args": ["server.py"],
            }
        ],
        agents=[
            {
                "key": agent_key,
                "name": agent_names[agent_key],
                "modelConnection": "graph_model",
                "systemPrompt": prompts[agent_key],
                "inputSchema": {"type": "object"},
                "outputSchema": "graph_note",
                "capabilityProfiles": ["graph_tools"],
                "mcpServers": ["graph_context"],
            }
            for agent_key in agent_keys
        ],
        workflows=[
            {
                "key": "advisory_research",
                "name": "Advisory Research",
                "inputSchema": input_schema,
                "flow": flow,
                "output": {"from": output_reference},
            }
        ],
    )


def test_digital_oracle_demo_execution_plan_uses_fanout_then_synthesis() -> None:
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(_DIGITAL_ORACLE_RESEARCHER_DEMO.read_text()),
        "research",
        model_bindings={
            "digital_oracle_primary_model": _model_binding("digital_oracle_primary_model")
        },
    )

    assert [step.index for step in plan.steps] == list(range(1, 8))
    assert [[agent.slot for agent in step.agents] for step in plan.steps] == [
        ["market_signals"],
        ["filing_signals"],
        ["sentiment_search_signals"],
        ["macro_evidence"],
        ["web_evidence"],
        ["sec_metadata"],
        ["report"],
    ]
    assert [[operation.slot for operation in step.operations] for step in plan.steps] == [
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    ]
    assert plan.final_output.step_index == 7
    assert plan.final_output.slot == "report"
    fanout_metadata = [plan.steps[index].agents[0].graph_metadata for index in range(3)]
    assert all(metadata is not None for metadata in fanout_metadata)
    assert [metadata.branch_id for metadata in fanout_metadata if metadata is not None] == [
        "market_signals",
        "filing_signals",
        "sentiment_search_signals",
    ]
    assert [metadata.fanout_id for metadata in fanout_metadata if metadata is not None] == [
        "evidence_fanout",
        "evidence_fanout",
        "evidence_fanout",
    ]
    synthesis = plan.steps[6].agents[0]
    assert synthesis.agent_key == "digital_oracle_synthesizer"
    assert synthesis.graph_metadata is not None
    assert synthesis.graph_metadata.source_refs == {
        "researchQuestion": {"source": "inputs", "path": "researchQuestion"},
        "outputLanguage": {"source": "inputs", "path": "outputLanguage"},
        "marketSignals": {
            "source": "nodes",
            "nodeId": "market_signals",
            "slot": "market_signals",
            "stepIndex": 1,
            "compiledSlot": "market_signals",
        },
        "filingSignals": {
            "source": "nodes",
            "nodeId": "filing_signals",
            "slot": "filing_signals",
            "stepIndex": 2,
            "compiledSlot": "filing_signals",
        },
        "sentimentSearchSignals": {
            "source": "nodes",
            "nodeId": "sentiment_search_signals",
            "slot": "sentiment_search_signals",
            "stepIndex": 3,
            "compiledSlot": "sentiment_search_signals",
        },
        "macroEvidence": {
            "source": "nodes",
            "nodeId": "macro_evidence_collect",
            "slot": "macro_evidence",
            "stepIndex": 4,
            "compiledSlot": "macro_evidence",
        },
        "webEvidence": {
            "source": "nodes",
            "nodeId": "web_evidence_collect",
            "slot": "web_evidence",
            "stepIndex": 5,
            "compiledSlot": "web_evidence",
        },
        "secMetadataEvidence": {
            "source": "nodes",
            "nodeId": "sec_metadata_collect",
            "slot": "sec_metadata",
            "stepIndex": 6,
            "compiledSlot": "sec_metadata",
        },
        "ticker": {"source": "inputs", "path": "ticker"},
        "cik": {"source": "inputs", "path": "cik"},
        "secSubmissionsUrl": {"source": "inputs", "path": "secSubmissionsUrl"},
        "asOfDate": {"source": "inputs", "path": "asOfDate"},
        "horizonDays": {"source": "inputs", "path": "horizonDays"},
    }
    assert plan.package_workflow is not None
    assert plan.package_workflow.package_key == "digital_oracle_researcher"
    assert plan.package_workflow.key == "research"
    assert plan.package_workflow.name == "Research"
    assert plan.package_workflow.final_output == plan.final_output
    assert plan.package_workflow.compiled_graph is not None
    assert plan.package_workflow.compiled_graph["rootNodeId"] == "research_sequence"
    compiled_nodes = cast(list[dict[str, object]], plan.package_workflow.compiled_graph["nodes"])
    assert [node["kind"] for node in compiled_nodes] == [
        "sequence",
        "fanout",
        "step",
        "step",
        "step",
        "step",
        "step",
        "step",
        "step",
    ]

    runtime_agents = [step.agents[0].package_runtime_agent for step in plan.steps if step.agents]
    assert [agent.key for agent in runtime_agents] == [
        "digital_oracle_signal_researcher",
        "digital_oracle_signal_researcher",
        "digital_oracle_signal_researcher",
        "macro_evidence_collector",
        "web_evidence_collector",
        "sec_metadata_collector",
        "digital_oracle_synthesizer",
    ]
    assert [agent.local_id for agent in runtime_agents] == [1, 1, 1, 3, 5, 4, 2]
    assert [agent.name for agent in runtime_agents] == [
        "Digital Oracle Signal Researcher",
        "Digital Oracle Signal Researcher",
        "Digital Oracle Signal Researcher",
        "Macro Evidence Collector",
        "Web Evidence Collector",
        "SEC Filing Evidence Collector",
        "Digital Oracle Synthesizer",
    ]
    assert [agent.model_binding for agent in runtime_agents] == [
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
        _model_binding("digital_oracle_primary_model"),
    ]
    assert [agent.output_schema.key for agent in runtime_agents] == [
        "digital_oracle_report",
        "digital_oracle_report",
        "digital_oracle_report",
        "macro_evidence_packet",
        "web_evidence_packet",
        "sec_metadata_packet",
        "digital_oracle_report",
    ]
    assert runtime_agents[0].output_schema.json_schema["required"] == [
        "summary",
        "signals",
        "horizons",
        "contradictions",
        "limitations",
        "nextQuestions",
    ]
    assert runtime_agents[0].input_schema["required"] == [
        "researchQuestion",
        "outputLanguage",
        "signalFocus",
    ]
    assert runtime_agents[6].input_schema["required"] == [
        "researchQuestion",
        "outputLanguage",
        "marketSignals",
        "filingSignals",
        "sentimentSearchSignals",
        "macroEvidence",
        "webEvidence",
        "secMetadataEvidence",
    ]

    expected_profile_tools = [
        (
            "digital_oracle_phase1_tools",
            (
                "signaldeck.digital_oracle.cftc_positioning.lookup",
                "signaldeck.digital_oracle.crypto_derivatives.lookup",
                "signaldeck.digital_oracle.macro_rates.lookup",
                "signaldeck.digital_oracle.market_sentiment.lookup",
                "signaldeck.digital_oracle.options.lookup",
                "signaldeck.digital_oracle.prediction_markets.lookup",
                "signaldeck.digital_oracle.sec_filings.lookup",
            ),
        )
    ]
    for runtime_agent in (
        runtime_agents[0],
        runtime_agents[1],
        runtime_agents[2],
        runtime_agents[6],
    ):
        assert [
            (profile.key, profile.tool_keys) for profile in runtime_agent.capability_profiles
        ] == expected_profile_tools
    assert [
        mcp_server["key"]
        for mcp_server in AgentExecutionService._runtime_mcp_server_refs(runtime_agents[4])
    ] == ["web_research"]
    for runtime_agent in (
        runtime_agents[0],
        runtime_agents[1],
        runtime_agents[2],
        runtime_agents[3],
        runtime_agents[5],
        runtime_agents[6],
    ):
        assert AgentExecutionService._runtime_mcp_server_refs(runtime_agent) == []


def test_package_execution_plan_preserves_fanout_loop_and_source_metadata() -> None:
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(_graph_package_manifest_source()),
        "advisory_research",
        model_bindings={"graph_model": _model_binding("graph_model")},
    )

    assert [step.index for step in plan.steps] == [1, 2, 3, 4, 5]
    assert [[agent.slot for agent in step.agents] for step in plan.steps] == [
        ["market"],
        ["news"],
        ["risk"],
        ["risk"],
        ["final"],
    ]
    market_metadata = plan.steps[0].agents[0].graph_metadata
    assert market_metadata is not None
    assert market_metadata.fanout_id == "analyst_fanout"
    assert market_metadata.branch_id == "market"
    assert market_metadata.source_refs == {"ticker": {"source": "inputs", "path": "ticker"}}
    assert plan.steps[2].agents[0].graph_metadata is not None
    assert plan.steps[2].agents[0].graph_metadata.loop_id == "review_loop"
    assert plan.steps[2].agents[0].graph_metadata.loop_iteration == 1
    assert plan.steps[3].agents[0].graph_metadata is not None
    assert plan.steps[3].agents[0].graph_metadata.loop_iteration == 2
    final_metadata = plan.steps[4].agents[0].graph_metadata
    assert final_metadata is not None
    assert final_metadata.source_refs is not None
    assert final_metadata.source_refs["riskReport"] == {
        "source": "nodes",
        "nodeId": "review_loop",
        "slot": "risk",
        "stepIndex": 4,
        "compiledSlot": "risk",
    }


PlanMutator = Callable[[dict[str, Any]], None]


@pytest.mark.parametrize(
    ("mutator", "workflow_key", "expected_field", "expected_issue"),
    [
        (
            lambda plan: cast(
                list[dict[str, Any]], cast(list[dict[str, Any]], plan["workflows"])[0]["steps"]
            )[0]["agents"][0].__setitem__("agentKey", "missing_agent"),
            "daily_research",
            "spec.workflows.daily_research.graph.steps[0].agents[0].agentRef",
            "missing_local_agent",
        ),
        (
            lambda plan: cast(list[dict[str, Any]], plan["agents"])[0].__setitem__(
                "outputSchema", "missing_schema"
            ),
            "daily_research",
            "spec.agents.market_analyst.outputSchema",
            "missing_local_output_schema",
        ),
        (
            lambda plan: cast(list[dict[str, Any]], plan["agents"])[0].__setitem__(
                "capabilityProfiles", ["missing_profile"]
            ),
            "daily_research",
            "spec.agents.market_analyst.capabilityProfiles[0]",
            "unknown_capability_profile",
        ),
        (
            lambda plan: cast(list[dict[str, Any]], plan["agents"])[0].__setitem__(
                "mcpServers", ["missing_context"]
            ),
            "daily_research",
            "spec.agents.market_analyst.mcpServers[0]",
            "unknown_mcp_config",
        ),
        (
            lambda plan: cast(
                list[dict[str, Any]],
                cast(
                    dict[str, Any],
                    cast(list[dict[str, Any]], plan["workflows"])[0]["compiledGraph"],
                )["nodes"],
            )[0].__setitem__("kind", "edge"),
            "daily_research",
            "spec.workflows.daily_research.compiledGraph.nodes[0].kind",
            "unsupported_graph_edge",
        ),
        (
            lambda plan: cast(
                list[dict[str, Any]], cast(list[dict[str, Any]], plan["workflows"])[0]["steps"]
            )[0]["agents"][0].__setitem__(
                "wiring", {"ticker": {"from": "step", "stepIndex": 1, "slot": "decision"}}
            ),
            "daily_research",
            "spec.workflows.daily_research.graph.steps[0].agents[0].with.ticker",
            "cycle",
        ),
        (
            lambda plan: cast(
                dict[str, Any], cast(list[dict[str, Any]], plan["workflows"])[0]["outputSpec"]
            ).__setitem__("stepIndex", 99),
            "daily_research",
            "spec.workflows.daily_research.output.from",
            "unreachable_node",
        ),
    ],
)
def test_package_execution_plan_errors_are_machine_readable(
    mutator: PlanMutator,
    workflow_key: str,
    expected_field: str,
    expected_issue: str,
) -> None:
    plan = deepcopy(_compiled_plan())
    mutator(plan)

    with pytest.raises(WorkflowPackageExecutionPlanError) as excinfo:
        _ = PackageExecutionPlanBuilder.build_from_compiled_plan(plan, workflow_key)

    assert excinfo.value.field == expected_field
    assert excinfo.value.issue == expected_issue
    assert excinfo.value.details == ({"field": expected_field, "issue": expected_issue},)


def test_package_execution_plan_reports_missing_entry_workflow() -> None:
    with pytest.raises(WorkflowPackageExecutionPlanError) as excinfo:
        _ = PackageExecutionPlanBuilder.build_from_compiled_plan(
            _compiled_plan(),
            "missing_workflow",
        )

    assert excinfo.value.field == "spec.workflows.missing_workflow"
    assert excinfo.value.issue == "missing_entry_workflow"
