# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.repositories.run import RunRepository
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanOperation,
    ExecutionPlanStep,
    ExecutionPlanTarget,
    PackageLocalOutputSchemaSpec,
    PackageResolvedModelBinding,
    PackageRuntimeAgentSpec,
    PackageRuntimeOperationSpec,
)
from app.services.http_operation_execution_service import HttpOperationExecutionService
from app.services.run_service import RunAgentInvocationResult, RunService
from tests.test_workflow_package_manifest_http_node import http_node_package_source

UTC_TZ = timezone.utc  # noqa: UP017


class _CapturingTransport(httpx.MockTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return response

        super().__init__(handler)


def _settings() -> Settings:
    return Settings(
        HTTP_OPERATION_ALLOW_INSECURE_HTTP=False,
        HTTP_OPERATION_BLOCK_PRIVATE_NETWORKS=True,
    )


def _client_factory(transport: _CapturingTransport) -> Callable[..., httpx.Client]:
    def factory(**kwargs: Any) -> httpx.Client:
        return httpx.Client(transport=transport, **kwargs)

    return factory


def _http_service(
    session: Session,
    transport: _CapturingTransport,
) -> HttpOperationExecutionService:
    return HttpOperationExecutionService(
        session,
        settings=_settings(),
        client_factory=_client_factory(transport),
        resolved_hosts={
            "api.example.test": ("93.184.216.34",),
            "example.test": ("93.184.216.34",),
        },
    )


def _claim_run(session_factory: sessionmaker[Session], run_id: int) -> None:
    with session_factory() as session:
        claimed = RunRepository(session).claim_next_queued(run_id=run_id)
        assert claimed is not None
        assert claimed.started_at is None
        session.commit()


def _execute_claimed_run_with_http_service(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    transport: _CapturingTransport,
) -> None:
    with session_factory() as session:
        service = RunService(session, session_factory)
        service.http_operation_execution_service = _http_service(session, transport)
        service.execute_claimed_run(run_id)


def _package_source(package_key: str) -> str:
    source = http_node_package_source().replace(
        "key: http_callbacks",
        f"key: {package_key}",
        1,
    )
    return source.replace(
        "      jsonSchema:\n        type: object\n  workflows:",
        "      jsonSchema:\n        type: object\n        properties:\n"
        "          ok:\n            type: boolean\n"
        "          message:\n            type: string\n  workflows:",
        1,
    )


def test_final_output_resolves_from_http_operation_slot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source("final_output_http_callbacks")},
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
            "workflowKey": "notify",
            "parameters": {
                "webhookUrl": "https://api.example.test/hooks?api_key=visible-secret",
                "ticker": "MSFT",
            },
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    transport = _CapturingTransport(
        httpx.Response(
            200,
            json={"ok": True, "message": "queued"},
            headers={"content-type": "application/json"},
        )
    )

    _claim_run(session_factory, run_id)
    _execute_claimed_run_with_http_service(
        session_factory,
        run_id=run_id,
        transport=transport,
    )
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    operation = cast(dict[str, Any], detail["steps"][0]["operationInvocations"][0])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"ok": True, "message": "queued"}
    assert operation["status"] == "succeeded"
    assert operation["outputOrigin"] == "executed"
    assert operation["output"] == {"ok": True, "message": "queued"}
    assert operation["requestMetadata"]["url"] == (
        "https://api.example.test/hooks?api_key=%5BREDACTED%5D&ticker=MSFT"
    )
    assert transport.requests[0].method == "POST"
    with session_factory() as session:
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() == 0
        persisted_operation = session.query(RunOperationInvocation).filter_by(run_id=run_id).one()
        assert persisted_operation.output == {"ok": True, "message": "queued"}


def test_deleted_package_rerun_does_not_fallback_to_replacement_secret_bindings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    package_key = "deleted_secret_http_callbacks"
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key)},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    package_id = int(package["id"])
    for key, value in {
        "slack_webhook_token": "original-slack-secret",
        "body_token": "original-body-secret",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package_id}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {
                "webhookUrl": "https://api.example.test/hooks",
                "ticker": "MSFT",
            },
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    source_run_id = int(launch_response.json()["id"])
    original_transport = _CapturingTransport(
        httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    _claim_run(session_factory, source_run_id)
    _execute_claimed_run_with_http_service(
        session_factory,
        run_id=source_run_id,
        transport=original_transport,
    )
    source_detail = client.get(f"/api/runs/{source_run_id}")
    assert source_detail.status_code == 200, source_detail.json()
    assert source_detail.json()["status"] == "succeeded"

    delete_response = client.delete(f"/api/workflow-packages/{package_id}")
    assert delete_response.status_code == 204, delete_response.text
    replacement_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key)},
    )
    assert replacement_response.status_code == 201, replacement_response.json()
    replacement = cast(dict[str, Any], replacement_response.json())
    for key, value in {
        "slack_webhook_token": "replacement-slack-secret",
        "body_token": "replacement-body-secret",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{replacement['id']}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    with session_factory() as session:
        source_run = session.get(Run, source_run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, source_run_id)
        assert source_run is not None
        assert snapshot is not None
        assert source_run.workflow_package_id is None
        assert snapshot.workflow_package_id == package_id
        serialized_snapshot = str(snapshot.package_definition) + str(snapshot.compiled_plan)
        assert "original-slack-secret" not in serialized_snapshot
        assert "replacement-slack-secret" not in serialized_snapshot

    rerun_response = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={
            "parameters": {
                "webhookUrl": "https://api.example.test/hooks",
                "ticker": "AAPL",
            }
        },
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_transport = _CapturingTransport(
        httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    _claim_run(session_factory, rerun_id)
    _execute_claimed_run_with_http_service(
        session_factory,
        run_id=rerun_id,
        transport=rerun_transport,
    )
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_detail = cast(dict[str, Any], rerun_detail_response.json())
    operation = cast(dict[str, Any], rerun_detail["steps"][0]["operationInvocations"][0])
    provenance = cast(dict[str, Any], rerun_detail["packageProvenance"])

    assert rerun_detail["status"] == "failed"
    assert rerun_detail["error"] == "HTTP secret binding 'slack_webhook_token' was not found"
    assert operation["status"] == "failed"
    assert operation["errorCode"] == "http_operation_secret_missing"
    assert provenance["workflowPackageId"] == package_id
    assert provenance["currentPackage"]["available"] is False
    assert rerun_transport.requests == []


def _schema(local_id: int, key: str, properties: dict[str, Any]) -> PackageLocalOutputSchemaSpec:
    return PackageLocalOutputSchemaSpec(
        local_id=local_id,
        key=key,
        name=key.replace("_", " ").title(),
        description=f"{key} schema",
        json_schema={
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
        },
    )


def _model_binding() -> PackageResolvedModelBinding:
    return PackageResolvedModelBinding(
        key="mixed_model",
        name="Mixed Model",
        connection_kind="deterministic_smoke",
        base_url="https://model.example.test/v1",
        model_id="mixed-model",
        reasoning_effort=None,
        api_style="responses",
        timeout_seconds=10,
        has_api_key=False,
    )


def _mixed_plan() -> ExecutionPlan:
    agent_output = _schema(1, "agent_output", {"summary": {"type": "string"}})
    operation_output = _schema(2, "operation_output", {"ok": {"type": "boolean"}})
    agent = PackageRuntimeAgentSpec(
        local_id=1,
        key="mixed_agent",
        name="Mixed Agent",
        description="Agent branch of a mixed step.",
        model_binding=_model_binding(),
        system_prompt="Return a summary.",
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "webhookUrl": {"type": "string"},
            },
            "required": ["ticker", "webhookUrl"],
        },
        output_schema=agent_output,
        capability_profiles=(),
        mcp_servers=(),
        budget_usd=Decimal("0"),
    )
    operation = PackageRuntimeOperationSpec(
        key="notify_after_agent",
        kind="http",
        slot="webhook_result",
        method="POST",
        request={
            "url": {"from": "input", "path": "webhookUrl"},
            "headers": {},
            "query": {},
            "body": {"ticker": {"from": "input", "path": "ticker"}},
        },
        output_schema=operation_output,
        timeout_seconds=5,
        optional=False,
    )
    return ExecutionPlan(
        target=ExecutionPlanTarget(
            kind="workflow_package",
            id=123,
            key="mixed_package",
            version=1,
        ),
        input_schema={"type": "object", "additionalProperties": True},
        aggregate_budget_usd=Decimal("0"),
        steps=(
            ExecutionPlanStep(
                index=1,
                agents=(
                    ExecutionPlanAgent(
                        slot="analysis",
                        agent_id=1,
                        agent_key=agent.key,
                        agent_version=1,
                        output_schema_id=1,
                        output_schema_version=1,
                        wiring={},
                        input_mode="passthrough",
                        package_runtime_agent=agent,
                    ),
                ),
                operations=(
                    ExecutionPlanOperation(
                        slot=operation.slot,
                        operation_key=operation.key,
                        operation_kind=operation.kind,
                        output_schema_id=2,
                        output_schema_version=1,
                        request=operation.request,
                        method=operation.method,
                        timeout_seconds=operation.timeout_seconds,
                        package_runtime_operation=operation,
                    ),
                ),
            ),
        ),
        final_output=ExecutionPlanFinalOutput(step_index=1, slot="analysis"),
    )


def _running_run(session: Session) -> Run:
    timestamp = datetime(2026, 5, 15, 9, 0, tzinfo=UTC_TZ)
    run_input = {"ticker": "MSFT", "webhookUrl": "https://api.example.test/mixed"}
    run = Run(
        target_kind="workflowPackage",
        target_id=123,
        target_key="mixed_package",
        target_version=1,
        workflow_package_key="mixed_package",
        workflow_package_workflow_key="mixed_workflow",
        input=run_input,
        status="running",
        queued_at=timestamp,
        started_at=timestamp,
        resume_step_index=1,
        total_tokens=0,
        inherited_tokens=0,
        executed_tokens=0,
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=123,
        workflow_package_key="mixed_package",
        workflow_package_name="Mixed Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key="mixed_workflow",
        workflow_name="Mixed Workflow",
        workflow_description="",
        manifest_hash="manifest-mixed",
        compiled_hash="compiled-mixed",
        manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
        package_definition={"metadata": {"key": "mixed_package", "name": "Mixed Package"}},
        compiled_plan={"packageKey": "mixed_package", "workflows": [{"key": "mixed_workflow"}]},
        extension_dependencies=[],
        local_resource_refs={
            "agents": ["mixed_agent"],
            "outputSchemas": ["agent_output", "operation_output"],
            "capabilityProfiles": [],
            "mcpServers": [],
            "workflows": ["mixed_workflow"],
        },
        input_schema={"type": "object", "additionalProperties": True},
        launch_parameters=run_input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    return run


def test_mixed_execution_runs_agent_and_http_operation_families(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    plan = _mixed_plan()
    transport = _CapturingTransport(
        httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    agent_calls: list[dict[str, Any]] = []

    async def fake_invoke_agent(**kwargs: Any) -> RunAgentInvocationResult:
        agent_calls.append(cast(dict[str, Any], kwargs))
        return RunAgentInvocationResult(
            output={"summary": f"analysis for {kwargs['resolved_input']['ticker']}"},
            tokens=7,
            duration_ms=11,
        )

    with session_factory() as session:
        run = _running_run(session)
        service = RunService(session, session_factory)
        service.http_operation_execution_service = _http_service(session, transport)
        monkeypatch.setattr(service, "_invoke_agent", fake_invoke_agent)
        service._create_planned_run_rows(
            run=run,
            plan=plan,
            validated_input=cast(dict[str, Any], run.input),
        )
        session.commit()

        asyncio.run(service._execute_run_with_trace(run=run, plan=plan, trace_id=None))
        session.refresh(run)
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run.id).one()
        operation = session.query(RunOperationInvocation).filter_by(run_id=run.id).one()

        assert run.status == "succeeded", (
            run.error,
            invocation.error_code,
            invocation.error_message,
            invocation.error_details,
            operation.error_code,
            operation.error_message,
        )
        assert run.final_output == {"summary": "analysis for MSFT"}
        assert run.executed_tokens == 7
        assert invocation.status == "succeeded"
        assert invocation.output_origin == "executed"
        assert invocation.output == {"summary": "analysis for MSFT"}
        assert operation.status == "succeeded"
        assert operation.output_origin == "executed"
        assert operation.output == {"ok": True}
        assert operation.request_metadata["body"] == {"ticker": {"from": "input", "path": "ticker"}}

    assert len(agent_calls) == 1
    assert transport.requests[0].method == "POST"
    assert str(transport.requests[0].url) == "https://api.example.test/mixed"
