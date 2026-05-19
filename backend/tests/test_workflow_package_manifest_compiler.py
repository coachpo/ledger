# pyright: reportPrivateUsage=false, reportUnnecessaryCast=false

from __future__ import annotations

import json
from typing import cast

import pytest

from app.services.workflow_package_manifest_compiler import (
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
)
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _inline_private_mcp_manifest_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: tradingagents_inline_private_mcp
  name: Inline Private MCP Research
  description: Round-trip manifest that keeps inline private MCP values.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles:
    - key: report_context_tools
      name: Report Context and Memory Tools
      description: Reads persisted SignalDeck reports and core memory for research context.
      toolKeys:
        - signaldeck.reports.lookup
        - signaldeck.memory.lookup
        - signaldeck.memory.write
  outputSchemas:
    - key: decision
      name: Decision
      description: Structured decision.
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  mcpServers:
    - key: exa
      name: Exa Web Search
      description: Remote Exa MCP server for advisory information search.
      transport: http-sse
      url: https://mcp.exa.ai/mcp
      headers:
        Authorization: Bearer test-token
      query:
        api_key: test-api-key
      toolKeys:
        - web_search_exa
  agents:
    - key: researcher
      name: Researcher
      description: Produces market research.
      modelConnection: tradingagents_primary_model
      systemPrompt: |
        Use provided tools and return structured output.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      outputSchema: decision
      capabilityProfiles: [report_context_tools]
      mcpServers: [exa]
  workflows:
    - key: inline_private_mcp_roundtrip
      name: Inline Private MCP Roundtrip
      description: Runs the researcher.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
        kind: step
        id: research_step
        slot: summary
        uses: researcher
        with:
          ticker: ${{ inputs.ticker }}
      output:
        from: ${{ nodes.research_step.outputs.summary }}
"""


def test_compile_valid_package_manifest_roundtrips_without_ids() -> None:
    compiled = compile_workflow_package_manifest(_valid_package_manifest_source())
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)

    assert set(compiled) == {
        "packageDefinition",
        "compiledPlan",
        "manifestHash",
        "compiledHash",
        "extensionDependencies",
        "diagnostics",
    }
    assert compiled["diagnostics"] == []
    assert isinstance(compiled["manifestHash"], str)
    assert len(cast(str, compiled["manifestHash"])) == 64
    assert isinstance(compiled["compiledHash"], str)
    assert len(cast(str, compiled["compiledHash"])) == 64
    assert _canonical_json(compiled) == _canonical_json(recompiled)
    assert roundtrip.source.startswith(
        "apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n"
    )
    assert "modelConnection: tradingagents_primary_model" in roundtrip.source
    removed_budget_field = "budget" + "Usd"
    assert removed_budget_field not in roundtrip.source

    serialized = _canonical_json(compiled)
    assert removed_budget_field not in serialized
    assert "modelConnectionId" not in serialized
    assert "outputSchemaId" not in serialized
    assert "capabilityId" not in serialized
    assert "mcpServerId" not in serialized
    assert "apiKey" not in serialized
    assert "secret" not in serialized.lower()
    assert "encrypted" not in serialized

    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    spec = cast(dict[str, object], package_definition["spec"])
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    agents = cast(list[dict[str, object]], spec["agents"])
    workflows = cast(list[dict[str, object]], compiled_plan["workflows"])
    workflow = workflows[0]
    steps = cast(list[dict[str, object]], workflow["steps"])
    graph = cast(dict[str, object], workflow["compiledGraph"])

    assert agents[0]["modelConnection"] == "tradingagents_primary_model"
    assert mcp_servers[0]["env"] == {"RESEARCH_CONTEXT_TOKEN": "local-token"}
    assert "RESEARCH_CONTEXT_TOKEN: local-token" in roundtrip.source
    assert "secretRefs" not in roundtrip.source
    assert "requiredBindings" not in roundtrip.source
    compiled_agents = cast(list[dict[str, object]], compiled_plan["agents"])
    assert compiled_agents[0]["capabilityProfiles"] == ["market_research_tools"]
    assert compiled_agents[0]["mcpServers"] == ["research_context"]
    assert compiled_plan["packageKey"] == "tradingagents_research"
    assert steps == [
        {
            "index": 1,
            "agents": [
                {
                    "agentKey": "market_analyst",
                    "slot": "decision",
                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                    "optional": False,
                }
            ],
        }
    ]
    assert workflow["outputSpec"] == {"kind": "slot", "stepIndex": 1, "slot": "decision"}
    assert graph["rootNodeId"] == "market_analysis"


def test_compile_inline_private_mcp_preserves_report_lookup_memory_keys() -> None:
    compiled = compile_workflow_package_manifest(_inline_private_mcp_manifest_source())
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)
    package_definition = cast(dict[str, object], recompiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}
    mcp_server = cast(list[dict[str, object]], spec["mcpServers"])[0]

    assert cast(list[str], profiles_by_key["report_context_tools"]["toolKeys"]) == [
        "signaldeck.reports.lookup",
        "signaldeck.memory.lookup",
        "signaldeck.memory.write",
    ]
    assert mcp_server["headers"] == {"Authorization": "Bearer test-token"}
    assert mcp_server["query"] == {"api_key": "test-api-key"}
    assert "Authorization: Bearer test-token" in roundtrip.source
    assert "api_key: test-api-key" in roundtrip.source
    assert "secretRefs" not in roundtrip.source
    assert "requiredBindings" not in roundtrip.source
    assert "signaldeck.reports.lookup" in roundtrip.source
    assert "signaldeck.memory.lookup" in roundtrip.source
    assert "signaldeck.memory.write" in roundtrip.source
    assert "signaldeck.reports.write" not in roundtrip.source
    assert _canonical_json(compiled) == _canonical_json(recompiled)


def test_compile_package_manifest_rejects_duplicate_report_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - signaldeck.market_data.quote_lookup\n",
        "        - signaldeck.reports.lookup\n        - signaldeck.reports.lookup\n",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[1]"
        and "Duplicate tool key 'signaldeck.reports.lookup' is not allowed" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_accepts_core_memory_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - signaldeck.market_data.quote_lookup\n",
        "        - signaldeck.memory.lookup\n",
        1,
    )

    compiled = compile_workflow_package_manifest(source)
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    assert cast(list[str], profiles_by_key["market_research_tools"]["toolKeys"])[0] == (
        "signaldeck.memory.lookup"
    )


def test_compile_package_manifest_rejects_unresolved_local_refs() -> None:
    source = _valid_package_manifest_source().replace(
        "outputSchema: trading_decision", "outputSchema: missing_schema", 1
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.agents[0].outputSchema"
        and "Package output schema 'missing_schema' was not found" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_rejects_unresolved_workflow_agent_refs() -> None:
    source = _valid_package_manifest_source().replace(
        "uses: market_analyst", "uses: missing_agent", 1
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.workflows[0].flow.uses"
        and "Package agent 'missing_agent' was not found" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_rejects_unresolved_capability_profile_refs() -> None:
    source = _valid_package_manifest_source().replace(
        "capabilityProfiles: [market_research_tools]",
        "capabilityProfiles: [missing_profile]",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.agents[0].capabilityProfiles[0]"
        and "Package capability profile 'missing_profile' was not found" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_rejects_unresolved_mcp_server_refs() -> None:
    source = _valid_package_manifest_source().replace(
        "mcpServers: [research_context]",
        "mcpServers: [missing_context]",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.agents[0].mcpServers[0]"
        and "Package MCP server 'missing_context' was not found" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )
