# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from __future__ import annotations

from typing import cast

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


def test_workflow_package_routes_are_registered(app) -> None:
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


def test_memory_review_api_is_not_registered(client: TestClient) -> None:
    response = client.get("/api/memory/proposals")

    assert response.status_code == 404


def test_workflow_package_openapi_exposes_current_package_shapes(client: TestClient) -> None:
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    paths = cast(dict[str, dict[str, object]], openapi["paths"])

    package_properties = cast(dict[str, object], schemas["WorkflowPackageRead"]["properties"])
    assert {
        "id",
        "key",
        "name",
        "description",
        "manifestHash",
        "compiledHash",
        "createdAt",
        "updatedAt",
    } <= set(package_properties)

    manifest_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageManifestRead"]["properties"],
    )
    assert {"packageId", "manifestSource"} <= set(manifest_properties)

    launch_properties = cast(dict[str, object], schemas["WorkflowPackageLaunchRead"]["properties"])
    assert {
        "packageId",
        "packageKey",
        "workflowKey",
        "ready",
        "blockingErrors",
        "warnings",
    } <= set(launch_properties)
    launch_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageLaunchCreateRequest"]["properties"],
    )
    assert {"workflowKey", "parameters"} <= set(launch_request_properties)

    update_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageUpdateRequest"]["properties"],
    )
    assert {"manifestSource"} <= set(update_request_properties)

    import_request_properties = cast(
        dict[str, object],
        schemas["WorkflowPackageImportRequest"]["properties"],
    )
    assert {"manifestSource"} <= set(import_request_properties)

    provenance_properties = cast(
        dict[str, object],
        schemas["RunPackageProvenanceRead"]["properties"],
    )
    run_properties = cast(dict[str, object], schemas["RunRead"]["properties"])
    current_package_properties = cast(
        dict[str, object],
        schemas["RunCurrentPackageAuditRead"]["properties"],
    )
    assert "workflowMemoryEvidence" not in run_properties
    assert "workflowPackageStatus" in provenance_properties
    assert "currentPackage" in provenance_properties
    assert {
        "available",
        "manifestHash",
        "manifestHashMatchesSnapshot",
        "compiledHash",
        "compiledHashMatchesSnapshot",
        "unavailableReason",
    } <= set(current_package_properties)

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
            assert "package_id" in {str(parameter["name"]) for parameter in parameters}


def test_schedule_openapi_exposes_hard_delete_operation(client: TestClient) -> None:
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    paths = cast(dict[str, dict[str, object]], openapi["paths"])

    assert "/api/schedules/{scheduleId}" in paths

    delete_operation = cast(dict[str, object], paths["/api/schedules/{scheduleId}"]["delete"])
    delete_responses = cast(dict[str, dict[str, object]], delete_operation["responses"])
    assert "204" in delete_responses
    assert "content" not in delete_responses["204"]
