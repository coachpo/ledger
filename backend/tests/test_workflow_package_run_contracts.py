from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.services.run_service import RunService
from tests.test_workflow_package_runtime_api import (
    _create_package,
    _drain_run_queue,
    _RuntimeRecordingOpenAIClient,
    _seed_model_connection,
    _wait_for_run,
)


def _launch_package_run(
    client: TestClient,
    package: dict[str, object],
    *,
    ticker: str = "MSFT",
) -> dict[str, Any]:
    response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": ticker},
        },
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def test_package_run_list_filters_and_detail_provenance_are_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory, api_key="sk-package-provenance-secret")
    first_package = _create_package(client, package_key="provenance_filter_package")
    second_package = _create_package(client, package_key="other_filter_package")
    first_package_id = cast(int, first_package["id"])

    first_run = _launch_package_run(client, first_package, ticker="MSFT")
    second_run = _launch_package_run(client, second_package, ticker="AAPL")

    by_package_key = client.get(
        "/api/runs",
        params={"workflowPackageKey": "provenance_filter_package"},
    )
    assert by_package_key.status_code == 200, by_package_key.json()
    assert [item["id"] for item in by_package_key.json()["items"]] == [first_run["id"]]

    by_package_id = client.get(
        "/api/runs",
        params={"workflowPackageId": first_package_id},
    )
    assert by_package_id.status_code == 200, by_package_id.json()
    assert [item["id"] for item in by_package_id.json()["items"]] == [first_run["id"]]

    by_workflow_key = client.get("/api/runs", params={"workflowKey": "runtime_workflow"})
    assert by_workflow_key.status_code == 200, by_workflow_key.json()
    assert [item["id"] for item in by_workflow_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    by_model_key = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_model_key.status_code == 200, by_model_key.json()
    assert [item["id"] for item in by_model_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    detail_response = client.get(f"/api/runs/{first_run['id']}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert detail["targetKind"] == "workflowPackage"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert provenance["workflowPackageId"] == first_package["id"]
    assert provenance["workflowPackageKey"] == "provenance_filter_package"
    assert provenance["workflowPackageVersion"] == 1
    assert provenance["workflowPackageVersionId"] is not None
    assert provenance["workflowPackageHash"]
    assert provenance["workflowKey"] == "runtime_workflow"
    assert provenance["launchSnapshot"]["parameters"] == {"ticker": "MSFT"}
    assert provenance["localResourceRefs"] == {
        "agents": ["package_analyst"],
        "outputSchemas": ["summary_output"],
        "capabilityProfiles": [],
        "mcpServers": [],
        "workflows": ["runtime_workflow"],
    }
    assert provenance["resolvedModelConnections"] == [
        {
            "key": "package_runtime_model",
            "name": "Package Runtime Model",
            "baseUrl": "https://runtime-v1.example.com/v1",
            "modelId": "gpt-package-v1",
            "reasoningEffort": "high",
            "apiStyle": "responses",
            "timeoutSeconds": 31,
            "hasApiKey": True,
        }
    ]
    assert provenance["preflightSummary"] == {
        "ready": True,
        "blockingErrors": [],
        "warnings": [],
    }
    assert provenance["availability"]["packageStatus"] == "active"
    assert provenance["availability"]["packageVersionAvailable"] is True
    serialized = json.dumps(detail, sort_keys=True)
    assert "sk-package-provenance-secret" not in serialized
    assert "secretPayload" not in serialized

    rerun_draft = client.get(f"/api/runs/{first_run['id']}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    assert rerun_draft.json()["packageProvenance"]["workflowPackageKey"] == (
        "provenance_filter_package"
    )


def test_package_run_drafts_reject_archived_package_artifacts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "archived package output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="archived_run_package")
    launched = _launch_package_run(client, package, ticker="NVDA")

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, int(launched["id"]))
    assert succeeded_detail["status"] == "succeeded"

    archive = client.delete(f"/api/workflow-packages/{package['id']}")
    assert archive.status_code == 200, archive.json()
    assert archive.json()["status"] == "archived"

    archived_detail = client.get(f"/api/runs/{launched['id']}")
    assert archived_detail.status_code == 200, archived_detail.json()
    availability = archived_detail.json()["packageProvenance"]["availability"]
    assert availability["packageStatus"] == "archived"
    assert availability["packageVersionAvailable"] is False
    assert availability["unavailableReason"] == "archivedPackage"

    rerun_draft = client.get(f"/api/runs/{launched['id']}/rerun-draft")
    assert rerun_draft.status_code == 400, rerun_draft.json()
    assert rerun_draft.json()["code"] == "workflow_package_run_artifact_unavailable"

    step_replay_draft = client.get(
        f"/api/runs/{launched['id']}/step-replay-draft",
        params={"stepIndex": 1},
    )
    assert step_replay_draft.status_code == 400, step_replay_draft.json()
    assert step_replay_draft.json()["code"] == "workflow_package_run_artifact_unavailable"
