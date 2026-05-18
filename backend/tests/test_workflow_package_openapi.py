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
    assert "/api/workflow-packages/{package_id}/versions" not in paths
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
        "/api/workflow-packages/{package_id}/manifest",
        "/api/workflow-packages/{package_id}/export",
        "/api/workflow-packages/{package_id}/preflight",
        "/api/workflow-packages/{package_id}/launch",
        "/api/workflow-packages/{package_id}/launches",
        "/api/tools",
    } <= route_paths
    assert "/api/workflow-packages/{package_id}/versions" not in route_paths
    assert route_paths.isdisjoint(_OLD_AUTHORING_PATHS)


def test_workflow_package_openapi_is_current_package_only(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    schemas = cast(dict[str, dict[str, object]], openapi["components"]["schemas"])
    paths = cast(dict[str, dict[str, object]], openapi["paths"])

    assert "WorkflowPackageVersionRead" not in schemas
    assert "WorkflowPackageVersionListRead" not in schemas
    assert "WorkflowPackageImportMode" not in schemas

    package_properties = cast(dict[str, object], schemas["WorkflowPackageRead"]["properties"])
    assert "latestVersion" not in package_properties
    assert "latestVersionId" not in package_properties

    manifest_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageManifestRead"]["properties"],
    )
    assert "version" not in manifest_properties

    launch_properties = cast(dict[str, object], schemas["WorkflowPackageLaunchRead"]["properties"])
    assert "packageVersion" not in launch_properties
    launch_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageLaunchCreateRequest"]["properties"],
    )
    assert "version" not in launch_request_properties

    import_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageImportRequest"]["properties"],
    )
    assert "mode" not in import_request_properties

    for path in (
        "/api/workflow-packages/{package_id}/manifest",
        "/api/workflow-packages/{package_id}/export",
        "/api/workflow-packages/{package_id}/preflight",
        "/api/workflow-packages/{package_id}/launch",
        "/api/workflow-packages/{package_id}/launches",
    ):
        for raw_operation in paths[path].values():
            operation = cast(dict[str, object], raw_operation)
            parameters = cast(list[dict[str, object]], operation.get("parameters") or [])
            assert all(parameter["name"] != "version" for parameter in parameters)
