from __future__ import annotations

from typing import cast

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

REMOVED_VERSIONING_PROPERTIES = {
    "latestVersion",
    "latestVersionId",
    "packageVersion",
    "targetVersion",
    "workflowPackageVersion",
    "workflowPackageVersionId",
}
REMOVED_VERSIONING_SCHEMAS = {
    "WorkflowPackageVersion",
    "WorkflowPackageVersionCreate",
    "WorkflowPackageVersionRead",
}
WORKFLOW_PACKAGE_PREFIX = "/api/workflow-packages"


def _route_paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def _openapi_schemas(app: FastAPI) -> dict[str, dict[str, object]]:
    openapi = cast(dict[str, object], app.openapi())
    components = cast(dict[str, object], openapi["components"])
    return cast(dict[str, dict[str, object]], components["schemas"])


def test_removed_workflow_package_versioning_routes_return_404(client: TestClient) -> None:
    assert client.get("/api/workflow-packages/1/versions").status_code == 404
    assert client.post("/api/workflow-packages/1/versions", json={}).status_code == 404
    assert client.get("/api/workflow-packages/1/versions/1").status_code == 404


def test_openapi_omits_workflow_package_versioning_contract(app: FastAPI) -> None:
    route_paths = _route_paths(app)
    openapi = cast(dict[str, object], app.openapi())
    openapi_paths = set(cast(dict[str, object], openapi["paths"]))

    for path in route_paths | openapi_paths:
        if path.startswith(WORKFLOW_PACKAGE_PREFIX):
            assert "/versions" not in path

    schemas = _openapi_schemas(app)
    assert schemas.keys().isdisjoint(REMOVED_VERSIONING_SCHEMAS)

    for schema_name in ("WorkflowPackageRead", "RunRead"):
        properties = cast(dict[str, object], schemas[schema_name]["properties"])
        assert properties.keys().isdisjoint(REMOVED_VERSIONING_PROPERTIES)
