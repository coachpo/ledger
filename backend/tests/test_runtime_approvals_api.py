from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.services.agent_runtime_service import AgentRuntimeService


def _build_runtime_run(
    *,
    status: str,
    approval_summary: dict[str, Any] | None = None,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type="api",
        caller_id=404,
        execution_kind="single_agent",
        workflow_spec_key=None,
        workflow_spec_version=None,
        agent_spec_key="approval_agent",
        agent_spec_version=1,
        caller_scope_key="approval-run",
        caller_identity_key=None,
        attempt_number=1,
        status=status,
        input_hash="4" * 64,
        output_hash=None,
        retention_class="persistent",
        trace_summary={
            "eventCount": 2,
            "toolCallCount": 0,
            "warningCount": 0,
            "lastEventAt": None,
        },
        approval_summary=approval_summary
        or {
            "totalCount": 1,
            "pendingCount": 1,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 0,
        },
    )


def _build_artifact(run_id: int) -> RuntimeRunArtifact:
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
    )


def _build_agent_spec(
    *,
    key: str,
    default_capability_bundle_keys: list[str] | None = None,
) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=1,
        origin="managed",
        status="ACTIVE",
        name=f"{key}-1",
        instructions=f"Instructions for {key}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=list(default_capability_bundle_keys or []),
        default_persona_profile_keys=[],
    )


def _build_connector_entry(*, key: str) -> CapabilityRegistryEntry:
    return CapabilityRegistryEntry(
        key=key,
        version=1,
        origin="managed",
        status="ACTIVE",
        type="connector",
        display_name=f"{key}-1",
        description="Connector capability",
        approval_mode="required",
        adapter_key=key,
        config_schema={"type": "object"},
        transport="mcp",
        lifecycle="approved",
    )


def test_runtime_approval_approve_returns_resolution_metadata_only_and_requires_run_poll(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_connector_entry(key="connector.review"),
                _build_agent_spec(
                    key="approval_agent",
                    default_capability_bundle_keys=["connector.review"],
                ),
            ]
        )
        session.commit()

    create_response = client.post(
        "/api/v2/runtime/runs",
        json={
            "callerType": "api",
            "callerId": 404,
            "callerScopeKey": "approval-run",
            "executionKind": "single_agent",
            "agentSpecKey": "approval_agent",
            "inputs": {"ticker": "MSFT"},
        },
    )
    assert create_response.status_code == 201, create_response.json()
    assert create_response.json()["status"] in {"QUEUED", "RUNNING", "WAITING_APPROVAL"}
    run_id = int(create_response.json()["runId"])

    approval_id: int | None = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and approval_id is None:
        detail_response = client.get(f"/api/v2/runtime/runs/{run_id}")
        assert detail_response.status_code == 200, detail_response.json()
        pending_approval_ids = detail_response.json()["pendingApprovalIds"]
        if detail_response.json()["status"] == "WAITING_APPROVAL" and pending_approval_ids:
            approval_id = int(pending_approval_ids[0])
            break
        time.sleep(0.05)

    assert approval_id is not None

    with session_factory() as session:
        persisted_approval_id = session.scalar(
            select(RuntimeApproval.id).where(RuntimeApproval.run_id == run_id)
        )
        assert persisted_approval_id == approval_id

    response = client.post(
        f"/api/v2/runtime/approvals/{approval_id}/approve",
        json={"actor": "reviewer", "reason": "Looks good"},
    )
    assert response.status_code == 200, response.json()
    assert set(response.json()) == {"approvalId", "status", "runId", "resolvedAt", "runStatus"}
    assert response.json()["approvalId"] == approval_id
    assert response.json()["status"] == "APPROVED"
    assert response.json()["runId"] == run_id
    assert response.json()["runStatus"] == "SUCCEEDED"
    assert "finalOutput" not in response.json()
    assert "terminalError" not in response.json()

    with session_factory() as session:
        approval_row = session.get(RuntimeApproval, approval_id)
        assert approval_row is not None
        assert approval_row.status == "APPROVED"
        assert approval_row.actor == "reviewer"
        assert approval_row.reason == "Looks good"
        assert approval_row.resolved_at is not None

        expected_detail = (
            AgentRuntimeService(session)
            .get_run(run_id)
            .model_dump(
                mode="json",
                by_alias=True,
            )
        )

    detail_response = client.get(f"/api/v2/runtime/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json() == expected_detail
    assert detail_response.json()["status"] == "SUCCEEDED"
    assert detail_response.json()["approvalSummary"] == {
        "totalCount": 1,
        "pendingCount": 0,
        "approvedCount": 1,
        "deniedCount": 0,
        "expiredCount": 0,
    }
    assert detail_response.json()["finalOutput"]["executionKind"] == "single_agent"


def test_runtime_approval_deny_returns_resolution_metadata_and_rejects_repeat_resolution(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_runtime_run(status="WAITING_APPROVAL")
        session.add(run)
        session.flush()
        approval = RuntimeApproval(
            run_id=run.id,
            step_key="review",
            capability_key="ledger.connector.market_data",
            status="PENDING",
        )
        session.add_all([approval, _build_artifact(run.id)])
        session.commit()
        run_id = run.id
        approval_id = approval.id

    deny_response = client.post(
        f"/api/v2/runtime/approvals/{approval_id}/deny",
        json={"actor": "reviewer", "reason": "Denied for safety"},
    )
    assert deny_response.status_code == 200, deny_response.json()
    assert set(deny_response.json()) == {"approvalId", "status", "runId", "resolvedAt", "runStatus"}
    assert deny_response.json()["status"] == "DENIED"
    assert deny_response.json()["runStatus"] == "FAILED"
    assert "finalOutput" not in deny_response.json()

    with session_factory() as session:
        expected_detail = (
            AgentRuntimeService(session)
            .get_run(run_id)
            .model_dump(
                mode="json",
                by_alias=True,
            )
        )

    detail_response = client.get(f"/api/v2/runtime/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json() == expected_detail
    assert detail_response.json()["terminalError"] == {
        "code": "approval_denied",
        "message": "Approval denied for capability ledger.connector.market_data",
    }
    assert "terminalErrorCode" not in detail_response.json()

    repeat_response = client.post(
        f"/api/v2/runtime/approvals/{approval_id}/deny",
        json={"actor": "reviewer", "reason": "Still denied"},
    )
    assert repeat_response.status_code == 400, repeat_response.json()
    assert repeat_response.json()["code"] == "runtime_approval_not_pending"
