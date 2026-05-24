# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
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
from app.schemas.model_connection import default_model_connection_capabilities
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


def test_package_delete_removes_http_operation_run_and_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
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
    assert delete_response.content == b""

    rerun_response = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={
            "parameters": {
                "webhookUrl": "https://api.example.test/hooks",
                "ticker": "AAPL",
            }
        },
    )
    assert rerun_response.status_code == 404, rerun_response.json()
    with session_factory() as session:
        assert session.get(Run, source_run_id) is None
        assert session.get(RunWorkflowPackageSnapshot, source_run_id) is None
        assert session.query(RunOperationInvocation).filter_by(run_id=source_run_id).count() == 0


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
    protocol_profile = "openai_responses"
    return PackageResolvedModelBinding(
        key="mixed_model",
        name="Mixed Model",
        connection_kind="deterministic_smoke",
        protocol_profile=protocol_profile,
        base_url="https://model.example.test/v1",
        model_id="mixed-model",
        reasoning_effort=None,
        capabilities=default_model_connection_capabilities(protocol_profile).model_dump(
            mode="json",
            by_alias=True,
        ),
        output_strategy_policy="prefer_strict_schema",
        parallel_tool_calls_policy="serialize",
        reasoning_policy="allow",
        streaming_policy="allow",
        probe_cache_ttl_seconds=900,
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


def test_progress_for_running_run_without_invocations_stays_zero_in_list_and_detail(
    session_factory: sessionmaker[Session],
) -> None:
    expected_progress = {
        "unit": "invocation",
        "terminalCount": 0,
        "totalCount": 0,
        "percent": 0,
    }
    with session_factory() as session:
        run = _running_run(session)
        run_id = run.id
        session.commit()

    with session_factory() as session:
        service = RunService(session, session_factory)
        detail = service.get_run(run_id).model_dump(mode="json", by_alias=True)
        run_list = service.list_runs().model_dump(mode="json", by_alias=True)

    assert detail["status"] == "running"
    assert detail["progress"] == expected_progress
    items = cast(list[dict[str, Any]], run_list["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed"])
def test_progress_for_terminal_run_without_invocations_is_complete_in_list_and_detail(
    terminal_status: str,
    session_factory: sessionmaker[Session],
) -> None:
    expected_progress = {
        "unit": "invocation",
        "terminalCount": 0,
        "totalCount": 0,
        "percent": 100,
    }
    with session_factory() as session:
        run = _running_run(session)
        run.status = terminal_status
        run.finished_at = run.started_at
        run.error = "terminal failure" if terminal_status == "failed" else None
        run.final_output = {"summary": "done"} if terminal_status == "succeeded" else None
        run_id = run.id
        session.commit()

    with session_factory() as session:
        service = RunService(session, session_factory)
        detail = service.get_run(run_id).model_dump(mode="json", by_alias=True)
        run_list = service.list_runs().model_dump(mode="json", by_alias=True)

    assert detail["status"] == terminal_status
    assert detail["progress"] == expected_progress
    items = cast(list[dict[str, Any]], run_list["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


def test_progress_for_running_mixed_agent_operation_invocations_matches_list_and_detail(
    session_factory: sessionmaker[Session],
) -> None:
    plan = _mixed_plan()
    with session_factory() as session:
        run = _running_run(session)
        service = RunService(session, session_factory)
        service._create_planned_run_rows(
            run=run,
            plan=plan,
            validated_input=cast(dict[str, Any], run.input),
        )
        session.flush()
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run.id).one()
        operation = session.query(RunOperationInvocation).filter_by(run_id=run.id).one()
        invocation.status = "succeeded"
        invocation.output = {"summary": "partial progress"}
        invocation.output_origin = "executed"
        operation.status = "running"
        run_id = run.id
        session.commit()

    expected_progress = {
        "unit": "invocation",
        "terminalCount": 1,
        "totalCount": 2,
        "percent": 50,
    }
    with session_factory() as session:
        service = RunService(session, session_factory)
        detail = service.get_run(run_id).model_dump(mode="json", by_alias=True)
        run_list = service.list_runs().model_dump(mode="json", by_alias=True)

    assert detail["progress"] == expected_progress
    step = cast(dict[str, Any], detail["steps"][0])
    assert step["invocations"][0]["status"] == "succeeded"
    assert step["operationInvocations"][0]["status"] == "running"
    items = cast(list[dict[str, Any]], run_list["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


def test_progress_for_terminal_run_with_sparse_invocation_counts_is_complete(
    session_factory: sessionmaker[Session],
) -> None:
    plan = _mixed_plan()
    with session_factory() as session:
        run = _running_run(session)
        service = RunService(session, session_factory)
        service._create_planned_run_rows(
            run=run,
            plan=plan,
            validated_input=cast(dict[str, Any], run.input),
        )
        session.flush()
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run.id).one()
        operation = session.query(RunOperationInvocation).filter_by(run_id=run.id).one()
        invocation.status = "succeeded"
        operation.status = "running"
        run.status = "failed"
        run.finished_at = run.started_at
        run.error = "operation interrupted"
        run_id = run.id
        session.commit()

    expected_progress = {
        "unit": "invocation",
        "terminalCount": 1,
        "totalCount": 2,
        "percent": 100,
    }
    with session_factory() as session:
        service = RunService(session, session_factory)
        detail = service.get_run(run_id).model_dump(mode="json", by_alias=True)
        run_list = service.list_runs().model_dump(mode="json", by_alias=True)

    assert detail["status"] == "failed"
    assert detail["progress"] == expected_progress
    items = cast(list[dict[str, Any]], run_list["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


class _RecordingModelExecutionGateway:
    init_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).init_calls.append((args, kwargs))

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []


def test_run_service_composes_gateway_without_direct_protocol_adapter(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RecordingModelExecutionGateway.reset()
    monkeypatch.setattr("app.services.run_service.ModelExecutionGateway", _RecordingModelExecutionGateway)
    with session_factory() as session:
        _ = RunService(session, session_factory)
    assert len(_RecordingModelExecutionGateway.init_calls) == 1
    args, kwargs = _RecordingModelExecutionGateway.init_calls[0]
    assert args == ()
    assert sorted(kwargs) == ["client_factory"]


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
