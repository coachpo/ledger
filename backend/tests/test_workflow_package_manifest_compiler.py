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

_TRADINGAGENTS_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_compile_valid_package_manifest_roundtrips_without_ids() -> None:
    compiled = compile_workflow_package_manifest(_valid_package_manifest_source())
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)

    assert set(compiled) == {
        "packageDefinition",
        "compiledPlan",
        "manifestHash",
        "compiledHash",
        "diagnostics",
    }
    assert compiled["diagnostics"] == []
    assert isinstance(compiled["manifestHash"], str)
    assert len(cast(str, compiled["manifestHash"])) == 64
    assert isinstance(compiled["compiledHash"], str)
    assert len(cast(str, compiled["compiledHash"])) == 64
    assert _canonical_json(compiled) == _canonical_json(recompiled)
    assert roundtrip.source.startswith(
        "apiVersion: ledger.workflowPackage/v1\nkind: WorkflowPackage\n"
    )
    assert "modelConnection: tradingagents_primary_model" in roundtrip.source

    serialized = _canonical_json(compiled)
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
    agents = cast(list[dict[str, object]], spec["agents"])
    workflows = cast(list[dict[str, object]], compiled_plan["workflows"])
    workflow = workflows[0]
    steps = cast(list[dict[str, object]], workflow["steps"])
    graph = cast(dict[str, object], workflow["compiledGraph"])

    assert agents[0]["modelConnection"] == "tradingagents_primary_model"
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


def test_compile_tradingagents_fixture_preserves_report_tool_keys_in_memory_profile() -> None:
    source = _TRADINGAGENTS_FIXTURE.read_text(encoding="utf-8")
    compiled = compile_workflow_package_manifest(source)
    roundtrip = decompile_workflow_package_manifest(compiled)
    recompiled = compile_workflow_package_manifest(roundtrip.source)
    package_definition = cast(dict[str, object], recompiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    assert cast(list[str], profiles_by_key["memory_write_tools"]["toolKeys"]) == [
        "ledger.reports.lookup",
        "ledger.reports.write",
    ]
    assert "ledger.reports.lookup" in roundtrip.source
    assert "ledger.reports.write" in roundtrip.source
    assert "ledger.memory." not in roundtrip.source


def test_compile_package_manifest_rejects_duplicate_report_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - ledger.market_data.quote_lookup\n",
        "        - ledger.reports.lookup\n        - ledger.reports.lookup\n",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[1]"
        and "Duplicate tool key 'ledger.reports.lookup' is not allowed" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_compile_package_manifest_rejects_phase_one_memory_tool_keys() -> None:
    source = _valid_package_manifest_source().replace(
        "        - ledger.market_data.quote_lookup\n",
        "        - ledger.memory.lookup\n",
        1,
    )

    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
        and "Unknown server-declared tool 'ledger.memory.lookup'" in diagnostic.message
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
