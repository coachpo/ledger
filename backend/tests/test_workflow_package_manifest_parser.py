from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest

_DIGITAL_ORACLE_RESEARCHER_DEMO = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)


def _valid_package_manifest_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: tradingagents_research
  name: TradingAgents Research Package
  description: Portable package for the representative research workflow.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles:
    - key: market_research_tools
      name: Market Research Tools
      description: Uses server-declared market data tools.
      toolKeys:
        - signaldeck.finance.market_data.quote_lookup
  outputSchemas:
    - key: trading_decision
      name: Trading Decision
      description: Final research-only portfolio decision.
      jsonSchema:
        type: object
        properties:
          action:
            type: string
          rationale:
            type: string
        required: [action, rationale]
  mcpServers:
    - key: research_context
      name: Research Context
      description: Local context server declaration.
      transport: stdio
      command: python
      args: [server.py]
      env:
        RESEARCH_CONTEXT_TOKEN: local-token
      toolKeys:
        - research_context.search
  agents:
    - key: market_analyst
      name: Market Analyst
      description: Produces market research.
      modelConnection: tradingagents_primary_model
      systemPrompt: |
        Use provided tools and return structured output.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      outputSchema: trading_decision
      capabilityProfiles: [market_research_tools]
      mcpServers: [research_context]
  workflows:
    - key: daily_research
      name: Daily Research
      description: Runs the market analyst.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
        kind: step
        id: market_analysis
        slot: decision
        uses: market_analyst
        with:
          ticker: ${{ inputs.ticker }}
      output:
        from: ${{ nodes.market_analysis.outputs.decision }}
"""


def _valid_http_sse_package_manifest_source() -> str:
    return _valid_package_manifest_source().replace(
        """      transport: stdio
      command: python
      args: [server.py]
      env:
        RESEARCH_CONTEXT_TOKEN: local-token
""",
        """      transport: http-sse
      url: https://mcp.example.test/sse
      headers:
        Authorization: Bearer test-token
      query:
        api_key: test-api-key
""",
        1,
    )


def _with_duplicate_output_schema() -> str:
    duplicate_schema = """    - key: trading_decision
      name: Trading Decision Duplicate
      jsonSchema:
        type: object
  mcpServers:
"""
    return _valid_package_manifest_source().replace("  mcpServers:\n", duplicate_schema, 1)


def _with_duplicate_agent() -> str:
    duplicate_agent = """    - key: market_analyst
      name: Market Analyst Duplicate
      modelConnection: tradingagents_primary_model
      systemPrompt: Test
      inputSchema:
        type: object
      outputSchema: trading_decision
  workflows:
"""
    return _valid_package_manifest_source().replace("  workflows:\n", duplicate_agent, 1)


def _with_duplicate_workflow() -> str:
    duplicate_workflow = """    - key: daily_research
      name: Duplicate Daily Research
      inputSchema:
        type: object
      flow:
        kind: step
        id: duplicate_research
        slot: duplicate_decision
        uses: market_analyst
      output:
        from: ${{ nodes.duplicate_research.outputs.duplicate_decision }}
    - key: daily_research
"""
    return _valid_package_manifest_source().replace(
        "    - key: daily_research\n", duplicate_workflow, 1
    )


def _single_diagnostic(source: str):
    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    return diagnostic


def _graph_package_manifest_source(*, flow: str, output_reference: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
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
  outputSchemas:
    - key: graph_note
      name: Graph Note
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
  agents:
    - key: market_agent
      name: Market Agent
      modelConnection: graph_model
      systemPrompt: Return market output.
      inputSchema:
        type: object
      outputSchema: graph_note
    - key: news_agent
      name: News Agent
      modelConnection: graph_model
      systemPrompt: Return news output.
      inputSchema:
        type: object
      outputSchema: graph_note
    - key: decision_agent
      name: Decision Agent
      modelConnection: graph_model
      systemPrompt: Return final output.
      inputSchema:
        type: object
      outputSchema: graph_note
  workflows:
    - key: advisory_research
      name: Advisory Research
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
{flow}
      output:
        from: {output_reference}
"""


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
    assert agents[0]["modelConnection"] == "tradingagents_primary_model"
    removed_budget_field = "budget" + "Usd"
    assert removed_budget_field not in agents[0]
    assert "modelConnectionId" not in agents[0]
    assert capability_profiles[0]["toolKeys"] == ["signaldeck.finance.market_data.quote_lookup"]
    assert "tool_keys" not in capability_profiles[0]
    assert mcp_servers[0]["env"] == {"RESEARCH_CONTEXT_TOKEN": "local-token"}
    assert "secretRefs" not in mcp_servers[0]
    assert "requiredBindings" not in mcp_servers[0]


def test_parse_digital_oracle_demo_preserves_methodology_tools_graph_and_private_exa() -> None:
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
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    agents = cast(list[dict[str, object]], spec["agents"])
    workflows = cast(list[dict[str, object]], spec["workflows"])
    workflow = workflows[0]
    flow = cast(dict[str, object], workflow["flow"])
    nodes = cast(list[dict[str, object]], flow["nodes"])
    fanout = nodes[0]
    synthesis = nodes[1]
    branches = cast(list[dict[str, object]], fanout["branches"])
    output = cast(dict[str, object], workflow["output"])

    assert profile_tool_keys == {
        "digital_oracle_phase1_tools": [
            "signaldeck.digital_oracle.prediction_markets.lookup",
            "signaldeck.digital_oracle.sec_filings.lookup",
            "signaldeck.digital_oracle.market_sentiment.lookup",
        ],
        "finance_price_history_tools": [
            "signaldeck.finance.market_data.history_lookup",
            "signaldeck.finance.market_data.ohlcv_lookup",
        ],
    }
    assert mcp_servers[0]["key"] == "exa"
    assert mcp_servers[0]["transport"] == "http-sse"
    assert mcp_servers[0]["url"] == "https://mcp.exa.ai/mcp?tools=web_search_exa"
    assert mcp_servers[0]["toolKeys"] == ["web_search_exa"]
    assert mcp_servers[0]["headers"] == {}
    assert mcp_servers[0]["query"] == {}
    assert "market-data-only reasoning" in str(agents[0]["systemPrompt"])
    assert "price-to-judgment reasoning" in str(agents[1]["systemPrompt"])
    assert "Never invent prices" in str(agents[0]["systemPrompt"])
    assert flow["kind"] == "sequence"
    assert flow["id"] == "research_sequence"
    assert [node["kind"] for node in nodes] == ["fanout", "step"]
    assert fanout["id"] == "signal_fanout"
    assert [branch["id"] for branch in branches] == [
        "market_signals",
        "filing_signals",
        "sentiment_search_signals",
    ]
    assert synthesis == {
        "kind": "step",
        "id": "synthesis",
        "slot": "report",
        "uses": "digital_oracle_synthesizer",
        "with": {
            "researchQuestion": "${{ inputs.researchQuestion }}",
            "outputLanguage": "${{ inputs.outputLanguage }}",
            "marketSignals": "${{ nodes.signal_fanout.outputs.market_signals }}",
            "filingSignals": "${{ nodes.signal_fanout.outputs.filing_signals }}",
            "sentimentSearchSignals": "${{ nodes.signal_fanout.outputs.sentiment_search_signals }}",
            "asOfDate": "${{ inputs.asOfDate }}",
            "horizonDays": "${{ inputs.horizonDays }}",
        },
        "memory": None,
        "optional": False,
    }
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
    source = _valid_package_manifest_source().replace(
        "        properties:\n          action:\n",
        "        allowAdditionalProperties: true\n        properties:\n          action:\n",
        1,
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
            _valid_package_manifest_source().replace(
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n      toolKeys:\n",
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n"
                + "      headers:\n        Authorization: Bearer test-token\n"
                + "      query:\n        api_key: test-api-key\n"
                + "      toolKeys:\n",
                1,
            ),
            "stdio MCP servers only support inline env values; unsupported fields: headers, query",
        ),
        (
            _valid_http_sse_package_manifest_source().replace(
                "      headers:\n",
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n      headers:\n",
                1,
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
        _valid_package_manifest_source().replace(
            """      inputSchema:
        type: object
        properties:
          ticker:
            type: string
""",
            """      inputSchema:
        type: string
""",
            1,
        )
    )

    assert diagnostic.path == "spec.agents[0].inputSchema"
    assert diagnostic.message == "inputSchema must be an object schema"


def test_parse_package_workflow_input_schema_must_be_object() -> None:
    diagnostic = _single_diagnostic(
        _valid_package_manifest_source().replace(
            """      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
""",
            """      inputSchema:
        type: string
      flow:
""",
            1,
        )
    )

    assert diagnostic.path == "spec.workflows[0].inputSchema"
    assert diagnostic.message == "inputSchema must be an object schema"


def test_parse_workflow_package_manifest_rejects_compiled_only_fields() -> None:
    diagnostic = _single_diagnostic(
        _valid_package_manifest_source().replace(
            """      output:
        from: ${{ nodes.market_analysis.outputs.decision }}
""",
            """      compiledGraph:
        apiVersion: signaldeck.workflowPackage/v1
        rootNodeId: market_analysis
        nodes: []
      output:
        from: ${{ nodes.market_analysis.outputs.decision }}
""",
            1,
        )
    )

    assert diagnostic.path == "spec.workflows[0].compiledGraph"
    assert diagnostic.message == "Extra inputs are not permitted"


@pytest.mark.parametrize(
    ("source", "expected_path"),
    [
        (
            _graph_package_manifest_source(
                flow="""        kind: step
        id: research
        slot: analysis
        uses: market_agent
        with:
          prior: ${{ nodes.research.outputs.analysis }}""",
                output_reference="${{ nodes.research.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.with.prior",
        ),
        (
            _graph_package_manifest_source(
                flow="""        kind: sequence
        id: root_sequence
        nodes:
          - kind: step
            id: research
            slot: analysis
            uses: market_agent
            with:
              prior: ${{ nodes.decision.outputs.final }}
          - kind: step
            id: decision
            slot: final
            uses: decision_agent""",
                output_reference="${{ nodes.root_sequence.outputs.final }}",
            ),
            "spec.workflows[0].flow.nodes[0].with.prior",
        ),
        (
            _graph_package_manifest_source(
                flow="""        kind: fanout
        id: analyst_fanout
        branches:
          - id: market
            node:
              kind: step
              id: market_analysis
              slot: market_report
              uses: market_agent
              with:
                ticker: ${{ inputs.ticker }}
          - id: news
            node:
              kind: step
              id: news_analysis
              slot: news_report
              uses: news_agent
              with:
                marketReport: ${{ nodes.market_analysis.outputs.market_report }}""",
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
                flow="""        kind: fanout
        id: analyst_fanout
        branches:
          - id: market
            node:
              kind: step
              id: market_analysis
              slot: analysis
              uses: market_agent
          - id: market
            node:
              kind: step
              id: news_analysis
              slot: news
              uses: news_agent""",
                output_reference="${{ nodes.analyst_fanout.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.branches[1].id",
            "Duplicate fanout branch id: market",
        ),
        (
            _graph_package_manifest_source(
                flow="""        kind: sequence
        id: root_sequence
        nodes:
          - kind: step
            id: research
            slot: analysis
            uses: market_agent
          - kind: step
            id: research
            slot: final
            uses: decision_agent""",
                output_reference="${{ nodes.root_sequence.outputs.analysis }}",
            ),
            "spec.workflows[0].flow.nodes[1].id",
            "Duplicate node id: research",
        ),
        (
            _graph_package_manifest_source(
                flow="""        kind: sequence
        id: root_sequence
        nodes:
          - kind: step
            id: research
            slot: analysis
            uses: market_agent
          - kind: step
            id: decision
            slot: analysis
            uses: decision_agent""",
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
            _valid_package_manifest_source().replace(
                "      mcpServers: [research_context]\n",
                "      mcpServers: [research_context]\n      " + "budget" + 'Usd: "0.25"\n',
                1,
            ),
            "spec.agents[0]." + "budget" + "Usd",
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
            _valid_package_manifest_source().replace(
                "modelConnection: tradingagents_primary_model",
                "modelConnectionId: 42",
                1,
            ),
            "spec.agents[0].modelConnectionId",
            "modelConnectionId is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "outputSchema: trading_decision",
                "outputSchemaId: 42",
                1,
            ),
            "spec.agents[0].outputSchemaId",
            "outputSchemaId is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "      capabilityProfiles: [market_research_tools]",
                "      capabilityId: 42",
                1,
            ),
            "spec.agents[0].capabilityId",
            "capabilityId is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "      mcpServers: [research_context]",
                "      mcpServerId: 42",
                1,
            ),
            "spec.agents[0].mcpServerId",
            "mcpServerId is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "modelConnection: tradingagents_primary_model",
                "apiKey: sk-raw-manifest-secret",
                1,
            ),
            "spec.agents[0].apiKey",
            "apiKey is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "modelConnection: tradingagents_primary_model",
                "secretPayload: {apiKey: sk-raw-manifest-secret}",
                1,
            ),
            "spec.agents[0].secretPayload",
            "secretPayload is not allowed",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "modelConnection: tradingagents_primary_model",
                "password: raw-password",
                1,
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
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n      toolKeys:\n",
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n"
                + "      secretRefs:\n        env: [RESEARCH_CONTEXT_TOKEN]\n"
                + "      toolKeys:\n",
                1,
            ),
            "spec.mcpServers[0].secretRefs",
            "Extra inputs are not permitted",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n      toolKeys:\n",
                "      env:\n        RESEARCH_CONTEXT_TOKEN: local-token\n"
                + "      requiredBindings:\n        - env.RESEARCH_CONTEXT_TOKEN\n"
                + "      toolKeys:\n",
                1,
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
            _valid_package_manifest_source().replace(
                "outputSchema: trading_decision",
                "outputSchema: trading_decision@1",
                1,
            ),
            "spec.agents[0].outputSchema",
            "package-local key without @version",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "uses: market_analyst", "uses: market_analyst@1", 1
            ),
            "spec.workflows[0].flow.uses",
            "package-local key without @version",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "          action:\n            type: string",
                "          encrypted:\n            type: string",
                1,
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
