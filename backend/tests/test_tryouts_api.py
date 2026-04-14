from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.models.agent_spec import AgentSpec
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_checkpoint import RuntimeCheckpoint
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent


def _build_agent_spec(*, key: str, version: int = 1, status: str = "ACTIVE") -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        instructions=f"Instructions for {key}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_tryout_run(
    *,
    status: str = "QUEUED",
    retention_class: str = "ephemeral",
    expires_at=None,
    trace_summary: dict[str, Any] | None = None,
    approval_summary: dict[str, Any] | None = None,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type="tryout",
        caller_id=None,
        execution_kind="single_agent",
        workflow_spec_key=None,
        workflow_spec_version=None,
        agent_spec_key="tryout_api_agent",
        agent_spec_version=1,
        caller_scope_key=None,
        caller_identity_key=None,
        attempt_number=1,
        status=status,
        input_hash="1" * 64,
        output_hash=None,
        retention_class=retention_class,
        expires_at=expires_at,
        trace_summary=trace_summary
        or {
            "eventCount": 1,
            "toolCallCount": 0,
            "warningCount": 0,
            "lastEventAt": None,
        },
        approval_summary=approval_summary
        or {
            "totalCount": 0,
            "pendingCount": 0,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 0,
        },
    )


def _build_artifact(
    *,
    run_id: int,
    final_output: Any | None = None,
    report_markdown: str | None = None,
) -> RuntimeRunArtifact:
    return RuntimeRunArtifact(
        run_id=run_id,
        entry_prompt_hash="a" * 64,
        full_user_prompt_hash="b" * 64,
        raw_mention_handles=[],
        resolved_persona_profile_refs=[],
        resolved_builtin_versions=[],
        resolved_role_versions=[],
        resolved_character_versions=[],
        resolved_bundle_versions=[],
        resolved_tool_versions=[],
        resolved_connector_versions=[],
        mentioned_target_outputs=[],
        resolved_mentions=[],
        resolved_workflow_agent_refs=None,
        resolved_capabilities=[],
        final_output=final_output,
        report_markdown=report_markdown,
        terminal_error_code=None,
        terminal_error_message=None,
    )


def _runtime_row_counts(session: Session) -> tuple[int, int, int]:
    return (
        int(session.scalar(select(func.count()).select_from(RuntimeRun)) or 0),
        int(session.scalar(select(func.count()).select_from(RuntimeRunArtifact)) or 0),
        int(session.scalar(select(func.count()).select_from(RuntimeTraceEvent)) or 0),
    )


def test_tryout_create_read_and_persist_flow(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_build_agent_spec(key="tryout_api_agent"))
        session.commit()

    before = utcnow()
    create_response = client.post(
        "/api/v2/tryouts",
        json={
            "agentSpecKey": "tryout_api_agent",
            "inputs": {"ticker": "MSFT"},
        },
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()
    assert set(created) == {"runId", "status", "expiresAt"}
    assert created["status"] == "SUCCEEDED"
    assert created["expiresAt"] is not None

    detail_response = client.get(f"/api/v2/tryouts/{created['runId']}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert detail["runId"] == created["runId"]
    assert detail["status"] == "SUCCEEDED"
    assert detail["finalOutput"] == {
        "executionKind": "single_agent",
        "agent": {"key": "tryout_api_agent", "version": 1, "name": "tryout_api_agent-1"},
        "inputs": {"ticker": "MSFT"},
        "personaProfileKeys": [],
        "capabilities": [],
        "summary": "Executed tryout_api_agent-1 from frozen pinned refs.",
    }
    assert detail["reportMarkdown"] == (
        "# Single-Agent Execution\n\n"
        "- Agent: tryout_api_agent-1 (tryout_api_agent v1)\n"
        "- Personas: none\n"
        "- Capabilities: none\n"
        "- Summary: Executed tryout_api_agent-1 from frozen pinned refs."
    )
    assert detail["traceSummary"] == {
        "eventCount": 4,
        "toolCallCount": 0,
        "warningCount": 0,
        "lastEventAt": detail["traceSummary"]["lastEventAt"],
    }
    assert detail["approvalSummary"] == {
        "totalCount": 0,
        "pendingCount": 0,
        "approvedCount": 0,
        "deniedCount": 0,
        "expiredCount": 0,
    }
    assert detail["expiresAt"] == created["expiresAt"]

    with session_factory() as session:
        run = session.get(RuntimeRun, created["runId"])
        assert run is not None
        assert run.retention_class == "ephemeral"
        assert run.expires_at is not None
        assert (
            timedelta(hours=23, minutes=59)
            <= run.expires_at - before
            <= timedelta(hours=24, minutes=1)
        )

    persist_response = client.post(f"/api/v2/tryouts/{created['runId']}/persist")
    assert persist_response.status_code == 200, persist_response.json()
    persisted = persist_response.json()
    assert persisted["runId"] == created["runId"]
    assert persisted["status"] == "SUCCEEDED"
    assert persisted["expiresAt"] is None

    refreshed_response = client.get(f"/api/v2/tryouts/{created['runId']}")
    assert refreshed_response.status_code == 200, refreshed_response.json()
    assert refreshed_response.json()["expiresAt"] is None


def test_tryout_persist_waiting_approval_keeps_same_run_id_and_attached_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_tryout_run(
            status="WAITING_APPROVAL",
            expires_at=utcnow() + timedelta(hours=24),
            approval_summary={
                "totalCount": 1,
                "pendingCount": 1,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                _build_artifact(run_id=run.id),
                RuntimeApproval(
                    run_id=run.id,
                    step_key="review",
                    capability_key="ledger.review",
                    status="PENDING",
                ),
                RuntimeCheckpoint(
                    run_id=run.id,
                    checkpoint_index=0,
                    step_key="review",
                    serialized_state={"cursor": "approval"},
                ),
            ]
        )
        session.commit()
        run_id = run.id

    response = client.post(f"/api/v2/tryouts/{run_id}/persist")
    assert response.status_code == 200, response.json()
    persisted = response.json()
    assert persisted["runId"] == run_id
    assert persisted["status"] == "WAITING_APPROVAL"
    assert persisted["approvalSummary"]["pendingCount"] == 1
    assert persisted["expiresAt"] is None

    with session_factory() as session:
        run = session.get(RuntimeRun, run_id)
        assert run is not None
        assert run.retention_class == "persistent"
        assert run.expires_at is None
        assert (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(RuntimeApproval)
                    .where(RuntimeApproval.run_id == run_id)
                )
                or 0
            )
            == 1
        )
        assert (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(RuntimeCheckpoint)
                    .where(RuntimeCheckpoint.run_id == run_id)
                )
                or 0
            )
            == 1
        )


def test_tryout_create_rejects_seeded_backtest_workflow_without_runtime_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        assert _runtime_row_counts(session) == (0, 0, 0)

    response = client.post(
        "/api/v2/tryouts",
        json={
            "workflowSpecKey": "seeded_internal_backtest_v1",
            "inputs": {"ticker": "AAPL"},
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "tryout_seeded_backtest_workflow_not_allowed"

    with session_factory() as session:
        assert _runtime_row_counts(session) == (0, 0, 0)


def test_tryout_persist_is_idempotent(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_build_agent_spec(key="tryout_api_agent"))
        session.commit()

    create_response = client.post(
        "/api/v2/tryouts",
        json={
            "agentSpecKey": "tryout_api_agent",
            "inputs": {"ticker": "NVDA"},
        },
    )
    assert create_response.status_code == 201, create_response.json()
    run_id = create_response.json()["runId"]

    first = client.post(f"/api/v2/tryouts/{run_id}/persist")
    second = client.post(f"/api/v2/tryouts/{run_id}/persist")
    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    assert first.json()["runId"] == run_id
    assert second.json()["runId"] == run_id
    assert first.json()["expiresAt"] is None
    assert second.json()["expiresAt"] is None

    with session_factory() as session:
        persisted = session.get(RuntimeRun, run_id)
        assert persisted is not None
        assert persisted.retention_class == "persistent"
        assert persisted.expires_at is None
        assert int(session.scalar(select(func.count()).select_from(RuntimeRun)) or 0) == 1
