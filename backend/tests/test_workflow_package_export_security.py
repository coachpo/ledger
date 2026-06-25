# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.services.workflow_package_export import export_workflow_package_yaml
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_http_sse_package_manifest_source


def test_export_redacts_secret_bearing_mcp_request_config() -> None:
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
    exported_bytes = exported.encode("utf-8")

    assert "apiVersion: signaldeck.workflowPackage/v1" in exported
    assert "modelConnection: tradingagents_primary_model" in exported
    assert "transport: http-sse" in exported
    assert "url: https://mcp.example.test/sse" in exported
    assert "env:" not in exported
    assert "headers:" not in exported
    assert "query:" not in exported
    assert "secretRefs:" not in exported
    assert "requiredBindings:" not in exported
    for forbidden in (
        b"sk-",
        b"apiKey",
        b"secretPayload",
        b"encrypted",
        b"password",
        b"raw-env-token",
        b"raw-header-token",
        b"raw-api-key",
        b"raw-query-token",
        b"raw-auth-token",
        b"modelConnectionId",
        b"mcpServerId",
        b"agentId",
        b"id: 99",
        b"id: 123",
    ):
        assert forbidden not in exported_bytes

    recompiled = compile_workflow_package_manifest(exported)
    safe_definition = cast(dict[str, Any], recompiled["packageDefinition"])
    safe_mcp_server = cast(
        list[dict[str, Any]], cast(dict[str, Any], safe_definition["spec"])["mcpServers"]
    )[0]
    assert "env" not in safe_mcp_server
    assert "headers" not in safe_mcp_server
    assert "query" not in safe_mcp_server
    assert "secretRefs" not in safe_mcp_server
    assert "requiredBindings" not in safe_mcp_server
