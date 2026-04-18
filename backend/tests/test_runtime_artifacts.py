from __future__ import annotations

from collections.abc import Mapping

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.tryout_service import TryoutService


def _build_workflow_run(
    *,
    caller_type: str,
    caller_id: int | None,
    caller_scope_key: str | None,
    attempt_number: int,
    status: str,
    input_hash_seed: str,
    workflow_spec_key: str,
    trace_summary: Mapping[str, object],
    approval_summary: Mapping[str, object],
) -> RuntimeRun:
    return RuntimeRun(
        caller_type=caller_type,
        caller_id=caller_id,
        execution_kind="workflow",
        workflow_spec_key=workflow_spec_key,
        workflow_spec_version=1,
        agent_spec_key=None,
        agent_spec_version=None,
        caller_scope_key=caller_scope_key,
        caller_identity_key=None,
        attempt_number=attempt_number,
        status=status,
        input_hash=input_hash_seed * 64,
        output_hash=None,
        retention_class="persistent",
        expires_at=None,
        trace_summary=dict(trace_summary),
        approval_summary=dict(approval_summary),
    )


def _build_artifact(
    *,
    run_id: int,
    prompt_seed: str,
    persona_profile_key: str,
    capability_key: str,
    capability_display_name: str,
    source_handle: str,
    final_output: object | None,
    terminal_error_code: str | None,
    terminal_error_message: str | None,
) -> RuntimeRunArtifact:
    return RuntimeRunArtifact(
        run_id=run_id,
        entry_prompt_hash=prompt_seed * 64,
        full_user_prompt_hash=(prompt_seed.upper()) * 64,
        authored_entry_prompt_body="Authored entry prompt.",
        compiled_entry_prompt_body="Compiled entry prompt.",
        execution_context_body="Execution context body.",
        prompt_report_slug=f"prompt-{run_id}",
        raw_mention_handles=[source_handle, "risk_team"],
        resolved_mentions=[
            {
                "originalText": f"@{source_handle}",
                "sourceHandle": source_handle,
                "canonicalTargetId": f"builtin:{source_handle}",
                "targetType": "builtin",
                "mentionOrder": 0,
                "personaProfileKey": f"builtin.{source_handle}",
                "personaProfileVersion": 1,
            },
            {
                "originalText": "@risk_team",
                "sourceHandle": "risk_team",
                "canonicalTargetId": "character:risk_team",
                "targetType": "character",
                "mentionOrder": 1,
                "personaProfileKey": "imported.character.risk_team",
                "personaProfileVersion": 5,
                "legacyRoleId": 3,
                "legacyRoleVersion": 4,
                "legacyCharacterId": 7,
                "legacyCharacterVersion": 8,
            },
        ],
        mentioned_target_outputs=[
            {
                "handle": source_handle,
                "canonical_target_id": f"builtin:{source_handle}",
                "target_type": "builtin",
                "output_markdown": "Artifact mention output",
            }
        ],
        resolved_persona_profile_refs=[
            {
                "personaProfileKey": persona_profile_key,
                "personaProfileVersion": 2,
                "canonicalTargetId": f"persona:{persona_profile_key}",
                "personaKind": "managed_persona",
                "origin": "managed",
                "selectionSource": "workflow_default",
            }
        ],
        report_markdown="# Runtime Artifact",
        normalized_trade_decisions=None,
        resolved_builtin_versions=[
            {
                "canonicalTargetId": f"builtin:{source_handle}",
                "handle": source_handle,
                "revision": 1,
            }
        ],
        resolved_role_versions=[],
        resolved_character_versions=[],
        resolved_bundle_versions=[{"bundleKey": "bundle.runtime", "revision": 2}],
        resolved_tool_versions=[],
        resolved_connector_versions=[{"connectorId": capability_key, "revision": 4}],
        resolved_workflow_agent_refs=[
            {
                "stepKey": "analysis",
                "agentSpecKey": "runtime_agent",
                "agentSpecVersion": 3,
                "personaProfileRefs": [
                    {
                        "personaProfileKey": persona_profile_key,
                        "personaProfileVersion": 2,
                        "canonicalTargetId": f"persona:{persona_profile_key}",
                        "personaKind": "managed_persona",
                        "origin": "managed",
                        "selectionSource": "step_config",
                    }
                ],
                "capabilityRefs": [
                    {
                        "capabilityKey": capability_key,
                        "capabilityVersion": 4,
                        "capabilityType": "connector",
                        "selectionSource": "step_config",
                        "effectiveApprovalMode": "required",
                        "effectiveConfig": {"scope": "runtime"},
                    }
                ],
            }
        ],
        resolved_capabilities=[
            {
                "capabilityKey": capability_key,
                "capabilityVersion": 4,
                "capabilityType": "connector",
                "approvalMode": "required",
                "displayName": capability_display_name,
                "transport": "mcp",
                "lifecycle": "approved",
                "effectiveConfig": {"scope": "runtime"},
            }
        ],
        final_output=final_output,
        terminal_error_code=terminal_error_code,
        terminal_error_message=terminal_error_message,
    )


def test_runtime_artifact_and_tryout_reads_share_canonical_runtime_run_summaries(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    trace_summary = {
        "eventCount": 13,
        "toolCallCount": 5,
        "warningCount": 2,
        "lastEventAt": None,
    }
    approval_summary = {
        "totalCount": 4,
        "pendingCount": 1,
        "approvedCount": 1,
        "deniedCount": 1,
        "expiredCount": 1,
    }

    with session_factory() as session:
        run = _build_workflow_run(
            caller_type="tryout",
            caller_id=None,
            caller_scope_key=None,
            attempt_number=1,
            status="WAITING_APPROVAL",
            input_hash_seed="g",
            workflow_spec_key="tryout_workflow",
            trace_summary=trace_summary,
            approval_summary=approval_summary,
        )
        session.add(run)
        session.flush()

        approval = RuntimeApproval(
            run_id=run.id,
            step_key="analysis",
            capability_key="connector.tryout_review",
            status="PENDING",
        )
        session.add_all(
            [
                _build_artifact(
                    run_id=run.id,
                    prompt_seed="h",
                    persona_profile_key="persona.tryout",
                    capability_key="connector.tryout_review",
                    capability_display_name="Tryout Review Connector",
                    source_handle="librarian",
                    final_output=None,
                    terminal_error_code=None,
                    terminal_error_message=None,
                ),
                approval,
            ]
        )
        session.flush()
        session.add_all(
            [
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=0,
                    event_type="RUN_CREATED",
                    payload={"stage": "created"},
                ),
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=1,
                    event_type="APPROVAL_REQUESTED",
                    step_key="analysis",
                    capability_key="connector.tryout_review",
                    approval_id=approval.id,
                    payload={"approvalId": approval.id, "status": "PENDING"},
                ),
            ]
        )
        session.commit()

        runtime_service = AgentRuntimeService(session)
        tryout_service = TryoutService(session)
        run_read = runtime_service.get_run(run.id)
        artifact_read = runtime_service.get_artifact(run.id)
        tryout_read = tryout_service.get_tryout(run.id)

        assert run_read.trace_summary.model_dump(by_alias=True) == trace_summary
        assert run_read.approval_summary.model_dump(by_alias=True) == approval_summary
        assert artifact_read.trace_summary.model_dump(by_alias=True) == trace_summary
        assert artifact_read.approval_summary.model_dump(by_alias=True) == approval_summary
        assert tryout_read.trace_summary.model_dump(by_alias=True) == trace_summary
        assert tryout_read.approval_summary.model_dump(by_alias=True) == approval_summary
        assert artifact_read.resolved_mentions[0].source_handle == "librarian"
        assert artifact_read.resolved_workflow_agent_refs is not None
        assert artifact_read.resolved_workflow_agent_refs[0].step_key == "analysis"
        assert artifact_read.resolved_capabilities[0].display_name == "Tryout Review Connector"

    runtime_run_response = client.get(f"/api/v2/runtime/runs/{run.id}")
    assert runtime_run_response.status_code == 200, runtime_run_response.json()
    assert runtime_run_response.json()["traceSummary"] == trace_summary
    assert runtime_run_response.json()["approvalSummary"] == approval_summary

    runtime_artifact_response = client.get(f"/api/v2/runtime/runs/{run.id}/artifacts")
    assert runtime_artifact_response.status_code == 200, runtime_artifact_response.json()
    assert runtime_artifact_response.json()["traceSummary"] == trace_summary
    assert runtime_artifact_response.json()["approvalSummary"] == approval_summary
    assert runtime_artifact_response.json()["resolvedMentions"][0]["sourceHandle"] == "librarian"
    assert runtime_artifact_response.json()["resolvedWorkflowAgentRefs"][0]["stepKey"] == "analysis"
    assert (
        runtime_artifact_response.json()["resolvedCapabilities"][0]["displayName"]
        == "Tryout Review Connector"
    )

    tryout_response = client.get(f"/api/v2/tryouts/{run.id}")
    assert tryout_response.status_code == 200, tryout_response.json()
    assert tryout_response.json()["traceSummary"] == trace_summary
    assert tryout_response.json()["approvalSummary"] == approval_summary

    approvals_response = client.get(
        "/api/v2/runtime/approvals",
        params={
            "runId": run.id,
            "capabilityKey": "connector.tryout_review",
            "status": "PENDING",
        },
    )
    assert approvals_response.status_code == 200, approvals_response.json()
    assert approvals_response.json()["items"] == [
        {
            "approvalId": approval.id,
            "runId": run.id,
            "status": "PENDING",
            "capabilityKey": "connector.tryout_review",
            "stepKey": "analysis",
            "callerType": "tryout",
            "callerId": None,
            "createdAt": approvals_response.json()["items"][0]["createdAt"],
        }
    ]

    trace_events_response = client.get(
        "/api/v2/runtime/trace-events",
        params={
            "runId": run.id,
            "capabilityKey": "connector.tryout_review",
            "eventType": "APPROVAL_REQUESTED",
        },
    )
    assert trace_events_response.status_code == 200, trace_events_response.json()
    assert trace_events_response.json()["items"] == [
        {
            "runId": run.id,
            "eventIndex": 1,
            "eventType": "APPROVAL_REQUESTED",
            "stepKey": "analysis",
            "capabilityKey": "connector.tryout_review",
            "callerType": "tryout",
            "callerId": None,
            "createdAt": trace_events_response.json()["items"][0]["createdAt"],
            "approvalId": approval.id,
            "payload": {"approvalId": approval.id, "status": "PENDING"},
        }
    ]


def test_runtime_artifact_reads_stay_native_in_multi_attempt_history_for_studio_callers(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    cycle_scope_key = "2026-04-13"
    caller_id = 4242

    with session_factory() as session:
        first_run = _build_workflow_run(
            caller_type="studio",
            caller_id=caller_id,
            caller_scope_key=cycle_scope_key,
            attempt_number=1,
            status="FAILED",
            input_hash_seed="i",
            workflow_spec_key="alpha_workflow",
            trace_summary={
                "eventCount": 7,
                "toolCallCount": 2,
                "warningCount": 1,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 1,
                "pendingCount": 0,
                "approvedCount": 0,
                "deniedCount": 1,
                "expiredCount": 0,
            },
        )
        second_run = _build_workflow_run(
            caller_type="studio",
            caller_id=caller_id,
            caller_scope_key=cycle_scope_key,
            attempt_number=2,
            status="SUCCEEDED",
            input_hash_seed="j",
            workflow_spec_key="alpha_workflow",
            trace_summary={
                "eventCount": 19,
                "toolCallCount": 6,
                "warningCount": 0,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 2,
                "pendingCount": 0,
                "approvedCount": 2,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        session.add_all([first_run, second_run])
        session.flush()

        session.add_all(
            [
                _build_artifact(
                    run_id=first_run.id,
                    prompt_seed="k",
                    persona_profile_key="persona.backtest.first",
                    capability_key="connector.market_data",
                    capability_display_name="Attempt One Connector",
                    source_handle="legacy_review",
                    final_output=None,
                    terminal_error_code="approval_denied",
                    terminal_error_message="Attempt one denied",
                ),
                _build_artifact(
                    run_id=second_run.id,
                    prompt_seed="l",
                    persona_profile_key="persona.backtest.second",
                    capability_key="connector.market_data",
                    capability_display_name="Attempt Two Connector",
                    source_handle="researcher",
                    final_output={"attempt": "two", "result": "buy"},
                    terminal_error_code=None,
                    terminal_error_message=None,
                ),
            ]
        )
        session.commit()

        service = AgentRuntimeService(session)
        first_artifact = service.get_artifact(first_run.id)
        second_artifact = service.get_artifact(second_run.id)

        assert first_artifact.model_dump(mode="json", by_alias=True)["terminalError"] == {
            "code": "approval_denied",
            "message": "Attempt one denied",
        }
        assert second_artifact.final_output == {"attempt": "two", "result": "buy"}
        assert second_artifact.resolved_mentions[0].source_handle == "researcher"
        assert second_artifact.resolved_capabilities[0].display_name == "Attempt Two Connector"
        assert second_artifact.resolved_workflow_agent_refs is not None
        assert second_artifact.resolved_workflow_agent_refs[0].step_key == "analysis"

    first_response = client.get(f"/api/v2/runtime/runs/{first_run.id}/artifacts")
    assert first_response.status_code == 200, first_response.json()
    assert first_response.json()["terminalError"] == {
        "code": "approval_denied",
        "message": "Attempt one denied",
    }

    second_response = client.get(f"/api/v2/runtime/runs/{second_run.id}/artifacts")
    assert second_response.status_code == 200, second_response.json()
    assert second_response.json()["finalOutput"] == {"attempt": "two", "result": "buy"}
    assert second_response.json()["traceSummary"] == {
        "eventCount": 19,
        "toolCallCount": 6,
        "warningCount": 0,
        "lastEventAt": None,
    }
    assert second_response.json()["approvalSummary"] == {
        "totalCount": 2,
        "pendingCount": 0,
        "approvedCount": 2,
        "deniedCount": 0,
        "expiredCount": 0,
    }
    assert second_response.json()["resolvedMentions"][0]["sourceHandle"] == "researcher"
    assert "handle" not in second_response.json()["resolvedMentions"][0]
    assert (
        second_response.json()["resolvedCapabilities"][0]["displayName"] == "Attempt Two Connector"
    )
    assert second_response.json()["resolvedWorkflowAgentRefs"][0]["stepKey"] == "analysis"
    assert "toolCallTrace" not in second_response.json()
    assert "approvalTrace" not in second_response.json()
    assert second_response.json()["finalOutput"] != first_response.json().get("finalOutput")
