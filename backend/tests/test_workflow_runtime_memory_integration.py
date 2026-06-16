# basedpyright: reportAny=false, reportExplicitAny=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.models.report import Report
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_memory import (
    WorkflowMemoryAuditEvent,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
)
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.services.run_queue_service import RunQueueService

_MEMORY_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "signaldeck_advisory_research_memory.yaml"
)
_OLD_MEMORY_TOOL_KEYS = {
    "signaldeck.core.memory.write",
    "signaldeck.core.memory.lookup",
}
_OLD_MEMORY_FUNCTION_NAMES = {
    "signaldeck_core_memory_write",
    "signaldeck_core_memory_lookup",
}


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
    output_text = (
        '{"summary":"memory integration output","evidence":["runtime"],'
        '"limitations":["fixture"],"memoryProposals":[]}'
    )
    total_tokens = 31

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
        cls.output_text = (
            '{"summary":"memory integration output","evidence":["runtime"],'
            '"limitations":["fixture"],"memoryProposals":[]}'
        )
        cls.total_tokens = 31


def _seed_model_connection(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                name="Memory Integration Model",
                description="Workflow memory integration model binding.",
                base_url="https://provider-runtime.example.test/v1",
                model_id="gpt-memory-integration-v1",
                reasoning_effort="high",
                api_style="responses",
                capabilities={},
                output_strategy_policy="prefer_strict_schema",
                parallel_tool_calls_policy="serialize",
                reasoning_policy="allow",
                streaming_policy="allow",
                timeout_seconds=31,
                secret_payload={"apiKey": "test-api-key"},
            )
        )
        session.commit()


def _create_memory_demo_package(client: TestClient) -> dict[str, Any]:
    manifest_source = _memory_integration_manifest_source()
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _memory_integration_manifest_source() -> str:
    manifest_source = _MEMORY_DEMO_FIXTURE.read_text()
    assert _OLD_MEMORY_TOOL_KEYS.isdisjoint(manifest_source)
    return manifest_source.replace(
        "                content:\n                  type: object",
        "                content:\n                  type: string",
        1,
    )


def _preflight_memory_demo(client: TestClient, package_id: int) -> None:
    response = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": "advisory_research", "parameters": _launch_parameters()},
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    assert _OLD_MEMORY_TOOL_KEYS.isdisjoint(str(body))


def _launch_memory_demo(client: TestClient, package_id: int) -> int:
    response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "advisory_research", "parameters": _launch_parameters()},
    )
    assert response.status_code == 201, response.json()
    return int(response.json()["id"])


def _launch_parameters() -> dict[str, str]:
    return {
        "ticker": "AAPL",
        "researchQuestion": "What changed this week?",
        "outputLanguage": "English",
    }


def _drain_run_queue(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        assert RunQueueService(session, session_factory).drain_once() is True


def _wait_for_run(client: TestClient, run_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 3.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.json()
        body = cast(dict[str, Any], response.json())
        last_body = body
        if body["status"] not in {"queued", "running"}:
            return body
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish in time: {last_body}")


def _api_tool_keys(client: TestClient) -> set[str]:
    response = client.get("/api/tools")
    assert response.status_code == 200, response.json()
    items = cast(list[dict[str, Any]], response.json()["items"])
    return {str(item["key"]) for item in items}


def _seed_active_memory(session_factory: sessionmaker[Session], *, content: str) -> str:
    with session_factory() as session:
        item = WorkflowMemoryRepository(session).create_memory_item(
            memory_id="mem-approved-active-context",
            package_key="signaldeck_advisory_research_memory",
            workflow_key="advisory_research",
            agent_key="advisory_researcher",
            step_id="advisory_analysis",
            namespace="advisory_research",
            kind="fact",
            content_json={"text": content},
            summary="Approved active advisory context",
            provenance_json={"source": "test-approved-memory"},
            valid_from=utcnow() - timedelta(days=1),
        )
        session.commit()
        return item.memory_id


def _first_invocation(detail: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], detail["steps"][0]["invocations"][0])


def _model_gateway_workflow_memory(detail: dict[str, Any]) -> dict[str, Any]:
    invocation = _first_invocation(detail)
    graph_metadata = cast(dict[str, Any], invocation["graphMetadata"])
    model_gateway = cast(dict[str, Any], graph_metadata["modelGateway"])
    return cast(dict[str, Any], model_gateway["workflowMemory"])


def _assert_no_old_memory_runtime_path(client: TestClient) -> None:
    assert _OLD_MEMORY_TOOL_KEYS.isdisjoint(_api_tool_keys(client))
    assert _OLD_MEMORY_FUNCTION_NAMES.isdisjoint(str(_RuntimeRecordingOpenAIClient.create_calls))


def test_memory_enabled_workflow_happy_path_projects_middleware_evidence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = (
        '{"summary":"memory integration output","evidence":["runtime"],'
        '"limitations":["fixture"],"memoryProposals":['
        '{"kind":"fact","namespace":"advisory_research",'
        '"content":"Runtime proposal should wait for review.",'
        '"reason":"observed in run"},'
        '{"kind":"fact","namespace":"advisory_research",'
        '"content":"Use sk-test_abcdefghijklmnopqrstuvwxyz123456 now.",'
        '"reason":"secret detector fixture"}]}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    active_memory_id = _seed_active_memory(
        session_factory,
        content="Approved context says AAPL prefers long-form risk notes.",
    )
    created = _create_memory_demo_package(client)
    package_id = int(created["id"])

    _preflight_memory_demo(client, package_id)
    run_id = _launch_memory_demo(client, package_id)
    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded", _first_invocation(detail)
    create_call = _RuntimeRecordingOpenAIClient.create_calls[0]
    instructions = str(create_call["instructions"])
    model_input = str(create_call["input"])
    assert "Approved context says AAPL prefers long-form risk notes." not in instructions
    assert "memoryContext" in model_input
    assert "Non-authoritative memory context" in model_input
    assert "Approved context says AAPL prefers long-form risk notes." in model_input
    assert "signaldeck.core.memory" not in model_input

    workflow_memory = _model_gateway_workflow_memory(detail)
    assert workflow_memory["contextItemIds"] == [active_memory_id]
    assert workflow_memory["checkpointIds"]
    assert workflow_memory["completion"] == {
        "proposalCount": 2,
        "decisionCount": 2,
        "rejectedCount": 0,
    }

    with session_factory() as session:
        proposals = session.query(WorkflowMemoryProposal).order_by(WorkflowMemoryProposal.id).all()
        decisions = session.query(WorkflowMemoryDecision).order_by(WorkflowMemoryDecision.id).all()
        quarantines = session.query(WorkflowMemoryQuarantine).all()
        checkpoints = session.query(WorkflowCheckpoint).order_by(WorkflowCheckpoint.sequence).all()
        active_items = session.query(WorkflowMemoryItem).all()
        audit_events = session.query(WorkflowMemoryAuditEvent).all()

    assert [proposal.status for proposal in proposals] == ["review_pending", "quarantined"]
    assert [decision.decision for decision in decisions] == ["review", "quarantine"]
    assert decisions[0].reason_code == "default_review"
    assert decisions[1].reason_code == "secret_detected"
    assert len(quarantines) == 1
    assert len(checkpoints) == 2
    assert {checkpoint.checkpoint_type for checkpoint in checkpoints} == {
        "step_begin",
        "step_finalize",
    }
    assert {item.memory_id for item in active_items} == {active_memory_id}
    assert len(audit_events) == 2

    review_pending = proposals[0]
    approve = client.post(
        f"/api/memory/proposals/{review_pending.proposal_id}/actions/approve",
        json={"reason": "Integration approval."},
    )
    assert approve.status_code == 200, approve.json()
    approved_memory_id = approve.json()["activeMemoryId"]
    projected = client.get(f"/api/runs/{run_id}")
    assert projected.status_code == 200, projected.json()
    evidence = projected.json()["workflowMemoryEvidence"]

    assert evidence["injections"][0]["contextItemIds"] == [active_memory_id]
    assert evidence["injections"][0]["checkpointIds"] == workflow_memory["checkpointIds"]
    assert evidence["injections"][0]["completion"] == workflow_memory["completion"]
    assert [proposal["status"] for proposal in evidence["proposals"]] == [
        "committed",
        "quarantined",
    ]
    assert evidence["proposals"][0]["activeMemoryIds"] == [approved_memory_id]
    assert [decision["decision"] for decision in evidence["decisions"]] == [
        "review",
        "quarantine",
        "commit",
    ]
    assert evidence["quarantines"][0]["reasonCode"] == "secret_detected"
    assert {checkpoint["checkpointType"] for checkpoint in evidence["checkpoints"]} == {
        "step_begin",
        "step_finalize",
    }
    assert {event["eventType"] for event in evidence["auditEvents"]} == {
        "memory_policy_review",
        "memory_policy_quarantine",
        "memory_review_commit",
    }
    _assert_no_old_memory_runtime_path(client)


def test_forbidden_states_not_injected_into_workflow_runtime_input(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    allowed_content = "Allowed active memory should be injected."
    allowed_memory_id = _seed_active_memory(session_factory, content=allowed_content)
    forbidden_markers = _seed_forbidden_memory_states(session_factory)
    created = _create_memory_demo_package(client)
    package_id = int(created["id"])

    _preflight_memory_demo(client, package_id)
    run_id = _launch_memory_demo(client, package_id)
    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded", _first_invocation(detail)
    model_input = str(_RuntimeRecordingOpenAIClient.create_calls[0]["input"])
    assert allowed_content in model_input
    assert _model_gateway_workflow_memory(detail)["contextItemIds"] == [allowed_memory_id]
    for marker in forbidden_markers:
        assert marker not in model_input
    with session_factory() as session:
        table_names = set(sqlalchemy_inspect(session.get_bind()).get_table_names())
    assert "agent_memory_entries" not in table_names
    assert "agent_memory_revisions" not in table_names
    assert "run_memory_events" not in table_names
    _assert_no_old_memory_runtime_path(client)


def _seed_forbidden_memory_states(session_factory: sessionmaker[Session]) -> list[str]:
    now = utcnow()
    markers = {
        "rejected": "Forbidden rejected memory must not appear.",
        "quarantined": "Forbidden quarantined memory must not appear.",
        "deleted": "Forbidden deleted memory must not appear.",
        "superseded": "Forbidden superseded memory must not appear.",
        "expired": "Forbidden expired memory must not appear.",
        "unauthorized": "Forbidden unauthorized memory must not appear.",
        "review_pending": "Forbidden review pending memory must not appear.",
        "legacy_archive": "Forbidden legacy archive memory must not appear.",
    }
    with session_factory() as session:
        repo = WorkflowMemoryRepository(session)
        rejected = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-rejected",
            content=markers["rejected"],
            policy_status="rejected",
        )
        quarantined = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-quarantined",
            content=markers["quarantined"],
        )
        _ = repo.quarantine_memory_item(
            memory_item=quarantined,
            reason_code="manual_quarantine",
            reason="Unresolved quarantine fixture.",
        )
        _ = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-deleted",
            content=markers["deleted"],
            lifecycle_status="deleted",
            deleted_at=now,
        )
        superseding = _create_memory_fixture(
            repo,
            memory_id="mem-superseding-active",
            content="Superseding active memory outside launch assertions.",
            namespace="superseding_archive",
        )
        session.flush()
        _ = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-superseded",
            content=markers["superseded"],
            lifecycle_status="superseded",
            superseded_by_id=superseding.id,
        )
        _ = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-expired",
            content=markers["expired"],
            lifecycle_status="expired",
            expires_at=now - timedelta(minutes=1),
        )
        _ = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-unauthorized",
            content=markers["unauthorized"],
            namespace="unauthorized_namespace",
        )
        _ = _create_memory_fixture(
            repo,
            memory_id="mem-forbidden-review-pending",
            content=markers["review_pending"],
            policy_status="review_pending",
        )
        session.add(
            Report(
                name="legacy_archive_memory_fixture",
                slug="legacy-archive-memory-fixture",
                source="agent",
                content=markers["legacy_archive"],
                metadata_={
                    "analysis": {
                        "reviewType": "agent_memory",
                        "versionGroup": "agent_memory/v1",
                    }
                },
            )
        )
        assert rejected.policy_status == "rejected"
        session.commit()
    return list(markers.values())


def _create_memory_fixture(
    repo: WorkflowMemoryRepository,
    *,
    memory_id: str,
    content: str,
    policy_status: str = "committed",
    lifecycle_status: str = "active",
    namespace: str = "advisory_research",
    expires_at: Any | None = None,
    deleted_at: Any | None = None,
    superseded_by_id: int | None = None,
) -> WorkflowMemoryItem:
    return repo.create_memory_item(
        memory_id=memory_id,
        package_key="signaldeck_advisory_research_memory",
        workflow_key="advisory_research",
        agent_key="advisory_researcher",
        step_id="advisory_analysis",
        namespace=namespace,
        kind="fact",
        content_json={"text": content},
        summary=content,
        provenance_json={"source": "forbidden-state-fixture"},
        policy_status=policy_status,
        lifecycle_status=lifecycle_status,
        valid_from=utcnow() - timedelta(days=1),
        expires_at=expires_at,
        deleted_at=deleted_at,
        superseded_by_id=superseded_by_id,
    )
