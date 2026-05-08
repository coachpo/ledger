from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient

_CANONICAL_TOOL_KEYS = {
    "ledger.market_data.quote_lookup",
    "ledger.reports.write",
}


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert _CANONICAL_TOOL_KEYS <= set(tools_by_key)
    quote_tool = tools_by_key["ledger.market_data.quote_lookup"]
    report_write_tool = tools_by_key["ledger.reports.write"]
    assert quote_tool == {
        "key": "ledger.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
        "module": "app.agents.tool_catalog.server_declared",
    }
    assert report_write_tool["displayName"] == "Report Memory Write"
    assert report_write_tool["module"] == "app.agents.tool_catalog.server_declared"
    assert "toolGrants" not in quote_tool
    assert "toolDefinitions" not in quote_tool


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}
