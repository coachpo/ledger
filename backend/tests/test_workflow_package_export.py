from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_http_node import http_node_package_source


def test_secret_binding_export_keeps_manifest_secret_references(client: TestClient) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())

    secret_response = client.put(
        f"/api/workflow-packages/{package['id']}/secret-bindings/slack_webhook_token",
        json={"value": "slack-secret-value"},
    )
    assert secret_response.status_code == 200, secret_response.json()

    export_response = client.get(f"/api/workflow-packages/{package['id']}/export")

    assert export_response.status_code == 200, export_response.text
    exported = export_response.text
    assert "kind: http" in exported
    assert "Authorization: ${{ secrets.slack_webhook_token }}" in exported
    assert "token: ${{ secrets.body_token }}" in exported
    assert compile_workflow_package_manifest(exported)["packageDefinition"] == (
        compile_workflow_package_manifest(http_node_package_source())["packageDefinition"]
    )
