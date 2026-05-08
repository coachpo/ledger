# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from __future__ import annotations

from typing import cast

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

_OLD_AUTHORING_PATHS = (
    "/api/agents",
    "/api/capabilities",
    "/api/mcp-servers",
    "/api/output-schemas",
    "/api/workflows",
)


def test_clean_break_removes_old_authoring_routes(client: TestClient) -> None:
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])

    assert "/api/workflow-packages" in paths
    assert "/api/tools" in paths
    assert "/api/model-connections" in paths
    assert "/api/runs" in paths
    for path in _OLD_AUTHORING_PATHS:
        assert path not in paths
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404


def test_workflow_package_routes_are_registered_without_old_authoring(app) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert {
        "/api/workflow-packages",
        "/api/workflow-packages/validate-manifest",
        "/api/workflow-packages/import",
        "/api/workflow-packages/{package_id}",
        "/api/workflow-packages/{package_id}/versions",
        "/api/workflow-packages/{package_id}/export",
        "/api/workflow-packages/{package_id}/launch",
        "/api/workflow-packages/{package_id}/launches",
        "/api/tools",
    } <= route_paths
    assert route_paths.isdisjoint(_OLD_AUTHORING_PATHS)
