# pyright: reportPrivateUsage=false, reportUnnecessaryCast=false

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from app.services.workflow_package_manifest_compiler import (
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
)
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source

_DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo"
_EXPECTED_DEMO_HASHES = {
    "digital_oracle_researcher": (
        "9cdde0eaf311164747948b386c9901cd3a70c0ef981c8296e616c52e212ac0c4",
        "1a997fe3f393bdef1db33473c7241683ecbba6e5f266b3bc1b1960c4e5ba5ea4",
    ),
    "tradingagents_advisory_research_macro": (
        "09c79f75209be49c4745b548129df309c039d84894e3dc80e27d21eeae6812de",
        "43cf2f6e2890e15ab1d943636d08471d9013aa1c8435cacea496da930ff50865",
    ),
    "tradingagents_advisory_research_mixed_signals": (
        "6b5e54a5bd3fc62d99aa6bec8d0be839f548d232e3e610535da3bc0d083ba92f",
        "59010485fc6eac23f94bb75777ae3fb3b920b5879738007f0dfd7ad58daa16fd",
    ),
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _demo_source(package_key: str) -> str:
    return (_DEMO_ROOT / f"{package_key}.yaml").read_text(encoding="utf-8")


def _compiled_tool_keys(compiled: dict[str, object]) -> set[str]:
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    return {tool_key for profile in profiles for tool_key in cast(list[str], profile["toolKeys"])}


def _items_by_key(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["key"]): item for item in items}


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
      name: Report Context Tools
      description: Reads persisted SignalDeck reports and quotes for research context.
      toolKeys:
        - signaldeck.finance.reports.lookup
        - signaldeck.finance.market_data.quote_lookup
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


def test_compile_valid_package_manifest_roundtrips_current_contract() -> None:
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

    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    spec = cast(dict[str, object], package_definition["spec"])
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    agents = cast(list[dict[str, object]], spec["agents"])
    workflows = cast(list[dict[str, object]], compiled_plan["workflows"])
    workflow = workflows[0]
    steps = cast(list[dict[str, object]], workflow["steps"])
    graph = cast(dict[str, object], workflow["compiledGraph"])

    assert set(package_definition) == {"apiVersion", "kind", "metadata", "spec"}
    assert set(spec) == {
        "inputs",
        "capabilityProfiles",
        "outputSchemas",
        "mcpServers",
        "agents",
        "workflows",
    }
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
    assert mcp_servers[0] == {
        "key": "research_context",
        "name": "Research Context",
        "description": "Local context server declaration.",
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "env": {"RESEARCH_CONTEXT_TOKEN": "local-token"},
        "toolKeys": ["research_context.search"],
    }
    assert "RESEARCH_CONTEXT_TOKEN: local-token" in roundtrip.source
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
                    "memoryPolicy": {
                        "enabled": False,
                        "retrieval": None,
                        "writes": None,
                        "policy": None,
                        "checkpoints": None,
                    },
                }
            ],
        }
    ]
    assert workflow["outputSpec"] == {"kind": "slot", "stepIndex": 1, "slot": "decision"}
    assert graph["rootNodeId"] == "market_analysis"


def test_compile_inline_private_mcp_preserves_report_and_quote_tool_keys() -> None:
    compiled = compile_workflow_package_manifest(_inline_private_mcp_manifest_source())
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)
    package_definition = cast(dict[str, object], recompiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}
    mcp_server = cast(list[dict[str, object]], spec["mcpServers"])[0]

    assert cast(list[str], profiles_by_key["report_context_tools"]["toolKeys"]) == [
        "signaldeck.finance.reports.lookup",
        "signaldeck.finance.market_data.quote_lookup",
    ]
    assert mcp_server == {
        "key": "exa",
        "name": "Exa Web Search",
        "description": "Remote Exa MCP server for advisory information search.",
        "transport": "http-sse",
        "url": "https://mcp.exa.ai/mcp",
        "headers": {"Authorization": "Bearer test-token"},
        "query": {"api_key": "test-api-key"},
        "toolKeys": ["web_search_exa"],
    }
    assert "Authorization: Bearer test-token" in roundtrip.source
    assert "api_key: test-api-key" in roundtrip.source
    assert "signaldeck.finance.reports.lookup" in roundtrip.source
    assert "signaldeck.finance.market_data.quote_lookup" in roundtrip.source
    assert _canonical_json(compiled) == _canonical_json(recompiled)


@pytest.mark.parametrize(
    ("package_key", "expected_tool_keys", "expected_http_ids"),
    [
        (
            "digital_oracle_researcher",
            {
                "signaldeck.digital_oracle.cftc_positioning.lookup",
                "signaldeck.digital_oracle.crypto_derivatives.lookup",
                "signaldeck.digital_oracle.macro_rates.lookup",
                "signaldeck.digital_oracle.prediction_markets.lookup",
                "signaldeck.digital_oracle.sec_filings.lookup",
                "signaldeck.digital_oracle.market_sentiment.lookup",
                "signaldeck.digital_oracle.options.lookup",
            },
            set(),
        ),
        (
            "tradingagents_advisory_research_macro",
            {
                "signaldeck.finance.fundamentals.lookup",
                "signaldeck.finance.indicators.lookup",
                "signaldeck.finance.insider_data.lookup",
                "signaldeck.finance.market_data.history_lookup",
                "signaldeck.finance.market_data.ohlcv_lookup",
                "signaldeck.finance.market_data.quote_lookup",
                "signaldeck.finance.news.lookup",
                "signaldeck.finance.positions.lookup",
                "signaldeck.finance.reports.lookup",
                "signaldeck.finance.social_sentiment.lookup",
            },
            {
                "fred_fedfunds_observations",
                "fred_unrate_observations",
                "fred_cpiaucsl_observations",
                "fred_t10y2y_observations",
                "treasury_rates_snapshot_json",
            },
        ),
        (
            "tradingagents_advisory_research_mixed_signals",
            {
                "signaldeck.digital_oracle.macro_rates.lookup",
                "signaldeck.digital_oracle.prediction_markets.lookup",
                "signaldeck.finance.fundamentals.lookup",
                "signaldeck.finance.indicators.lookup",
                "signaldeck.finance.insider_data.lookup",
                "signaldeck.finance.market_data.history_lookup",
                "signaldeck.finance.market_data.ohlcv_lookup",
                "signaldeck.finance.market_data.quote_lookup",
                "signaldeck.finance.news.lookup",
                "signaldeck.finance.positions.lookup",
                "signaldeck.finance.reports.lookup",
                "signaldeck.finance.social_sentiment.lookup",
            },
            set(),
        ),
    ],
)
def test_compile_demo_presets_lock_hashes_tools_and_private_operations(
    package_key: str,
    expected_tool_keys: set[str],
    expected_http_ids: set[str],
) -> None:
    compiled = compile_workflow_package_manifest(_demo_source(package_key))
    expected_manifest_hash, expected_compiled_hash = _EXPECTED_DEMO_HASHES[package_key]
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    spec = cast(dict[str, object], package_definition["spec"])
    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    operation_ids = {
        str(operation["operationKey"])
        for workflow in cast(list[dict[str, object]], compiled_plan["workflows"])
        for step in cast(list[dict[str, object]], workflow["steps"])
        for operation in cast(list[dict[str, object]], step.get("operations", []))
    }

    assert compiled["manifestHash"] == expected_manifest_hash
    assert compiled["compiledHash"] == expected_compiled_hash
    assert compiled["diagnostics"] == []
    assert _compiled_tool_keys(compiled) == expected_tool_keys
    assert expected_http_ids <= operation_ids
    assert all(
        operation_id.startswith(("fred_", "treasury_", "sec_")) for operation_id in operation_ids
    )
    if package_key == "digital_oracle_researcher":
        extension_dependencies = cast(list[dict[str, object]], compiled["extensionDependencies"])
        assert {dependency["extensionKey"] for dependency in extension_dependencies} == {
            "signaldeck.digital_oracle",
            "signaldeck.finance",
        }
    else:
        assert mcp_servers and mcp_servers[0]["key"] == "web_research"
        assert mcp_servers[0]["toolKeys"] == ["web_search_exa"]
    if package_key == "tradingagents_advisory_research_macro":
        assert not any(
            tool_key.startswith("signaldeck.digital_oracle.") for tool_key in expected_tool_keys
        )
    if package_key == "tradingagents_advisory_research_mixed_signals":
        assert (
            not {
                "signaldeck.digital_oracle.sec_filings.lookup",
                "signaldeck.digital_oracle.market_sentiment.lookup",
            }
            & expected_tool_keys
        )


def test_compile_macro_demo_collector_accepts_raw_http_payload_shapes() -> None:
    compiled = compile_workflow_package_manifest(
        _demo_source("tradingagents_advisory_research_macro")
    )
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    spec = cast(dict[str, object], package_definition["spec"])
    output_schemas = _items_by_key(cast(list[dict[str, object]], spec["outputSchemas"]))
    agents = _items_by_key(cast(list[dict[str, object]], spec["agents"]))
    macro_collector = agents["macro_context_collector"]
    input_schema = cast(dict[str, object], macro_collector["inputSchema"])
    input_properties = cast(dict[str, object], input_schema["properties"])
    fred_schema = cast(dict[str, object], output_schemas["fred_observations_raw"])["jsonSchema"]
    treasury_schema = cast(dict[str, object], output_schemas["treasury_rates_raw"])["jsonSchema"]

    for property_name in (
        "fredFedfundsObservations",
        "fredUnrateObservations",
        "fredCpiaucslObservations",
        "fredT10y2yObservations",
    ):
        assert input_properties[property_name] == fred_schema
    assert input_properties["treasuryRatesSnapshot"] == treasury_schema

    advisory_workflow = next(
        workflow
        for workflow in cast(list[dict[str, object]], compiled_plan["workflows"])
        if workflow["key"] == "advisory_research"
    )
    treasury_operation = next(
        operation
        for step in cast(list[dict[str, object]], advisory_workflow["steps"])
        for operation in cast(list[dict[str, object]], step.get("operations", []))
        if operation["operationKey"] == "treasury_rates_snapshot_json"
    )
    request = cast(dict[str, object], treasury_operation["request"])
    assert request["url"] == (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
        "v2/accounting/od/avg_interest_rates"
    )


def test_compile_package_manifest_rejects_duplicate_report_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - signaldeck.finance.market_data.quote_lookup\n",
        (
            "        - signaldeck.finance.reports.lookup\n"
            "        - signaldeck.finance.reports.lookup\n"
        ),
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[1]"
        and "Duplicate tool key 'signaldeck.finance.reports.lookup' is not allowed"
        in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_rejects_unknown_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - signaldeck.finance.market_data.quote_lookup\n",
        "        - signaldeck.unknown.lookup\n",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
        and "Unknown server-declared tool 'signaldeck.unknown.lookup'" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
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
