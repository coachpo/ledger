from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent_spec import AgentSpec
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.workflow_spec import WorkflowSpec
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.schemas.runtime import RuntimeCallerType
from app.services.agent_runtime_service import AgentRuntimeService


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


def _build_runtime_run(
    *,
    caller_type: str,
    caller_id: int | None,
    caller_scope_key: str | None,
    attempt_number: int,
    status: str,
    input_hash_seed: str,
    caller_identity_key: str | None = None,
    agent_spec_key: str = "runtime_api_agent",
    trace_summary: dict[str, Any] | None = None,
    approval_summary: dict[str, Any] | None = None,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type=caller_type,
        caller_id=caller_id,
        execution_kind="single_agent",
        workflow_spec_key=None,
        workflow_spec_version=None,
        agent_spec_key=agent_spec_key,
        agent_spec_version=1,
        caller_scope_key=caller_scope_key,
        caller_identity_key=caller_identity_key,
        attempt_number=attempt_number,
        status=status,
        input_hash=input_hash_seed * 64,
        output_hash=None,
        retention_class="persistent",
        trace_summary=trace_summary
        or {
            "eventCount": 0,
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
    terminal_error_code: str | None = None,
    terminal_error_message: str | None = None,
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
        terminal_error_code=terminal_error_code,
        terminal_error_message=terminal_error_message,
    )


def _build_workflow_spec(*, key: str, version: int = 1, origin: str, status: str) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin=origin,
        status=status,
        name=f"{key}-{version}",
        graph_definition={
            "entryStepKey": "analysis",
            "steps": [{"stepKey": "analysis", "agentSpecKey": "position_analyst"}],
        },
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        mention_policy={"version": 1, "allowCharacterPersonas": True, "allowedBuiltinHandles": []},
        execution_mode="structured_output",
        default_tool_ids=[],
        allowed_capability_bundle_keys=[],
        connector_ids=[],
        review_mode=None,
        approval_policy_overrides=[],
    )


def test_runtime_create_returns_minimal_contract_and_rejects_reserved_public_caller_types(
    client: TestClient,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    dispatched_run_ids: list[int] = []

    monkeypatch.setattr(
        AgentRuntimeService,
        "_dispatch_prepared_run_in_background",
        lambda self, prepared: dispatched_run_ids.append(prepared.run_id),
    )

    with session_factory() as session:
        session.add(_build_agent_spec(key="runtime_api_agent"))
        session.commit()

    response = client.post(
        "/api/v2/runtime/runs",
        json={
            "callerType": "api",
            "callerId": 9,
            "callerScopeKey": "adhoc-runtime-create",
            "executionKind": "single_agent",
            "agentSpecKey": "runtime_api_agent",
            "inputs": {"ticker": "MSFT"},
        },
    )
    assert response.status_code == 201, response.json()
    created = response.json()
    assert set(created) == {"runId", "status", "expiresAt"}
    assert created["status"] == "QUEUED"
    assert created["expiresAt"] is None
    assert dispatched_run_ids == [created["runId"]]

    detail_response = client.get(f"/api/v2/runtime/runs/{created['runId']}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json()["status"] == "QUEUED"
    assert detail_response.json()["finalOutput"] is None
    assert detail_response.json()["traceSummary"] == {
        "eventCount": 1,
        "toolCallCount": 0,
        "warningCount": 0,
        "lastEventAt": detail_response.json()["traceSummary"]["lastEventAt"],
    }
    assert detail_response.json()["approvalSummary"] == {
        "totalCount": 0,
        "pendingCount": 0,
        "approvedCount": 0,
        "deniedCount": 0,
        "expiredCount": 0,
    }

    for caller_type, caller_id, caller_scope_key in [
        ("tryout", None, None),
        ("studio", None, "studio-session"),
    ]:
        invalid_response = client.post(
            "/api/v2/runtime/runs",
            json={
                "callerType": caller_type,
                "callerId": caller_id,
                "callerScopeKey": caller_scope_key,
                "executionKind": "single_agent",
                "agentSpecKey": "runtime_api_agent",
                "inputs": {"ticker": "AAPL"},
            },
        )
        assert invalid_response.status_code == 400, invalid_response.json()
        assert invalid_response.json()["code"] == "runtime_public_caller_type_not_allowed"


def test_runtime_create_rejects_pinned_archived_workflow_specs(
    client: TestClient,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    dispatched_run_ids: list[int] = []

    monkeypatch.setattr(
        AgentRuntimeService,
        "_dispatch_prepared_run_in_background",
        lambda self, prepared: dispatched_run_ids.append(prepared.run_id),
    )

    with session_factory() as session:
        session.add(
            _build_workflow_spec(
                key="archived_runtime_workflow",
                origin="seeded",
                status="ARCHIVED",
            )
        )
        session.commit()

    response = client.post(
        "/api/v2/runtime/runs",
        json={
            "callerType": "api",
            "callerId": 9,
            "callerScopeKey": "adhoc-runtime-create",
            "executionKind": "workflow",
            "workflowSpecKey": "archived_runtime_workflow",
            "workflowSpecVersion": 1,
            "inputs": {"ticker": "MSFT"},
        },
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "runtime_public_workflow_not_active"
    assert dispatched_run_ids == []


def test_runtime_and_studio_run_reads_reuse_canonical_run_models_and_filtered_lists(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        api_run = _build_runtime_run(
            caller_type="api",
            caller_id=101,
            caller_scope_key="alpha",
            attempt_number=1,
            status="SUCCEEDED",
            input_hash_seed="1",
            trace_summary={
                "eventCount": 4,
                "toolCallCount": 1,
                "warningCount": 0,
                "lastEventAt": None,
            },
        )
        studio_run = _build_runtime_run(
            caller_type="studio",
            caller_id=None,
            caller_scope_key="studio-session",
            attempt_number=1,
            status="FAILED",
            input_hash_seed="2",
            caller_identity_key="studio-user-1",
            trace_summary={
                "eventCount": 3,
                "toolCallCount": 0,
                "warningCount": 1,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 1,
                "pendingCount": 1,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        other_run = _build_runtime_run(
            caller_type="api",
            caller_id=202,
            caller_scope_key="beta",
            attempt_number=1,
            status="QUEUED",
            input_hash_seed="3",
        )
        session.add_all([api_run, studio_run, other_run])
        session.flush()
        session.add_all(
            [
                _build_artifact(run_id=api_run.id, final_output={"message": "done"}),
                _build_artifact(
                    run_id=studio_run.id,
                    terminal_error_code="adapter_failure",
                    terminal_error_message="Execution failed",
                ),
                _build_artifact(run_id=other_run.id),
                RuntimeApproval(
                    run_id=studio_run.id,
                    step_key="review",
                    capability_key="ledger.review",
                    status="PENDING",
                ),
            ]
        )
        session.commit()
        studio_run_id = studio_run.id

    with session_factory() as session:
        service = AgentRuntimeService(session)
        expected_runtime_list = service.list_runs(
            caller_type=cast(Any, RuntimeCallerType.API),
            caller_id=101,
        ).model_dump(mode="json", by_alias=True)
        expected_studio_list = service.list_runs(
            caller_scope_key="studio-session",
        ).model_dump(mode="json", by_alias=True)
        expected_detail = service.get_run(studio_run_id).model_dump(mode="json", by_alias=True)

    runtime_list_response = client.get(
        "/api/v2/runtime/runs",
        params={"callerType": "api", "callerId": 101},
    )
    assert runtime_list_response.status_code == 200, runtime_list_response.json()
    assert runtime_list_response.json() == expected_runtime_list

    studio_list_response = client.get(
        "/api/v2/studio/runs",
        params={"callerScopeKey": "studio-session"},
    )
    assert studio_list_response.status_code == 200, studio_list_response.json()
    assert studio_list_response.json() == expected_studio_list

    runtime_detail_response = client.get(f"/api/v2/runtime/runs/{studio_run_id}")
    assert runtime_detail_response.status_code == 200, runtime_detail_response.json()
    assert runtime_detail_response.json() == expected_detail
    assert runtime_detail_response.json()["terminalError"] == {
        "code": "adapter_failure",
        "message": "Execution failed",
    }
    assert "terminalErrorCode" not in runtime_detail_response.json()
    assert "terminalErrorMessage" not in runtime_detail_response.json()

    studio_detail_response = client.get(f"/api/v2/studio/runs/{studio_run_id}")
    assert studio_detail_response.status_code == 200, studio_detail_response.json()
    assert studio_detail_response.json() == expected_detail


def test_runtime_cancel_marks_waiting_approval_run_cancelled_and_expires_pending_approvals(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_runtime_run(
            caller_type="api",
            caller_id=303,
            caller_scope_key="cancel-me",
            attempt_number=1,
            status="WAITING_APPROVAL",
            input_hash_seed="4",
            trace_summary={
                "eventCount": 2,
                "toolCallCount": 0,
                "warningCount": 0,
                "lastEventAt": None,
            },
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
        approval = RuntimeApproval(
            run_id=run.id,
            step_key="review",
            capability_key="ledger.market_data",
            status="PENDING",
        )
        session.add_all([approval, _build_artifact(run_id=run.id)])
        session.commit()
        run_id = run.id
        approval_id = approval.id

    cancel_response = client.post(f"/api/v2/runtime/runs/{run_id}/cancel")
    assert cancel_response.status_code == 200, cancel_response.json()
    assert cancel_response.json() == {
        "runId": run_id,
        "status": "CANCELLED",
        "approvalSummary": {
            "totalCount": 1,
            "pendingCount": 0,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 1,
        },
    }

    with session_factory() as session:
        approval_row = session.get(RuntimeApproval, approval_id)
        assert approval_row is not None
        assert approval_row.status == "EXPIRED"
        assert approval_row.actor is None
        assert approval_row.reason == "Run cancelled before approval resolution"

        detail = AgentRuntimeService(session).get_run(run_id).model_dump(mode="json", by_alias=True)
        assert detail["status"] == "CANCELLED"
        assert detail["pendingApprovalIds"] == []
        assert detail["approvalSummary"]["expiredCount"] == 1

        trace_events = RuntimeTraceEventRepository(session).list_for_run(run_id)
        assert [event.event_type for event in trace_events[-2:]] == [
            "APPROVAL_RESOLVED",
            "RUN_CANCELLED",
        ]
