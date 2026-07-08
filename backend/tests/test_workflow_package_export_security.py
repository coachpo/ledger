# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.services.workflow_package_export import (
    build_workflow_package_manifest_hydration_payload,
    export_workflow_package_yaml,
)
from tests.test_workflow_package_manifest_parser import (
    _valid_http_sse_package_manifest_source,
    _valid_package_manifest_source,
)


def test_manifest_hydration_keeps_stored_source_and_safe_package_definition() -> None:
    manifest_source = _valid_http_sse_package_manifest_source()
    hydrated = build_workflow_package_manifest_hydration_payload(
        {"manifestSource": manifest_source}
    )
    safe_definition = deepcopy(cast(dict[str, Any], hydrated["packageDefinition"]))
    safe_spec = cast(dict[str, Any], safe_definition["spec"])
    safe_agents = cast(list[dict[str, Any]], safe_spec["agents"])
    safe_mcp_server = cast(list[dict[str, Any]], safe_spec["mcpServers"])[0]

    hydrated_source = cast(str, hydrated["manifestSource"])
    assert hydrated_source.startswith("apiVersion: signaldeck.workflowPackage/v1")
    assert "modelConnection: tradingagents_primary_model" in hydrated_source
    assert "transport: http-sse" in hydrated_source
    assert "url: https://mcp.example.test/sse" in hydrated_source
    assert "headers:" not in hydrated_source
    assert "query:" not in hydrated_source
    assert set(safe_spec) == {
        "inputs",
        "capabilityProfiles",
        "outputSchemas",
        "mcpServers",
        "agents",
        "workflows",
    }
    assert set(safe_agents[0]) == {
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
    assert safe_mcp_server == {
        "key": "research_context",
        "name": "Research Context",
        "description": "Local context server declaration.",
        "transport": "http-sse",
        "url": "https://mcp.example.test/sse",
        "toolKeys": ["research_context.search"],
    }


def test_manifest_hydration_strips_inline_private_mcp_env() -> None:
    hydrated = build_workflow_package_manifest_hydration_payload(
        {"manifestSource": _valid_package_manifest_source()}
    )

    hydrated_source = cast(str, hydrated["manifestSource"])
    assert "env:" not in hydrated_source
    assert "local-token" not in hydrated_source


def test_export_strips_inline_private_mcp_values() -> None:
    http_sse_exported = export_workflow_package_yaml(
        {"manifestSource": _valid_http_sse_package_manifest_source()}
    )
    stdio_exported = export_workflow_package_yaml(
        {"manifestSource": _valid_package_manifest_source()}
    )

    assert "headers:" not in http_sse_exported
    assert "query:" not in http_sse_exported
    assert "Authorization" not in http_sse_exported
    assert "test-token" not in http_sse_exported
    assert "test-api-key" not in http_sse_exported
    assert "env:" not in stdio_exported
    assert "local-token" not in stdio_exported
