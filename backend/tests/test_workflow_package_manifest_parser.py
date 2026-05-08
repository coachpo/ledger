from __future__ import annotations

from typing import cast

import pytest

from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest


def _valid_package_manifest_source() -> str:
    return """apiVersion: ledger.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: tradingagents_research
  name: TradingAgents Research Package
  description: Portable package for the representative research workflow.
spec:
  inputs:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles:
    - key: market_research_tools
      name: Market Research Tools
      description: Uses server-declared market data tools.
      toolKeys:
        - ledger.market_data.quote_lookup
  outputSchemas:
    - key: trading_decision
      name: Trading Decision
      description: Final research-only portfolio decision.
      jsonSchema:
        type: object
        additionalProperties: false
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
      budgetUsd: "0.25"
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


def test_parse_valid_workflow_package_manifest_returns_typed_manifest() -> None:
    result = parse_workflow_package_manifest(_valid_package_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.api_version == "ledger.workflowPackage/v1"
    assert result.manifest.kind == "WorkflowPackage"
    assert result.manifest.metadata.key == "tradingagents_research"
    assert result.manifest.spec.agents[0].model_connection == "tradingagents_primary_model"
    assert result.manifest.spec.agents[0].output_schema == "trading_decision"
    assert result.manifest.spec.workflows[0].flow.id == "market_analysis"

    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    spec = cast(dict[str, object], dumped["spec"])
    agents = cast(list[dict[str, object]], spec["agents"])
    capability_profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    assert agents[0]["modelConnection"] == "tradingagents_primary_model"
    assert "modelConnectionId" not in agents[0]
    assert capability_profiles[0]["toolKeys"] == ["ledger.market_data.quote_lookup"]
    assert "tool_keys" not in capability_profiles[0]


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
                "apiVersion: ledger.workflowPackage/v1\n",
                "apiVersion: ledger.workflowPackage/v1\napiVersion: ledger.workflowPackage/v1\n",
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
            _valid_package_manifest_source().replace('budgetUsd: "0.25"', "budgetUsd: .inf", 1),
            "spec.agents[0].budgetUsd",
            "YAML numeric values must be finite",
            False,
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
                "  capabilityProfiles:\n",
                "  skills:\n    - old_skill@1\n  capabilityProfiles:\n",
                1,
            ),
            "spec.skills",
            "spec.skills is no longer supported",
            True,
        ),
        (
            _valid_package_manifest_source().replace(
                "ledger.workflowPackage/v1", "ledger.workflow/v2", 1
            ),
            "apiVersion",
            "Workflow roots are not package manifests",
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
def test_parse_rejects_unsafe_yaml_and_legacy_global_refs(
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
