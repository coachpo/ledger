from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from tests.fixtures.workflow_manifests import (
    base_manifest,
    dump_manifest,
    tradingagents_research_manifest,
    tradingagents_research_manifest_data,
)

_DIGITAL_ORACLE_RESEARCHER_DEMO = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)


def _valid_package_manifest_source() -> str:
    return tradingagents_research_manifest()


def _updated_valid_manifest(mutator: Callable[[dict[str, Any]], None]) -> str:
    data = tradingagents_research_manifest_data()
    mutator(data)
    return dump_manifest(data)


def _valid_http_sse_package_manifest_source() -> str:
    data = _valid_http_sse_package_manifest_data()
    return dump_manifest(data)


def _valid_http_sse_package_manifest_data() -> dict[str, Any]:
    data = tradingagents_research_manifest_data()
    data["spec"]["mcpServers"][0] = {
        "key": "research_context",
        "name": "Research Context",
        "description": "Local context server declaration.",
        "transport": "http-sse",
        "url": "https://mcp.example.test/sse",
        "headers": {"Authorization": "Bearer test-token"},
        "query": {"api_key": "test-api-key"},
        "toolKeys": ["research_context.search"],
    }
    return data


def _updated_http_sse_manifest(mutator: Callable[[dict[str, Any]], None]) -> str:
    data = _valid_http_sse_package_manifest_data()
    mutator(data)
    return dump_manifest(data)


def _with_duplicate_output_schema() -> str:
    data = tradingagents_research_manifest_data()
    data["spec"]["outputSchemas"].append(
        {
            "key": "trading_decision",
            "name": "Trading Decision Duplicate",
            "jsonSchema": {"type": "object"},
        }
    )
    return dump_manifest(data)


def _with_duplicate_agent() -> str:
    data = tradingagents_research_manifest_data()
    data["spec"]["agents"].append(
        {
            "key": "market_analyst",
            "name": "Market Analyst Duplicate",
            "modelConnection": "tradingagents_primary_model",
            "systemPrompt": "Test",
            "inputSchema": {"type": "object"},
            "outputSchema": "trading_decision",
        }
    )
    return dump_manifest(data)


def _with_duplicate_workflow() -> str:
    data = tradingagents_research_manifest_data()
    data["spec"]["workflows"].insert(
        0,
        {
            "key": "daily_research",
            "name": "Duplicate Daily Research",
            "inputSchema": {"type": "object"},
            "flow": {
                "kind": "step",
                "id": "duplicate_research",
                "slot": "duplicate_decision",
                "uses": "market_analyst",
            },
            "output": {"from": "${{ nodes.duplicate_research.outputs.duplicate_decision }}"},
        },
    )
    return dump_manifest(data)


def _single_diagnostic(source: str):
    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    return diagnostic


def _graph_package_manifest_source(*, flow: dict[str, Any], output_reference: str) -> str:
    input_schema = {"type": "object", "properties": {"ticker": {"type": "string"}}}
    agents = [
        {
            "key": "market_agent",
            "name": "Market Agent",
            "modelConnection": "graph_model",
            "systemPrompt": "Return market output.",
            "inputSchema": {"type": "object"},
            "outputSchema": "graph_note",
        },
        {
            "key": "news_agent",
            "name": "News Agent",
            "modelConnection": "graph_model",
            "systemPrompt": "Return news output.",
            "inputSchema": {"type": "object"},
            "outputSchema": "graph_note",
        },
        {
            "key": "decision_agent",
            "name": "Decision Agent",
            "modelConnection": "graph_model",
            "systemPrompt": "Return final output.",
            "inputSchema": {"type": "object"},
            "outputSchema": "graph_note",
        },
    ]
    return base_manifest(
        package_key="graph_package",
        package_name="Graph Package",
        package_description=None,
        input_schema=input_schema,
        output_schema_key="graph_note",
        output_schemas=[
            {
                "key": "graph_note",
                "name": "Graph Note",
                "jsonSchema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                },
            }
        ],
        agents=agents,
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


def test_parse_valid_workflow_package_manifest_returns_typed_manifest() -> None:
    result = parse_workflow_package_manifest(_valid_package_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.api_version == "signaldeck.workflowPackage/v1"
    assert result.manifest.kind == "WorkflowPackage"
    assert result.manifest.metadata.key == "tradingagents_research"
    assert result.manifest.spec.agents[0].model_connection == "tradingagents_primary_model"
    assert result.manifest.spec.agents[0].output_schema == "trading_decision"
    assert result.manifest.spec.workflows[0].flow.id == "market_analysis"

    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    spec = cast(dict[str, object], dumped["spec"])
    agents = cast(list[dict[str, object]], spec["agents"])
    capability_profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    assert set(agents[0]) == {
        "key",
        "name",
        "description",
        "modelConnection",
        "systemPrompt",
        "inputSchema",
        "outputSchema",
        "capabilityProfiles",
        "mcpServers",
    }
    assert agents[0]["modelConnection"] == "tradingagents_primary_model"
    assert capability_profiles[0]["toolKeys"] == ["signaldeck.finance.market_data.quote_lookup"]
    assert mcp_servers[0] == {
        "key": "research_context",
        "name": "Research Context",
        "description": "Local context server declaration.",
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "url": None,
        "env": {"RESEARCH_CONTEXT_TOKEN": "local-token"},
        "headers": {},
        "query": {},
        "toolKeys": ["research_context.search"],
    }


def test_parse_digital_oracle_demo_preserves_methodology_tools_and_graph() -> None:
    demo_source = _DIGITAL_ORACLE_RESEARCHER_DEMO.read_text()
    result = parse_workflow_package_manifest(demo_source)
    compiled = compile_workflow_package_manifest(demo_source)

    assert result.diagnostics == []
    assert compiled["diagnostics"] == []
    assert result.manifest is not None
    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    spec = cast(dict[str, object], dumped["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profile_tool_keys = {str(profile["key"]): profile["toolKeys"] for profile in profiles}
    agents = cast(list[dict[str, object]], spec["agents"])
    agents_by_key = {str(agent["key"]): agent for agent in agents}
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    workflows = cast(list[dict[str, object]], spec["workflows"])
    workflow = workflows[0]
    flow = cast(dict[str, object], workflow["flow"])
    nodes = cast(list[dict[str, object]], flow["nodes"])
    evidence_fanout = nodes[0]
    sec_metadata_collect = nodes[1]
    synthesis = nodes[2]
    evidence_branches = cast(list[dict[str, object]], evidence_fanout["branches"])
    output = cast(dict[str, object], workflow["output"])

    assert profile_tool_keys == {
        "digital_oracle_phase1_tools": [
            "signaldeck.digital_oracle.prediction_markets.lookup",
            "signaldeck.digital_oracle.sec_filings.lookup",
            "signaldeck.digital_oracle.market_sentiment.lookup",
            "signaldeck.digital_oracle.macro_rates.lookup",
            "signaldeck.digital_oracle.crypto_derivatives.lookup",
            "signaldeck.digital_oracle.cftc_positioning.lookup",
            "signaldeck.digital_oracle.options.lookup",
        ]
    }
    assert mcp_servers[0]["key"] == "web_research"
    assert mcp_servers[0]["transport"] == "http-sse"
    assert mcp_servers[0]["url"] == "https://mcp.exa.ai/mcp"
    assert mcp_servers[0]["headers"] == {"Authorization": "Bearer IMPLEMENTATION_TIME_VALUE"}
    assert mcp_servers[0]["query"] == {"api_key": "IMPLEMENTATION_TIME_VALUE"}
    assert mcp_servers[0]["toolKeys"] == ["web_search_exa"]
    signal_researcher = agents_by_key["digital_oracle_signal_researcher"]
    synthesizer = agents_by_key["digital_oracle_synthesizer"]
    assert "Use only the granted Digital Oracle" in str(signal_researcher["systemPrompt"])
    assert "Synthesize only from the supplied signal reports" in str(synthesizer["systemPrompt"])
    assert "Never invent filing facts" in str(signal_researcher["systemPrompt"])
    assert flow["kind"] == "sequence"
    assert flow["id"] == "research_sequence"
    assert [node["kind"] for node in nodes] == ["fanout", "step", "step"]
    assert evidence_fanout["id"] == "evidence_fanout"
    assert [branch["id"] for branch in evidence_branches] == [
        "market_signals",
        "filing_signals",
        "sentiment_search_signals",
        "macro_evidence",
        "web_evidence",
    ]
    assert sec_metadata_collect["id"] == "sec_metadata_collect"
    assert sec_metadata_collect["uses"] == "sec_metadata_collector"
    synthesis_with = cast(dict[str, object], synthesis["with"])
    assert synthesis["id"] == "synthesis"
    assert synthesis["uses"] == "digital_oracle_synthesizer"
    assert synthesis_with["marketSignals"] == "${{ nodes.market_signals.outputs.market_signals }}"
    assert synthesis_with["filingSignals"] == "${{ nodes.filing_signals.outputs.filing_signals }}"
    assert synthesis_with["sentimentSearchSignals"] == (
        "${{ nodes.sentiment_search_signals.outputs.sentiment_search_signals }}"
    )
    assert synthesis_with["macroEvidence"] == (
        "${{ nodes.macro_evidence_collect.outputs.macro_evidence }}"
    )
    assert synthesis_with["webEvidence"] == (
        "${{ nodes.web_evidence_collect.outputs.web_evidence }}"
    )
    assert synthesis_with["secMetadataEvidence"] == (
        "${{ nodes.sec_metadata_collect.outputs.sec_metadata }}"
    )
    assert output["from"] == "${{ nodes.synthesis.outputs.report }}"


def test_parse_rejects_package_schema_additional_properties_keyword() -> None:
    source = _valid_package_manifest_source().replace(
        "  inputs:\n    type: object\n    properties:\n",
        "  inputs:\n    type: object\n    additionalProperties: false\n    properties:\n",
        1,
    )

    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert [diagnostic.model_dump(mode="json") for diagnostic in result.diagnostics] == [
        {
            "severity": "error",
            "message": (
                "additionalProperties is not supported in package schemas; "
                "objects are closed by default"
            ),
            "path": "spec.inputs.additionalProperties",
            "line": 10,
            "column": 27,
        }
    ]


def test_parse_rejects_package_schema_allow_additional_properties_keyword() -> None:
    source = _updated_valid_manifest(
        lambda data: data["spec"]["outputSchemas"][0]["jsonSchema"].__setitem__(
            "allowAdditionalProperties", True
        )
    )

    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert [diagnostic.path for diagnostic in result.diagnostics] == [
        "spec.outputSchemas[0].jsonSchema.allowAdditionalProperties"
    ]
    assert result.diagnostics[0].message == (
        "allowAdditionalProperties is not supported in package schemas; "
        "objects are closed by default"
    )


def test_parse_http_sse_mcp_server_accepts_headers_and_query() -> None:
    result = parse_workflow_package_manifest(_valid_http_sse_package_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    server = result.manifest.spec.mcp_servers[0]
    assert server.transport == "http-sse"
    assert server.url == "https://mcp.example.test/sse"
    assert server.headers == {"Authorization": "Bearer test-token"}
    assert server.query == {"api_key": "test-api-key"}


@pytest.mark.parametrize(
    ("source", "expected_message"),
    [
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["mcpServers"][0].update(
                    {
                        "headers": {"Authorization": "Bearer test-token"},
                        "query": {"api_key": "test-api-key"},
                    }
                )
            ),
            "stdio MCP servers only support inline env values; unsupported fields: headers, query",
        ),
        (
            _updated_http_sse_manifest(
                lambda data: data["spec"]["mcpServers"][0].__setitem__(
                    "env", {"RESEARCH_CONTEXT_TOKEN": "local-token"}
                )
            ),
            "http-sse MCP servers only support inline headers and query values; "
            + "unsupported fields: env",
        ),
    ],
)
def test_parse_rejects_transport_specific_mcp_inline_map_mismatch(
    source: str,
    expected_message: str,
) -> None:
    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert [diagnostic.path for diagnostic in result.diagnostics] == ["spec.mcpServers[0]"]
    assert expected_message in result.diagnostics[0].message
    assert result.diagnostics[0].line is not None
    assert result.diagnostics[0].column is not None


def test_parse_workflow_package_manifest_rejects_malformed_yaml_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: [broken
"""
    )

    assert diagnostic.path == "$"
    assert "Malformed YAML" in diagnostic.message
    assert diagnostic.line is not None
    assert diagnostic.column is not None


def test_parse_package_agent_input_schema_must_be_object() -> None:
    diagnostic = _single_diagnostic(
        _updated_valid_manifest(
            lambda data: data["spec"]["agents"][0].__setitem__("inputSchema", {"type": "string"})
        )
    )

    assert diagnostic.path == "spec.agents[0].inputSchema"
    assert diagnostic.message == "inputSchema must be an object schema"


def test_parse_package_workflow_input_schema_must_be_object() -> None:
    diagnostic = _single_diagnostic(
        _updated_valid_manifest(
            lambda data: data["spec"]["workflows"][0].__setitem__("inputSchema", {"type": "string"})
        )
    )

    assert diagnostic.path == "spec.workflows[0].inputSchema"
    assert diagnostic.message == "inputSchema must be an object schema"


def test_parse_workflow_package_manifest_rejects_compiled_only_fields() -> None:
    diagnostic = _single_diagnostic(
        _updated_valid_manifest(
            lambda data: data["spec"]["workflows"][0].__setitem__(
                "compiledGraph",
                {
                    "apiVersion": "signaldeck.workflowPackage/v1",
                    "rootNodeId": "market_analysis",
                    "nodes": [],
                },
            )
        )
    )

    assert diagnostic.path == "spec.workflows[0].compiledGraph"
    assert diagnostic.message == "Extra inputs are not permitted"


@pytest.mark.parametrize(
    ("source", "expected_path"),
    [
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "step",
                    "id": "research",
                    "slot": "analysis",
                    "uses": "market_agent",
                    "with": {"prior": "${{ nodes.research.outputs.analysis }}"},
                },
                output_reference="${{ nodes.research.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.with.prior",
        ),
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "sequence",
                    "id": "root_sequence",
                    "nodes": [
                        {
                            "kind": "step",
                            "id": "research",
                            "slot": "analysis",
                            "uses": "market_agent",
                            "with": {"prior": "${{ nodes.decision.outputs.final }}"},
                        },
                        {
                            "kind": "step",
                            "id": "decision",
                            "slot": "final",
                            "uses": "decision_agent",
                        },
                    ],
                },
                output_reference="${{ nodes.root_sequence.outputs.final }}",
            ),
            "spec.workflows[0].flow.nodes[0].with.prior",
        ),
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "fanout",
                    "id": "analyst_fanout",
                    "branches": [
                        {
                            "id": "market",
                            "node": {
                                "kind": "step",
                                "id": "market_analysis",
                                "slot": "market_report",
                                "uses": "market_agent",
                                "with": {"ticker": "${{ inputs.ticker }}"},
                            },
                        },
                        {
                            "id": "news",
                            "node": {
                                "kind": "step",
                                "id": "news_analysis",
                                "slot": "news_report",
                                "uses": "news_agent",
                                "with": {
                                    "marketReport": (
                                        "${{ nodes.market_analysis.outputs.market_report }}"
                                    )
                                },
                            },
                        },
                    ],
                },
                output_reference="${{ nodes.analyst_fanout.outputs.news }}",
            ),
            "spec.workflows[0].flow.branches[1].node.with.marketReport",
        ),
    ],
)
def test_parse_package_workflow_graph_rejects_non_earlier_node_refs(
    source: str,
    expected_path: str,
) -> None:
    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == "Node references must point to an earlier node"


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_message"),
    [
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "fanout",
                    "id": "analyst_fanout",
                    "branches": [
                        {
                            "id": "market",
                            "node": {
                                "kind": "step",
                                "id": "market_analysis",
                                "slot": "analysis",
                                "uses": "market_agent",
                            },
                        },
                        {
                            "id": "market",
                            "node": {
                                "kind": "step",
                                "id": "news_analysis",
                                "slot": "news",
                                "uses": "news_agent",
                            },
                        },
                    ],
                },
                output_reference="${{ nodes.analyst_fanout.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.branches[1].id",
            "Duplicate fanout branch id: market",
        ),
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "sequence",
                    "id": "root_sequence",
                    "nodes": [
                        {
                            "kind": "step",
                            "id": "research",
                            "slot": "analysis",
                            "uses": "market_agent",
                        },
                        {
                            "kind": "step",
                            "id": "research",
                            "slot": "final",
                            "uses": "decision_agent",
                        },
                    ],
                },
                output_reference="${{ nodes.root_sequence.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.nodes[1].id",
            "Duplicate node id: research",
        ),
        (
            _graph_package_manifest_source(
                flow={
                    "kind": "sequence",
                    "id": "root_sequence",
                    "nodes": [
                        {
                            "kind": "step",
                            "id": "research",
                            "slot": "analysis",
                            "uses": "market_agent",
                        },
                        {
                            "kind": "step",
                            "id": "decision",
                            "slot": "analysis",
                            "uses": "decision_agent",
                        },
                    ],
                },
                output_reference="${{ nodes.root_sequence.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.nodes[1].slot",
            "Duplicate output slot name within the same sequence",
        ),
    ],
)
def test_parse_package_workflow_graph_preserves_duplicate_diagnostics(
    source: str,
    expected_path: str,
    expected_message: str,
) -> None:
    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == expected_message


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_message", "requires_location"),
    [
        (
            _valid_package_manifest_source().replace("metadata:\n", "metadata: &metadata\n", 1),
            "$",
            "YAML anchors are not supported",
            True,
        ),
        (
            _valid_package_manifest_source()
            .replace("metadata:\n", "metadata: &metadata\n", 1)
            .replace("spec:\n", "extra: *metadata\nspec:\n", 1),
            "$",
            "YAML aliases are not supported",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                (
                    "metadata:\n"
                    "  key: tradingagents_research\n"
                    "  name: TradingAgents Research Package\n"
                ),
                (
                    "metadata:\n"
                    "  <<: {key: tradingagents_research, "
                    "name: TradingAgents Research Package}\n"
                ),
                1,
            ),
            "$",
            "YAML merge keys are not supported",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "apiVersion: signaldeck.workflowPackage/v1\n",
                (
                    "apiVersion: signaldeck.workflowPackage/v1\n"
                    "apiVersion: signaldeck.workflowPackage/v1\n"
                ),
                1,
            ),
            "$",
            "Duplicate mapping key is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "name: TradingAgents Research Package",
                "name: !secret TradingAgents Research Package",
                1,
            ),
            "$",
            "YAML tag '!secret' is not supported",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "description: Portable package for the representative research workflow.",
                "description: .inf",
                1,
            ),
            "metadata.description",
            "YAML numeric values must be finite",
            False,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("unexpectedOption", True)
            ),
            "spec.agents[0].unexpectedOption",
            "Extra inputs are not permitted",
            True,
        ),
        (
            _with_duplicate_output_schema(),
            "spec.outputSchemas[1].key",
            "Duplicate output schema key: trading_decision",
            True,
        ),
        (
            _with_duplicate_agent(),
            "spec.agents[1].key",
            "Duplicate agent key: market_analyst",
            True,
        ),
        (
            _with_duplicate_workflow(),
            "spec.workflows[1].key",
            "Duplicate workflow key: daily_research",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("modelConnectionId", 42)
            ),
            "spec.agents[0].modelConnectionId",
            "modelConnectionId is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("outputSchemaId", 42)
            ),
            "spec.agents[0].outputSchemaId",
            "outputSchemaId is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("capabilityId", 42)
            ),
            "spec.agents[0].capabilityId",
            "capabilityId is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("mcpServerId", 42)
            ),
            "spec.agents[0].mcpServerId",
            "mcpServerId is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__(
                    "apiKey", "sk-raw-manifest-secret"
                )
            ),
            "spec.agents[0].apiKey",
            "apiKey is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__(
                    "secretPayload", {"apiKey": "sk-raw-manifest-secret"}
                )
            ),
            "spec.agents[0].secretPayload",
            "secretPayload is not allowed",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__("password", "raw-password")
            ),
            "spec.agents[0].password",
            "password is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "  capabilityProfiles:\n",
                "  skills:\n    - old_skill@1\n  capabilityProfiles:\n",
                1,
            ),
            "spec.skills",
            "spec.skills is not supported in workflow package manifests",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "  capabilityProfiles:\n",
                "  memory:\n    retrieval:\n      enabled: true\n  capabilityProfiles:\n",
                1,
            ),
            "spec.memory",
            "Extra inputs are not permitted",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["mcpServers"][0].__setitem__(
                    "secretRefs", {"env": ["RESEARCH_CONTEXT_TOKEN"]}
                )
            ),
            "spec.mcpServers[0].secretRefs",
            "Extra inputs are not permitted",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["mcpServers"][0].__setitem__(
                    "requiredBindings", ["env.RESEARCH_CONTEXT_TOKEN"]
                )
            ),
            "spec.mcpServers[0].requiredBindings",
            "Extra inputs are not permitted",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "signaldeck.workflowPackage/v1", "signaldeck.workflow/v2", 1
            ),
            "apiVersion",
            "Workflow manifests are not workflow package manifests",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "signaldeck.workflowPackage/v1", "signaldeck.workflowPackage/v2", 1
            ),
            "apiVersion",
            "Input should be 'signaldeck.workflowPackage/v1'",
            True,
        ),
        (
            _valid_package_manifest_source().replace("kind: WorkflowPackage", "kind: Workflow", 1),
            "kind",
            "Input should be 'WorkflowPackage'",
            True,
        ),
        (
            "- just\n- a list\n",
            "$",
            "Manifest source must be a YAML mapping",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["agents"][0].__setitem__(
                    "outputSchema", "trading_decision@1"
                )
            ),
            "spec.agents[0].outputSchema",
            "package-local key without @version",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["workflows"][0]["flow"].__setitem__(
                    "uses", "market_analyst@1"
                )
            ),
            "spec.workflows[0].flow.uses",
            "package-local key without @version",
            True,
        ),
        (
            _updated_valid_manifest(
                lambda data: data["spec"]["outputSchemas"][0]["jsonSchema"][
                    "properties"
                ].__setitem__("encrypted", {"type": "string"})
            ),
            "spec.outputSchemas[0].jsonSchema.properties.encrypted",
            "encrypted is not allowed",
            True,
        ),
    ],
)
def test_parse_rejects_unsafe_yaml_and_unsupported_global_refs(
    source: str,
    expected_path: str,
    expected_message: str,
    requires_location: bool,
) -> None:
    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    matching_diagnostics = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.path == expected_path and expected_message in diagnostic.message
    ]
    assert matching_diagnostics
    if requires_location:
        assert matching_diagnostics[0].line is not None
        assert matching_diagnostics[0].column is not None


__all__ = ["_valid_package_manifest_source"]
