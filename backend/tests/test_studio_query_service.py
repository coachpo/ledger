from __future__ import annotations

from collections.abc import Mapping

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.schemas.runtime import RuntimeCallerType, RuntimeTraceEventType
from app.services.studio_query_service import StudioQueryService


def _build_workflow_run(
    *,
    caller_type: str,
    caller_id: int | None,
    caller_scope_key: str | None,
    caller_identity_key: str | None,
    workflow_spec_key: str,
    attempt_number: int,
    status: str,
    input_hash_seed: str,
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
        caller_identity_key=caller_identity_key,
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
    final_output: object | None,
    prompt_seed: str,
    persona_profile_key: str,
    capability_key: str,
    capability_display_name: str,
    source_handle: str,
) -> RuntimeRunArtifact:
    return RuntimeRunArtifact(
        run_id=run_id,
        entry_prompt_hash=prompt_seed * 64,
        full_user_prompt_hash=(prompt_seed.upper()) * 64,
        authored_entry_prompt_body="Review the current setup.",
        compiled_entry_prompt_body="Compiled review prompt.",
        execution_context_body="Studio execution context.",
        prompt_report_slug=f"prompt-{run_id}",
        raw_mention_handles=[source_handle, "analyst"],
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
                "originalText": "@analyst",
                "sourceHandle": "analyst",
                "canonicalTargetId": "character:analyst",
                "targetType": "character",
                "mentionOrder": 1,
                "personaProfileKey": "imported.character.analyst",
                "personaProfileVersion": 4,
                "legacyRoleId": 8,
                "legacyRoleVersion": 3,
                "legacyCharacterId": 13,
                "legacyCharacterVersion": 6,
            },
        ],
        mentioned_target_outputs=[
            {
                "handle": source_handle,
                "canonical_target_id": f"builtin:{source_handle}",
                "target_type": "builtin",
                "output_markdown": "Mention output",
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
        report_markdown="# Studio Artifact",
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
        resolved_bundle_versions=[{"bundleKey": "bundle.research", "revision": 2}],
        resolved_tool_versions=[],
        resolved_connector_versions=[{"connectorId": capability_key, "revision": 3}],
        resolved_workflow_agent_refs=[
            {
                "stepKey": "analysis",
                "agentSpecKey": "studio_agent",
                "agentSpecVersion": 2,
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
                        "capabilityVersion": 3,
                        "capabilityType": "connector",
                        "selectionSource": "step_config",
                        "effectiveApprovalMode": "required",
                        "effectiveConfig": {"channel": "quotes"},
                    }
                ],
            }
        ],
        resolved_capabilities=[
            {
                "capabilityKey": capability_key,
                "capabilityVersion": 3,
                "capabilityType": "connector",
                "approvalMode": "required",
                "displayName": capability_display_name,
                "transport": "mcp",
                "lifecycle": "approved",
                "effectiveConfig": {"channel": "quotes"},
            }
        ],
        final_output=final_output,
        terminal_error_code=None,
        terminal_error_message=None,
    )


def test_studio_query_service_and_routes_use_canonical_run_summaries_and_filters(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    studio_trace_summary = {
        "eventCount": 41,
        "toolCallCount": 17,
        "warningCount": 3,
        "lastEventAt": None,
    }
    studio_approval_summary = {
        "totalCount": 5,
        "pendingCount": 2,
        "approvedCount": 1,
        "deniedCount": 1,
        "expiredCount": 1,
    }

    with session_factory() as session:
        studio_run = _build_workflow_run(
            caller_type="studio",
            caller_id=None,
            caller_scope_key="studio-session-a",
            caller_identity_key="studio-user-1",
            workflow_spec_key="alpha_workflow",
            attempt_number=1,
            status="WAITING_APPROVAL",
            input_hash_seed="a",
            trace_summary=studio_trace_summary,
            approval_summary=studio_approval_summary,
        )
        api_run = _build_workflow_run(
            caller_type="api",
            caller_id=77,
            caller_scope_key="api-scope-77",
            caller_identity_key="runtime-user-77",
            workflow_spec_key="alpha_workflow",
            attempt_number=1,
            status="SUCCEEDED",
            input_hash_seed="b",
            trace_summary={
                "eventCount": 9,
                "toolCallCount": 2,
                "warningCount": 0,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 1,
                "pendingCount": 0,
                "approvedCount": 1,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        unrelated_run = _build_workflow_run(
            caller_type="api",
            caller_id=88,
            caller_scope_key="api-scope-88",
            caller_identity_key="runtime-user-88",
            workflow_spec_key="beta_workflow",
            attempt_number=1,
            status="FAILED",
            input_hash_seed="c",
            trace_summary={
                "eventCount": 2,
                "toolCallCount": 0,
                "warningCount": 1,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 0,
                "pendingCount": 0,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        session.add_all([studio_run, api_run, unrelated_run])
        session.flush()

        studio_approval = RuntimeApproval(
            run_id=studio_run.id,
            step_key="analysis",
            capability_key="connector.market_data",
            status="PENDING",
        )
        session.add_all(
            [
                _build_artifact(
                    run_id=studio_run.id,
                    final_output=None,
                    prompt_seed="d",
                    persona_profile_key="persona.alpha",
                    capability_key="connector.market_data",
                    capability_display_name="Market Data Connector",
                    source_handle="librarian",
                ),
                _build_artifact(
                    run_id=api_run.id,
                    final_output={"status": "done"},
                    prompt_seed="e",
                    persona_profile_key="persona.beta",
                    capability_key="tool.screeners",
                    capability_display_name="Screeners Tool",
                    source_handle="explore",
                ),
                _build_artifact(
                    run_id=unrelated_run.id,
                    final_output=None,
                    prompt_seed="f",
                    persona_profile_key="persona.gamma",
                    capability_key="connector.company_filings",
                    capability_display_name="Company Filings Connector",
                    source_handle="librarian",
                ),
                studio_approval,
                RuntimeTraceEvent(
                    run_id=studio_run.id,
                    event_index=0,
                    event_type="RUN_CREATED",
                    payload={"stage": "created"},
                ),
                RuntimeTraceEvent(
                    run_id=studio_run.id,
                    event_index=1,
                    event_type="TOOL_CALLED",
                    step_key="analysis",
                    capability_key="connector.market_data",
                    payload={"tool": "market-data"},
                ),
                RuntimeTraceEvent(
                    run_id=api_run.id,
                    event_index=0,
                    event_type="RUN_COMPLETED",
                    payload={"status": "SUCCEEDED"},
                ),
            ]
        )
        session.commit()

        service = StudioQueryService(session)
        studio_run_read = service.get_run(studio_run.id)
        studio_artifact_read = service.get_artifact(studio_run.id)
        persona_filtered = service.list_artifacts(persona_profile_key="persona.alpha")
        capability_filtered = service.list_artifacts(capability_key="connector.market_data")
        approval_detail = service.get_approval(studio_approval.id)
        trace_filtered = service.list_trace_events(
            workflow_spec_key="alpha_workflow",
            capability_key="connector.market_data",
            event_type=RuntimeTraceEventType.TOOL_CALLED,
        )

        assert studio_run_read.trace_summary.model_dump(by_alias=True) == studio_trace_summary
        assert studio_run_read.approval_summary.model_dump(by_alias=True) == studio_approval_summary
        assert studio_run_read.pending_approval_ids == [studio_approval.id]
        assert studio_artifact_read.trace_summary.model_dump(by_alias=True) == studio_trace_summary
        assert (
            studio_artifact_read.approval_summary.model_dump(by_alias=True)
            == studio_approval_summary
        )
        assert studio_artifact_read.resolved_mentions[0].source_handle == "librarian"
        assert studio_artifact_read.resolved_workflow_agent_refs is not None
        assert studio_artifact_read.resolved_workflow_agent_refs[0].step_key == "analysis"
        assert studio_artifact_read.resolved_capabilities[0].display_name == "Market Data Connector"
        assert [item.run_id for item in persona_filtered.items] == [studio_run.id]
        assert [item.run_id for item in capability_filtered.items] == [studio_run.id]
        assert approval_detail.summary.model_dump(by_alias=True) == {
            "approvalMode": "required",
            "displayName": "Market Data Connector",
            "transport": "mcp",
        }
        assert approval_detail.allowed_actions == ["approve", "deny"]
        assert len(trace_filtered.items) == 1
        assert trace_filtered.items[0].event_index == 1
        assert trace_filtered.items[0].payload == {"tool": "market-data"}

    run_response = client.get(f"/api/v2/studio/runs/{studio_run.id}")
    assert run_response.status_code == 200, run_response.json()
    assert run_response.json()["traceSummary"] == studio_trace_summary
    assert run_response.json()["approvalSummary"] == studio_approval_summary
    assert run_response.json()["pendingApprovalIds"] == [studio_approval.id]

    artifact_response = client.get(f"/api/v2/studio/runs/{studio_run.id}/artifacts")
    assert artifact_response.status_code == 200, artifact_response.json()
    assert artifact_response.json()["traceSummary"] == studio_trace_summary
    assert artifact_response.json()["approvalSummary"] == studio_approval_summary
    assert artifact_response.json()["resolvedMentions"][0]["sourceHandle"] == "librarian"
    assert (
        artifact_response.json()["resolvedCapabilities"][0]["displayName"]
        == "Market Data Connector"
    )

    list_response = client.get(
        "/api/v2/studio/artifacts",
        params={"personaProfileKey": "persona.alpha", "capabilityKey": "connector.market_data"},
    )
    assert list_response.status_code == 200, list_response.json()
    assert [item["runId"] for item in list_response.json()["items"]] == [studio_run.id]
    assert list_response.json()["items"][0]["traceSummary"] == studio_trace_summary
    assert list_response.json()["items"][0]["approvalSummary"] == studio_approval_summary

    approvals_response = client.get(
        "/api/v2/studio/approvals",
        params={
            "callerType": RuntimeCallerType.STUDIO.value,
            "workflowSpecKey": "alpha_workflow",
            "capabilityKey": "connector.market_data",
            "status": "PENDING",
        },
    )
    assert approvals_response.status_code == 200, approvals_response.json()
    assert approvals_response.json()["items"] == [
        {
            "approvalId": studio_approval.id,
            "runId": studio_run.id,
            "status": "PENDING",
            "capabilityKey": "connector.market_data",
            "stepKey": "analysis",
            "callerType": "studio",
            "callerId": None,
            "createdAt": approvals_response.json()["items"][0]["createdAt"],
        }
    ]

    approval_response = client.get(f"/api/v2/studio/approvals/{studio_approval.id}")
    assert approval_response.status_code == 200, approval_response.json()
    assert approval_response.json()["summary"] == {
        "approvalMode": "required",
        "displayName": "Market Data Connector",
        "transport": "mcp",
    }
    assert approval_response.json()["allowedActions"] == ["approve", "deny"]

    trace_response = client.get(
        "/api/v2/studio/trace-events",
        params={
            "callerType": RuntimeCallerType.STUDIO.value,
            "workflowSpecKey": "alpha_workflow",
            "capabilityKey": "connector.market_data",
            "eventType": RuntimeTraceEventType.TOOL_CALLED.value,
        },
    )
    assert trace_response.status_code == 200, trace_response.json()
    assert trace_response.json()["items"] == [
        {
            "runId": studio_run.id,
            "eventIndex": 1,
            "eventType": "TOOL_CALLED",
            "stepKey": "analysis",
            "capabilityKey": "connector.market_data",
            "callerType": "studio",
            "callerId": None,
            "createdAt": trace_response.json()["items"][0]["createdAt"],
            "approvalId": None,
            "payload": {"tool": "market-data"},
        }
    ]
