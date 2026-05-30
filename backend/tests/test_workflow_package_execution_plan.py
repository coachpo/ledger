# pyright: reportMissingImports=false, reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportUnknownLambdaType=false
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, cast

import pytest

from app.schemas.model_connection import default_model_connection_capabilities
from app.services.agent_execution_service import AgentExecutionService
from app.services.execution_plan import PackageResolvedModelBinding
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import (
    _valid_http_sse_package_manifest_source,
    _valid_package_manifest_source,
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


def test_package_execution_plan_builds_from_local_compiled_plan_without_global_rows() -> None:
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
        ("signaldeck.market_data.quote_lookup",)
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


def _graph_package_manifest_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: graph_package
  name: Graph Package
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles:
    - key: graph_tools
      name: Graph Tools
      toolKeys:
        - signaldeck.market_data.quote_lookup
  outputSchemas:
    - key: graph_note
      name: Graph Note
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  mcpServers:
    - key: graph_context
      name: Graph Context
      transport: stdio
      command: python
      args: [server.py]
  agents:
    - key: market_agent
      name: Market Agent
      modelConnection: graph_model
      systemPrompt: Return market output.
      inputSchema:
        type: object
      outputSchema: graph_note
      capabilityProfiles: [graph_tools]
      mcpServers: [graph_context]
    - key: news_agent
      name: News Agent
      modelConnection: graph_model
      systemPrompt: Return news output.
      inputSchema:
        type: object
      outputSchema: graph_note
      capabilityProfiles: [graph_tools]
      mcpServers: [graph_context]
    - key: risk_agent
      name: Risk Agent
      modelConnection: graph_model
      systemPrompt: Return risk output.
      inputSchema:
        type: object
      outputSchema: graph_note
      capabilityProfiles: [graph_tools]
      mcpServers: [graph_context]
    - key: decision_agent
      name: Decision Agent
      modelConnection: graph_model
      systemPrompt: Return final output.
      inputSchema:
        type: object
      outputSchema: graph_note
      capabilityProfiles: [graph_tools]
      mcpServers: [graph_context]
  workflows:
    - key: advisory_research
      name: Advisory Research
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: sequence
        id: root_sequence
        nodes:
          - kind: fanout
            id: analyst_fanout
            branches:
              - id: market
                node:
                  kind: step
                  id: market_analysis
                  slot: market
                  uses: market_agent
                  with:
                    ticker: ${{ inputs.ticker }}
              - id: news
                node:
                  kind: step
                  id: news_analysis
                  slot: news
                  uses: news_agent
                  with:
                    ticker: ${{ inputs.ticker }}
          - kind: loop
            id: review_loop
            maxIterations: 2
            sequence:
              kind: sequence
              id: review_sequence
              nodes:
                - kind: step
                  id: risk_review
                  slot: risk
                  uses: risk_agent
                  with:
                    ticker: ${{ inputs.ticker }}
          - kind: step
            id: decision
            slot: final
            uses: decision_agent
            with:
              marketReport: ${{ nodes.analyst_fanout.outputs.market }}
              newsReport: ${{ nodes.analyst_fanout.outputs.news }}
              riskReport: ${{ nodes.review_loop.outputs.risk }}
      output:
        from: ${{ nodes.root_sequence.outputs.final }}
"""


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
