# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.services.workflow_package_export import export_workflow_package_yaml
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_http_sse_package_manifest_source


def test_export_emits_authoring_safe_mcp_manifest() -> None:
    compiled = compile_workflow_package_manifest(_valid_http_sse_package_manifest_source())
    package_definition = deepcopy(cast(dict[str, Any], compiled["packageDefinition"]))
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    spec = cast(dict[str, Any], package_definition["spec"])
    spec["id"] = 99
    agent = cast(list[dict[str, Any]], spec["agents"])[0]
    agent.update(
        {
            "id": 123,
            "agentId": 456,
            "modelConnectionId": 789,
            "secretPayload": {"apiKey": "sk-export-secret"},
            "password": "raw-password",
        }
    )
    mcp_server = cast(list[dict[str, Any]], spec["mcpServers"])[0]
    mcp_server.update(
        {
            "id": 321,
            "mcpServerId": 654,
            "env": {"EXA_TOKEN": "raw-env-token"},
            "headers": {
                "Authorization": "Bearer raw-header-token",
                "X-Api-Key": "raw-api-key",
            },
            "query": {"api_key": "raw-query-token"},
            "auth": {"header": "X-Api-Key", "apiKey": "raw-auth-token"},
            "encrypted": {"ciphertext": "encrypted-bytes"},
        }
    )

    exported = export_workflow_package_yaml(
        {"packageDefinition": package_definition, "compiledPlan": compiled_plan}
    )
    recompiled = compile_workflow_package_manifest(exported)
    safe_definition = cast(dict[str, Any], recompiled["packageDefinition"])
    safe_spec = cast(dict[str, Any], safe_definition["spec"])
    safe_agents = cast(list[dict[str, Any]], safe_spec["agents"])
    safe_mcp_server = cast(list[dict[str, Any]], safe_spec["mcpServers"])[0]

    assert "apiVersion: signaldeck.workflowPackage/v1" in exported
    assert "modelConnection: tradingagents_primary_model" in exported
    assert "transport: http-sse" in exported
    assert "url: https://mcp.example.test/sse" in exported
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
