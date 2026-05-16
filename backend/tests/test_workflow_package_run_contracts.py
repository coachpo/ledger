from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.report import Report
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService
from app.services.run_service import RunService
from tests.test_workflow_package_manifest_http_node import http_node_package_source
from tests.test_workflow_package_preflight import _package_source as _tradingagents_package_source
from tests.test_workflow_package_preflight import (
    _seed_model_connection as _seed_tradingagents_model_connection,
)
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


def test_operation_invocation_read_shape_for_http_package_run_is_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    for key, value in {
        "slack_webhook_token": "slack-secret-value",
        "body_token": "body-secret-value",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package['id']}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    step = cast(dict[str, Any], detail["steps"][0])
    operation_invocations = cast(list[dict[str, Any]], step["operationInvocations"])
    request_metadata = cast(dict[str, Any], operation_invocations[0]["requestMetadata"])
    serialized = json.dumps(detail, sort_keys=True)

    assert step["invocations"] == []
    assert len(operation_invocations) == 1
    assert operation_invocations[0]["operationKey"] == "notify_slack"
    assert operation_invocations[0]["operationKind"] == "http"
    assert operation_invocations[0]["status"] == "pending"
    assert request_metadata["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
        "redacted": True,
    }
    assert request_metadata["body"]["token"] == {
        "from": "secret",
        "key": "body_token",
        "redacted": True,
    }
    assert "slack-secret-value" not in serialized
    assert "body-secret-value" not in serialized
    assert "secretPayload" not in serialized
    with session_factory() as session:
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() == 0
        operation = session.query(RunOperationInvocation).filter_by(run_id=run_id).one()
        assert operation.request_metadata == request_metadata


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
            "connectionKind": "provider",
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
    rerun_provenance = cast(dict[str, Any], rerun_draft.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageKey"] == "provenance_filter_package"
    assert rerun_provenance["resolvedModelConnections"][0]["connectionKind"] == "provider"


def test_delete_package_cascades_launched_runs_steps_invocations_and_memory_reports(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "cascade package output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="cascade_run_package")
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])
    memory_slug = f"agent_memory_cascade_run_{run_id}"

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    with session_factory() as session:
        assert session.get(Run, run_id) is not None
        assert session.query(RunStep).filter_by(run_id=run_id).count() > 0
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() > 0
        session.add(
            Report(
                name=f"Agent Memory Cascade Run {run_id}",
                slug=memory_slug,
                source="agent",
                content="# Agent memory",
                metadata_={
                    "analysis": {"reviewType": "agent_memory", "runId": run_id},
                },
            )
        )
        session.commit()

    deleted = client.delete(f"/api/workflow-packages/{package['id']}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert client.get(f"/api/runs/{run_id}").status_code == 404

    with session_factory() as session:
        assert session.get(Run, run_id) is None
        assert session.query(RunStep).filter_by(run_id=run_id).count() == 0
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() == 0
        assert session.query(Report).filter_by(slug=memory_slug).count() == 0


def _create_tradingagents_package(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _tradingagents_package_source()},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _tradingagents_parameters() -> dict[str, object]:
    return {
        "ticker": "MSFT",
        "asOfDate": "2026-05-15",
        "portfolioId": "portfolio-1",
        "horizonDays": 30,
        "benchmarkSymbol": "SPY",
        "initialInvestmentDebateState": {},
        "initialRiskDebateState": {},
    }


def _disable_finance_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )


def test_tradingagents_advisory_research_launch_persists_extension_dependencies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )

    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert dependencies
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
    assert dependencies[0]["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    surfaces = cast(list[str], dependencies[0]["surfaces"])
    assert "tool.signaldeck.market_data.quote_lookup" in surfaces


def test_tradingagents_advisory_research_launch_blocks_extension_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    _disable_finance_extension(session_factory)

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )

    assert launch_response.status_code == 422, launch_response.json()
    body = launch_response.json()
    assert body["code"] == "validation_error"
    details = cast(list[dict[str, object]], body["details"])
    assert any(
        detail.get("code") == "extension_disabled"
        and detail.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        for detail in details
    )


def test_tradingagents_advisory_research_runtime_fails_when_extension_disabled_after_launch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    _disable_finance_extension(session_factory)

    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert detail["status"] == "failed"
    assert detail["error"] == "Extension is disabled"
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
