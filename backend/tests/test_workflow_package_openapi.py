# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from __future__ import annotations

from typing import cast

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


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


def test_workflow_package_openapi_is_current_package_only(client: TestClient) -> None:
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    paths = cast(dict[str, dict[str, object]], openapi["paths"])

    assert "WorkflowPackageVersionRead" not in schemas
    assert "WorkflowPackageVersionListRead" not in schemas
    assert "WorkflowPackageImportMode" not in schemas

    package_properties = cast(dict[str, object], schemas["WorkflowPackageRead"]["properties"])
    assert "status" not in package_properties
    assert "latestVersion" not in package_properties
    assert "latestVersionId" not in package_properties
    assert "warnings" not in package_properties
    assert "validation" + "Summary" not in package_properties
    assert "last" + "LaunchedAt" not in package_properties
    assert "ready" not in package_properties
    assert "blockingErrors" not in package_properties

    manifest_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageManifestRead"]["properties"],
    )
    assert "version" not in manifest_properties

    launch_properties = cast(dict[str, object], schemas["WorkflowPackageLaunchRead"]["properties"])
    assert "packageVersion" not in launch_properties
    assert "facts" not in launch_properties
    assert {"ready", "blockingErrors", "warnings"} <= set(launch_properties)
    launch_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageLaunchCreateRequest"]["properties"],
    )
    assert "version" not in launch_request_properties

    update_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageUpdateRequest"]["properties"],
    )
    assert "status" not in update_request_properties

    import_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageImportRequest"]["properties"],
    )
    assert "mode" not in import_request_properties

    provenance_properties = cast(
        dict[str, object],
        schemas["RunPackageProvenanceRead"]["properties"],
    )
    current_package_properties = cast(
        dict[str, object],
        schemas["RunCurrentPackageAuditRead"]["properties"],
    )
    assert "workflowPackageStatus" in provenance_properties
    assert "currentPackage" in provenance_properties
    assert "status" not in current_package_properties

    list_operation = cast(dict[str, object], paths["/api/workflow-packages"]["get"])
    list_parameters = cast(
        list[dict[str, object]],
        list_operation.get("parameters") or [],
    )
    assert all(parameter["name"] != "status" for parameter in list_parameters)

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


def test_schedule_openapi_exposes_hard_delete_operation(client: TestClient) -> None:
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    paths = cast(dict[str, dict[str, object]], openapi["paths"])

    assert "/api/schedules/{scheduleId}" in paths

    delete_operation = cast(dict[str, object], paths["/api/schedules/{scheduleId}"]["delete"])
    delete_responses = cast(dict[str, dict[str, object]], delete_operation["responses"])
    assert "204" in delete_responses
    assert "content" not in delete_responses["204"]


def test_schedule_openapi_removes_archive_route(client: TestClient) -> None:
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    paths = cast(dict[str, dict[str, object]], openapi["paths"])
    schedule_paths = {path for path in paths if path.startswith("/api/schedules/")}

    assert "/api/schedules/{scheduleId}/archive" not in paths
    assert all(not path.endswith("/archive") for path in schedule_paths)
