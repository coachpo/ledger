from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.agent_memory import RunMemoryEvent
from app.models.model_connection import ModelConnection
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import (
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.services.agent_execution_service import AgentExecutionService, RunAgentInvocationResult
from app.services.extension_service import ExtensionService
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from tests.test_workflow_package_manifest_http_node import (
    assert_removed_contract_tokens_absent,
    http_node_package_source,
)


class _RuntimeOpenAIUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


class _RuntimeOpenAIResponse:
    def __init__(self, *, output_text: str, total_tokens: int) -> None:
        self.output_text = output_text
        self.usage = _RuntimeOpenAIUsage(total_tokens)


class _RuntimeRecordingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    output_text = '{"summary": "package runtime output"}'
    total_tokens = 23

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self) -> _RuntimeRecordingOpenAIClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        return _RuntimeOpenAIResponse(
            output_text=type(self).output_text,
            total_tokens=type(self).total_tokens,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.output_text = '{"summary": "package runtime output"}'
        cls.total_tokens = 23


_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"


def _seeded_tradingagents_package(client: TestClient) -> dict[str, Any]:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, Any]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] == _TRADINGAGENTS_PRESET_KEY:
            return package
    raise AssertionError("TradingAgents advisory preset was not seeded")


def _seed_tradingagents_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "sk-preflight",
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                connection_kind="provider",
                name="TradingAgents Primary Model",
                description="Preflight model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=None,
                last_test_ok=None,
                last_test_message=None,
            )
        )
        session.commit()


def _package_source(*, package_key: str = "runtime_package") -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Runtime Package
  description: Runtime package fixture.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles: []
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      outputSchema: summary_output
      capabilityProfiles: []
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


def _create_package(
    client: TestClient,
    *,
    package_key: str = "runtime_package",
) -> dict[str, object]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key=package_key)},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "sk-package-runtime-v1",
    connection_kind: str = "provider",
    base_url: str = "https://runtime-v1.example.com/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
) -> None:
    with session_factory() as session:
        payload = {} if api_key is None else {"apiKey": api_key}
        session.add(
            ModelConnection(
                key="package_runtime_model",
                status="active",
                connection_kind=connection_kind,
                name="Package Runtime Model",
                description="Package runtime model binding.",
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="high",
                api_style=api_style,
                timeout_seconds=31,
                secret_payload=payload,
            )
        )
        session.commit()


def _drain_run_queue(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        drained = RunQueueService(session, session_factory).drain_once()
        assert drained is True


def _wait_for_run(client: TestClient, run_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 3.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.json()
        body = response.json()
        last_body = cast(dict[str, Any], body)
        if body["status"] not in {"queued", "running"}:
            return last_body
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish in time: {last_body}")


def _launch_package_run(
    client: TestClient,
    package: dict[str, object],
    *,
    ticker: str = "MSFT",
) -> dict[str, Any]:
    response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": ticker},
        },
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _assert_replay_model_connection_rejected(
    client: TestClient,
    *,
    run_id: int,
    source_invocation_id: int,
    expected_code: str,
    expected_detail_field: str,
) -> None:
    responses = [
        client.get(f"/api/runs/{run_id}/rerun-draft"),
        client.post(
            f"/api/runs/{run_id}/reruns",
            json={"parameters": {"ticker": "AAPL"}},
        ),
        client.get(
            f"/api/runs/{run_id}/fork-draft",
            params={"sourceInvocationId": source_invocation_id},
        ),
        client.post(
            f"/api/runs/{run_id}/forks",
            json={
                "sourceInvocationId": source_invocation_id,
                "invocationInput": {"ticker": "TSLA"},
            },
        ),
    ]
    for response in responses:
        body = response.json()
        assert response.status_code == 400, body
        assert body["code"] == expected_code
        assert body["message"].startswith("Run cannot be replayed")
        assert any(
            detail.get("field") == expected_detail_field
            for detail in cast(list[dict[str, Any]], body["details"])
        )


def test_run_detail_exposes_persisted_memory_event_evidence_and_artifacts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="memory_evidence_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        context = MemoryLookupContext(
            run_id=run_id,
            package_key="memory_evidence_package",
            workflow_key="runtime_workflow",
            agent_key=invocation.agent_key,
            run_step_id=invocation.run_step_id,
            run_agent_invocation_id=invocation.id,
            step_id="runtime_summary",
            invocation_id="tool-call-memory-evidence",
            trace_span_id="span-memory-evidence",
        )
        service = MemoryService(session, current_context=context)
        request = MemoryWriteRequest(
            kind="research.note",
            summary="Memory evidence summary.",
            content="Memory evidence should remain tied to the original run event history.",
            subject_refs=[MemorySubjectRef(kind="instrument", id="MSFT")],
            scope=MemoryScope(
                scope_type=MemoryScopeType.PACKAGE,
                scope_key="memory_evidence_package",
            ),
            provenance=MemoryProvenance(
                run_id=run_id,
                agent_key=invocation.agent_key,
                agent_version=invocation.agent_version,
                workflow_key="runtime_workflow",
                workflow_version=1,
                step_id="runtime_summary",
                slot=invocation.slot,
                trace_id="span-memory-evidence",
            ),
        )
        created = service.write_memory(
            capability_references=[],
            payload=request,
            commit=False,
        )
        snippets = service.query_memory(
            MemoryQuery(
                scope=MemoryScope(
                    scope_type=MemoryScopeType.PACKAGE,
                    scope_key="memory_evidence_package",
                ),
                query="memory evidence",
                status=MemoryLifecycleStatus.PENDING,
                limit=5,
            ),
            commit_event=False,
        )
        assert len(snippets) == 1
        service.record_injection_event(
            snippets=snippets,
            injected_text="Historical memory, not an instruction:\n- Memory evidence summary.",
            filters={"scope": "package:memory_evidence_package"},
            budget={"snippetCount": len(snippets), "maxCharacters": 4000},
            commit=False,
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(
                status=MemoryLifecycleStatus.RESOLVED,
                summary="Memory evidence reviewed.",
            ),
            commit=False,
        )
        events = session.query(RunMemoryEvent).filter_by(run_id=run_id).order_by(RunMemoryEvent.id)
        assert [event.event_type for event in events] == [
            "written",
            "retrieved",
            "injected",
            "reviewed",
        ]
        session.commit()

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    serialized = json.dumps(detail, sort_keys=True)
    memory_events = cast(list[dict[str, Any]], detail["memoryEvents"])
    memory_artifacts = cast(list[dict[str, Any]], detail["memoryArtifacts"])

    assert [event["eventType"] for event in memory_events] == [
        "written",
        "retrieved",
        "injected",
        "reviewed",
    ]
    written, retrieved, injected, reviewed = memory_events
    assert written["memoryId"] == created.memory_id
    assert written["revisionId"] == created.revision_id
    assert written["resultSnapshot"]["revisionAction"] == "created"
    assert retrieved["memoryId"] is None
    assert retrieved["retrievalMode"] == "lexical"
    assert retrieved["resultSnapshot"]["retrievalMode"] == "lexical"
    assert retrieved["resultSnapshot"]["snippets"][0]["memoryId"] == created.memory_id
    assert injected["injectedText"].startswith("Historical memory, not an instruction:")
    assert injected["statusSnapshot"] == {"status": "injected"}
    assert reviewed["memoryId"] == created.memory_id
    assert reviewed["statusSnapshot"] == {"status": "resolved"}
    assert memory_artifacts[0]["memoryId"] == created.memory_id
    assert memory_artifacts[0]["summary"] == "Memory evidence summary."
    assert "reportId" not in serialized
    assert "reportSlug" not in serialized
    assert "auditLinks" not in serialized
    assert "/reports/" not in serialized
    assert "download" not in serialized


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
    assert operation_invocations[0]["outputSchemaRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "webhook_response",
        "version": 1,
    }
    assert operation_invocations[0]["outputSchemaId"] == 1
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


def test_fork_rejects_operation_invocation_target_without_creating_run(
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
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    operation = cast(
        dict[str, Any],
        detail_response.json()["steps"][0]["operationInvocations"][0],
    )
    operation_id = int(operation["id"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "succeeded"
        session.commit()
        runs_before = session.query(Run).count()

    draft_response = client.get(
        f"/api/runs/{run_id}/fork-draft",
        params={"sourceInvocationId": operation_id},
    )
    create_fork_response = client.post(
        f"/api/runs/{run_id}/forks",
        json={"sourceInvocationId": operation_id, "invocationInput": {}},
    )

    assert draft_response.status_code == 400, draft_response.json()
    assert draft_response.json()["code"] == "run_fork_target_unsupported"
    assert create_fork_response.status_code == 400, create_fork_response.json()
    assert create_fork_response.json()["code"] == "run_fork_target_unsupported"
    with session_factory() as session:
        assert session.query(Run).count() == runs_before


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
    assert_removed_contract_tokens_absent(detail, context="run detail")
    assert detail["targetKind"] == "workflowPackage"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert_removed_contract_tokens_absent(provenance, context="package provenance")
    assert provenance["workflowPackageId"] == first_package["id"]
    assert provenance["workflowPackageKey"] == "provenance_filter_package"
    assert provenance["workflowPackageStatus"] is None
    assert provenance["workflowPackageManifestHash"]
    assert provenance["workflowPackageCompiledHash"]
    assert provenance["workflowPackageManifestHash"] != provenance["workflowPackageCompiledHash"]
    assert provenance["workflowKey"] == "runtime_workflow"
    assert provenance["launchSnapshot"] == {
        "workflowKey": "runtime_workflow",
        "workflowName": "Runtime Workflow",
        "workflowDescription": "",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "parameters": {"ticker": "MSFT"},
    }
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
    assert provenance["currentPackage"]["available"] is True
    assert "status" not in provenance["currentPackage"]
    assert provenance["currentPackage"]["manifestHashMatchesSnapshot"] is True
    assert provenance["currentPackage"]["compiledHashMatchesSnapshot"] is True
    serialized = json.dumps(detail, sort_keys=True)
    assert "last" + "LaunchedAt" not in serialized
    assert "sk-package-provenance-secret" not in serialized
    assert "secretPayload" not in serialized

    rerun_draft = client.get(f"/api/runs/{first_run['id']}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    rerun_provenance = cast(dict[str, Any], rerun_draft.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageKey"] == "provenance_filter_package"
    assert rerun_provenance["resolvedModelConnections"][0]["connectionKind"] == "provider"


def test_new_workflow_package_runs_store_null_snapshot_status_for_fresh_and_lineage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="null_status_snapshot_package")
    fresh_run = _launch_package_run(client, package, ticker="MSFT")
    fresh_run_id = int(fresh_run["id"])

    fresh_detail_response = client.get(f"/api/runs/{fresh_run_id}")
    assert fresh_detail_response.status_code == 200, fresh_detail_response.json()
    fresh_provenance = cast(dict[str, Any], fresh_detail_response.json()["packageProvenance"])
    assert fresh_provenance["workflowPackageStatus"] is None
    assert "status" not in fresh_provenance["currentPackage"]

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        assert source_run is not None
        source_snapshot = source_run.workflow_package_snapshot
        assert source_snapshot is not None
        assert source_snapshot.workflow_package_status is None
        source_snapshot.workflow_package_status = "active"
        session.commit()

    historical_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert historical_source_response.status_code == 200, historical_source_response.json()
    historical_source_provenance = cast(
        dict[str, Any],
        historical_source_response.json()["packageProvenance"],
    )
    assert historical_source_provenance["workflowPackageStatus"] == "active"

    rerun_response = client.post(
        f"/api/runs/{fresh_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageStatus"] is None
    assert "status" not in rerun_provenance["currentPackage"]

    stable_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert stable_source_response.status_code == 200, stable_source_response.json()
    stable_source_provenance = cast(
        dict[str, Any],
        stable_source_response.json()["packageProvenance"],
    )
    assert stable_source_provenance["workflowPackageStatus"] == "active"

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        rerun = session.get(Run, rerun_id)
        assert source_run is not None
        assert rerun is not None
        assert source_run.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot is not None
        assert source_run.workflow_package_snapshot.workflow_package_status == "active"
        assert rerun.workflow_package_snapshot.workflow_package_status is None


_recording_package_agent_calls: list[dict[str, Any]] = []


async def _recording_package_agent_invoke(
    self: AgentExecutionService,
    **kwargs: Any,
) -> RunAgentInvocationResult:
    del self
    _recording_package_agent_calls.append(dict(kwargs))
    return RunAgentInvocationResult(output={"summary": "versionless package context"}, tokens=1)


def test_workflow_package_runtime_context_does_not_emit_fake_workflow_version(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    monkeypatch.setattr(AgentExecutionService, "invoke", _recording_package_agent_invoke)
    _recording_package_agent_calls.clear()
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="versionless_context_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert len(_recording_package_agent_calls) == 1
    assert _recording_package_agent_calls[0]["workflow_key"] == "runtime_workflow"
    assert _recording_package_agent_calls[0]["workflow_version"] is None
    assert _recording_package_agent_calls[0]["package_ownership"] is not None


def test_rerun_uses_run_snapshot_after_current_package_mutation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="mutated_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="MSFT")
    source_run_id = int(launched["id"])
    source_detail_response = client.get(f"/api/runs/{source_run_id}")
    assert source_detail_response.status_code == 200, source_detail_response.json()
    source_provenance = cast(dict[str, Any], source_detail_response.json()["packageProvenance"])
    snapshot_compiled_plan = deepcopy(source_provenance["compiledPlan"])
    snapshot_compiled_hash = str(source_provenance["workflowPackageCompiledHash"])

    with session_factory() as session:
        package_row = session.get(WorkflowPackage, package_id)
        assert package_row is not None
        package_row.manifest_hash = "c" * 64
        package_row.compiled_hash = "d" * 64
        package_row.compiled_plan = {"packageKey": "mutated_snapshot_package", "workflows": []}
        session.commit()

    rerun_response = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])

    removed_target_version_field = "target" + "Version"
    assert removed_target_version_field not in rerun_response.json()
    assert removed_target_version_field not in rerun_detail_response.json()
    by_snapshot_model = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_snapshot_model.status_code == 200, by_snapshot_model.json()
    assert [item["id"] for item in by_snapshot_model.json()["items"]] == [
        rerun_id,
        source_run_id,
    ]

    assert rerun_provenance["compiledPlan"] == snapshot_compiled_plan
    assert rerun_provenance["workflowPackageCompiledHash"] == snapshot_compiled_hash
    assert rerun_provenance["launchSnapshot"]["parameters"] == {"ticker": "AAPL"}
    assert rerun_provenance["currentPackage"]["available"] is True
    assert "status" not in rerun_provenance["currentPackage"]
    assert rerun_provenance["currentPackage"]["manifestHashMatchesSnapshot"] is False
    assert rerun_provenance["currentPackage"]["compiledHashMatchesSnapshot"] is False

    with session_factory() as session:
        rerun = session.get(Run, rerun_id)
        assert rerun is not None
        assert rerun.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot.compiled_plan == snapshot_compiled_plan
        assert rerun.workflow_package_snapshot.launch_parameters == {"ticker": "AAPL"}


def test_package_deletion_deletes_owned_runs_and_agent_memory_reports(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package deletion output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_owned_runs_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(
        dict[str, Any],
        succeeded_detail["steps"][0]["invocations"][0],
    )
    source_invocation_id = int(source_invocation["id"])
    assert source_invocation["resolvedInput"] == {"ticker": "NVDA"}

    fork_response = client.post(
        f"/api/runs/{run_id}/forks",
        json={
            "sourceInvocationId": source_invocation_id,
            "invocationInput": {"ticker": "TSLA"},
        },
    )
    assert fork_response.status_code == 201, fork_response.json()
    fork_id = int(fork_response.json()["id"])
    memory_slugs = {
        run_id: f"agent_memory_deleted_owned_run_{run_id}",
        fork_id: f"agent_memory_deleted_owned_run_{fork_id}",
    }

    with session_factory() as session:
        source_run = session.get(Run, run_id)
        fork_run = session.get(Run, fork_id)
        assert source_run is not None
        assert fork_run is not None
        assert source_run.workflow_package_id == package_id
        assert fork_run.workflow_package_id == package_id
        assert session.query(RunStep).filter_by(run_id=run_id).count() > 0
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() > 0
        fork_run.status = "running"
        for owned_run_id, slug in memory_slugs.items():
            session.add(
                Report(
                    name=f"Agent Memory Deleted Owned Run {owned_run_id}",
                    slug=slug,
                    source="agent",
                    content="# Agent memory",
                    metadata_={
                        "analysis": {"reviewType": "agent_memory", "runId": owned_run_id},
                    },
                )
            )
        session.commit()

    deleted = client.delete(f"/api/workflow-packages/{package_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{fork_id}").status_code == 404

    with session_factory() as session:
        assert session.get(WorkflowPackage, package_id) is None
        assert session.get(Run, run_id) is None
        assert session.get(Run, fork_id) is None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is None
        assert session.get(RunWorkflowPackageSnapshot, fork_id) is None
        assert session.query(RunStep).filter(RunStep.run_id.in_([run_id, fork_id])).count() == 0
        assert (
            session.query(RunAgentInvocation)
            .filter(RunAgentInvocation.run_id.in_([run_id, fork_id]))
            .count()
            == 0
        )
        assert session.query(Report).filter(Report.slug.in_(memory_slugs.values())).count() == 0


def test_deleted_model_connection_preserves_run_detail_but_blocks_replay(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "deleted connection source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_connection_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], succeeded_detail["steps"][0]["invocations"][0])
    source_invocation_id = int(source_invocation["id"])

    with session_factory() as session:
        package_row = session.get(WorkflowPackage, package_id)
        assert package_row is not None
        package_row.compiled_plan = {"agents": [], "workflows": []}
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection_id = connection.id
        session.commit()

    deleted_connection = client.delete(f"/api/model-connections/{connection_id}")
    assert deleted_connection.status_code == 204, deleted_connection.text

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert provenance["resolvedModelConnections"][0]["key"] == "package_runtime_model"

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None
        runs_before = session.query(Run).count()

    _assert_replay_model_connection_rejected(
        client,
        run_id=run_id,
        source_invocation_id=source_invocation_id,
        expected_code="run_model_connection_missing",
        expected_detail_field="modelConnection",
    )

    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def test_rerun_and_fork_reject_incompatible_live_model_connection_before_queueing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "incompatible source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="incompatible_connection_snapshot_package")
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], succeeded_detail["steps"][0]["invocations"][0])
    source_invocation_id = int(source_invocation["id"])

    with session_factory() as session:
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-incompatible.example.com/v1"
        session.commit()
        runs_before = session.query(Run).count()

    _assert_replay_model_connection_rejected(
        client,
        run_id=run_id,
        source_invocation_id=source_invocation_id,
        expected_code="run_model_connection_incompatible",
        expected_detail_field="modelConnection.baseUrl",
    )

    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def _create_tradingagents_package(client: TestClient) -> dict[str, Any]:
    return _seeded_tradingagents_package(client)


def _tradingagents_parameters() -> dict[str, object]:
    return {
        "ticker": "MSFT",
        "asOfDate": "2026-05-15",
        "portfolioId": "portfolio-1",
        "horizonDays": 30,
        "benchmarkSymbol": "SPY",
    }


def test_seeded_tradingagents_advisory_manifest_exports_after_startup(
    client: TestClient,
) -> None:
    package = _seeded_tradingagents_package(client)

    response = client.get(f"/api/workflow-packages/{package['id']}/manifest")

    assert response.status_code == 200, response.json()
    manifest = cast(dict[str, Any], response.json())
    assert_removed_contract_tokens_absent(manifest, context="seeded manifest hydration")
    assert manifest["packageId"] == package["id"]
    assert manifest["packageKey"] == _TRADINGAGENTS_PRESET_KEY
    assert _TRADINGAGENTS_PRESET_KEY in manifest["manifestSource"]
    assert manifest["packageDefinition"]["metadata"]["key"] == _TRADINGAGENTS_PRESET_KEY

    exported = client.get(f"/api/workflow-packages/{package['id']}/export")
    assert exported.status_code == 200, exported.text
    assert_removed_contract_tokens_absent(exported.text, context="seeded manifest export")


def _mcp_only_package_source(package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: MCP Dependency Snapshot Fixture
spec:
  inputs:
    type: object
  capabilityProfiles: []
  outputSchemas:
    - key: mcp_output
      name: MCP Output
      jsonSchema:
        type: object
  mcpServers:
    - key: exa
      name: Exa Web Search
      transport: http-sse
      url: https://mcp.exa.ai/mcp?tools=web_search_exa
      toolKeys: [web_search_exa]
  agents:
    - key: mcp_agent
      name: MCP Agent
      modelConnection: tradingagents_primary_model
      systemPrompt: Use package-private MCP search and return JSON.
      inputSchema:
        type: object
      outputSchema: mcp_output
      capabilityProfiles: []
      mcpServers: [exa]
  workflows:
    - key: mcp_flow
      name: MCP Flow
      inputSchema:
        type: object
      flow:
        kind: step
        id: mcp_step
        slot: result
        uses: mcp_agent
        with: {{}}
      output:
        from: ${{{{ nodes.mcp_step.outputs.result }}}}
"""


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
    surfaces = set(cast(list[str], dependencies[0]["surfaces"]))
    assert {
        "hook.workflowPackageStart",
        "provider.quote",
        "provider.socialSentiment",
        "runtime.tool.signaldeck.market_data.quote_lookup",
        "tool.signaldeck.market_data.quote_lookup",
    } <= surfaces
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        assert package_row.extension_dependencies == dependencies


def test_run_dependency_snapshot_is_copied_from_current_package(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        frozen_dependencies = deepcopy(package_row.extension_dependencies)
        compiled_plan = deepcopy(package_row.compiled_plan)
        for profile in cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"]):
            profile["toolKeys"] = []
        package_row.compiled_plan = compiled_plan
        session.commit()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json()["extensionDependencies"] == frozen_dependencies

    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        package_row.extension_dependencies = []
        session.commit()

    stable_detail_response = client.get(f"/api/runs/{run_id}")
    assert stable_detail_response.status_code == 200, stable_detail_response.json()
    assert stable_detail_response.json()["extensionDependencies"] == frozen_dependencies


def test_package_private_mcp_dependency_snapshot_blocks_disabled_extension_runtime(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_tradingagents_model_connection(session_factory)
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _mcp_only_package_source("mcp_dependency_package")},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={"workflowKey": "mcp_flow", "parameters": {}},
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    queued_detail = client.get(f"/api/runs/{run_id}")
    assert queued_detail.status_code == 200, queued_detail.json()
    dependency = cast(list[dict[str, object]], queued_detail.json()["extensionDependencies"])[0]
    surfaces = set(cast(list[str], dependency["surfaces"]))
    assert "mcp.packagePrivate.web_search_exa" in surfaces
    assert "tool.signaldeck.market_data.quote_lookup" not in surfaces

    _disable_finance_extension(session_factory)
    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)

    failed_detail = client.get(f"/api/runs/{run_id}")
    assert failed_detail.status_code == 200, failed_detail.json()
    assert failed_detail.json()["status"] == "failed"
    assert failed_detail.json()["error"] == "Extension is disabled"


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
    assert detail["status"] == "failed"
    assert detail["error"] == "Extension is disabled"
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
