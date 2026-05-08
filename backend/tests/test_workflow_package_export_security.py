# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.services.workflow_package_export import export_workflow_package_yaml
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def test_export_never_contains_secrets_ids_or_encrypted_payloads() -> None:
    compiled = compile_workflow_package_manifest(_valid_package_manifest_source())
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
            "env": {"RESEARCH_TOKEN": "raw-env-token"},
            "headers": {"Authorization": "Bearer raw-header-token"},
            "auth": {"header": "X-Api-Key", "apiKey": "raw-auth-token"},
            "encrypted": {"ciphertext": "encrypted-bytes"},
        }
    )

    exported = export_workflow_package_yaml(
        {"packageDefinition": package_definition, "compiledPlan": compiled_plan}
    )
    exported_bytes = exported.encode("utf-8")

    assert "apiVersion: ledger.workflowPackage/v1" in exported
    assert "modelConnection: tradingagents_primary_model" in exported
    assert "secretRefs:" in exported
    assert "requiredBindings:" in exported
    assert "RESEARCH_TOKEN" in exported
    assert "Authorization" in exported
    assert "X-Api-Key" in exported
    for forbidden in (
        b"sk-",
        b"apiKey",
        b"secretPayload",
        b"encrypted",
        b"password",
        b"raw-env-token",
        b"raw-header-token",
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
    assert safe_mcp_server["secretRefs"] == {
        "env": ["RESEARCH_TOKEN"],
        "headers": ["Authorization", "X-Api-Key"],
    }
    assert safe_mcp_server["requiredBindings"] == [
        "env.RESEARCH_TOKEN",
        "header.Authorization",
        "header.X-Api-Key",
    ]
