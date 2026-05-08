from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.agents import ToolCatalogValidationError, get_default_tool_catalog

_CANONICAL_TOOL_KEYS = {
    "ledger.market_data.quote_lookup",
    "ledger.reports.lookup",
    "ledger.reports.write",
}


def test_default_tool_catalog_rejects_duplicate_unknown_and_phase_one_memory_keys() -> None:
    catalog = get_default_tool_catalog()

    with pytest.raises(ToolCatalogValidationError) as exc_info:
        _ = catalog.resolve_tool_keys(
            [
                "ledger.reports.lookup",
                "ledger.reports.lookup",
                "ledger.memory.lookup",
                "ledger.memory.write",
            ]
        )

    assert exc_info.value.details == [
        {
            "field": "toolKeys.1",
            "issue": "Duplicate tool key 'ledger.reports.lookup' is not allowed",
        },
        {
            "field": "toolKeys.2",
            "issue": "Unknown server-declared tool 'ledger.memory.lookup'",
        },
        {
            "field": "toolKeys.3",
            "issue": "Unknown server-declared tool 'ledger.memory.write'",
        },
    ]


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert _CANONICAL_TOOL_KEYS <= set(tools_by_key)
    quote_tool = tools_by_key["ledger.market_data.quote_lookup"]
    report_lookup_tool = tools_by_key["ledger.reports.lookup"]
    report_write_tool = tools_by_key["ledger.reports.write"]
    assert quote_tool == {
        "key": "ledger.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
        "module": "app.agents.tool_catalog.server_declared",
    }
    assert report_lookup_tool == {
        "key": "ledger.reports.lookup",
        "displayName": "Report Lookup",
        "description": "Read persisted Ledger reports through server-owned report lookups.",
        "module": "app.agents.tool_catalog.server_declared",
    }
    assert report_write_tool == {
        "key": "ledger.reports.write",
        "displayName": "Report Memory Write",
        "description": "Create pending agent-memory reports through server-owned memory writes.",
        "module": "app.agents.tool_catalog.server_declared",
    }
    assert not any(key.startswith("ledger.memory.") for key in tools_by_key)
    for tool in (quote_tool, report_lookup_tool, report_write_tool):
        assert "toolGrants" not in tool
        assert "toolDefinitions" not in tool


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}
