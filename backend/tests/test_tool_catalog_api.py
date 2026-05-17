from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.runtime_tools import RUNTIME_TOOL_SPECS
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source

_CANONICAL_TOOL_KEYS = {
    "signaldeck.market_data.quote_lookup",
    "signaldeck.reports.lookup",
    "signaldeck.reports.write",
}


def test_signaldeck_finance_tool_inventory_matches_catalog_and_runtime() -> None:
    server_declared_keys = {tool.key for tool in SERVER_DECLARED_TOOL_SPECS}
    runtime_keys = {tool.key for tool in RUNTIME_TOOL_SPECS}
    runtime_function_names = {tool.openai_function_name for tool in RUNTIME_TOOL_SPECS}

    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == server_declared_keys
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == runtime_keys
    assert set(FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES) == runtime_function_names


def test_default_tool_catalog_rejects_duplicate_unknown_and_phase_one_memory_keys() -> None:
    catalog = get_default_tool_catalog()

    with pytest.raises(ToolCatalogValidationError) as exc_info:
        _ = catalog.resolve_tool_keys(
            [
                "signaldeck.reports.lookup",
                "signaldeck.reports.lookup",
                "signaldeck.memory.lookup",
                "signaldeck.memory.write",
            ]
        )

    assert exc_info.value.details == [
        {
            "field": "toolKeys.1",
            "issue": "Duplicate tool key 'signaldeck.reports.lookup' is not allowed",
        },
        {
            "field": "toolKeys.2",
            "issue": "Unknown server-declared tool 'signaldeck.memory.lookup'",
        },
        {
            "field": "toolKeys.3",
            "issue": "Unknown server-declared tool 'signaldeck.memory.write'",
        },
    ]


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert not any("module" in item for item in items)
    assert _CANONICAL_TOOL_KEYS <= set(tools_by_key)
    quote_tool = tools_by_key["signaldeck.market_data.quote_lookup"]
    report_lookup_tool = tools_by_key["signaldeck.reports.lookup"]
    report_write_tool = tools_by_key["signaldeck.reports.write"]
    assert quote_tool == {
        "key": "signaldeck.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
    }
    assert report_lookup_tool == {
        "key": "signaldeck.reports.lookup",
        "displayName": "Report Lookup",
        "description": "Read persisted SignalDeck reports through server-owned report lookups.",
    }
    assert report_write_tool == {
        "key": "signaldeck.reports.write",
        "displayName": "Report Memory Write",
        "description": "Create pending agent-memory reports through server-owned memory writes.",
    }
    assert not any(key.startswith("signaldeck.memory.") for key in tools_by_key)
    for tool in (quote_tool, report_lookup_tool, report_write_tool):
        assert "module" not in tool
        assert "ownerExtensionKey" not in tool
        assert "contributionCategories" not in tool
        assert "toolGrants" not in tool
        assert "toolDefinitions" not in tool


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}


def test_tool_catalog_hides_disabled_extension_tools_and_validation_classifies_them(
    client: TestClient,
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert response.status_code == 200, response.json()

    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200, tools_response.json()
    tools_body = cast(dict[str, object], tools_response.json())
    assert tools_body["items"] == []

    validation_response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": _valid_package_manifest_source()},
    )
    assert validation_response.status_code == 200, validation_response.json()
    body = cast(dict[str, object], validation_response.json())
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert body["metadata"] is None
    assert any(
        diagnostic["path"] == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
        and diagnostic["message"]
        == (
            "Server-declared tool 'signaldeck.market_data.quote_lookup' is disabled because "
            "extension 'signaldeck.finance' is disabled"
        )
        for diagnostic in diagnostics
    )
    assert not any("Unknown server-declared tool" in str(item) for item in diagnostics)
