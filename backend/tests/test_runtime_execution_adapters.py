from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.agent_spec import AgentSpec
from app.models.workflow_spec import WorkflowSpec
from app.schemas.runtime import (
    ApprovalMode,
    ApprovalSummary,
    CapabilityRef,
    CapabilityType,
    PersonaProfileKind,
    PersonaProfileRef,
    ResolvedCapabilityRead,
    RuntimeCheckpointRead,
    SpecOrigin,
    TraceSummary,
    WorkflowAgentRef,
)
from app.services.execution_adapters import (
    ExecutionAdapterRequest,
    ExecutionApprovalState,
    FrozenExecutionSnapshot,
    GenericWorkflowExecutionAdapter,
    SingleAgentExecutionAdapter,
)


def _build_agent_spec(
    *,
    key: str,
    version: int,
    name: str | None = None,
    status: str = "ACTIVE",
) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=name or f"{key} v{version}",
        instructions=f"Instructions for {key} v{version}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_workflow_spec(
    *,
    key: str,
    version: int,
    graph_definition: dict[str, Any],
    execution_mode: str | None = None,
) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin="managed",
        status="ACTIVE",
        name=f"{key} v{version}",
        graph_definition=graph_definition,
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        mention_policy={"version": 1, "allow_characters": False, "allowed_builtin_handles": []},
        execution_mode=execution_mode,
        default_tool_ids=[],
        allowed_capability_bundle_keys=[],
        connector_ids=[],
        review_mode=None,
        approval_policy_overrides=[],
    )


def _persona_ref(key: str, version: int = 1) -> PersonaProfileRef:
    return PersonaProfileRef(
        persona_profile_key=key,
        persona_profile_version=version,
        canonical_target_id=f"persona:{key}",
        persona_kind=cast(Any, PersonaProfileKind.MANAGED_PERSONA),
        origin=cast(Any, SpecOrigin.MANAGED),
        selection_source="test",
    )


def _capability_ref(
    key: str,
    *,
    version: int = 1,
    capability_type: CapabilityType | str,
    approval_mode: ApprovalMode | str,
    selection_source: str = "test",
) -> CapabilityRef:
    return CapabilityRef(
        capability_key=key,
        capability_version=version,
        capability_type=_normalize_capability_type(capability_type),
        selection_source=selection_source,
        effective_approval_mode=_normalize_approval_mode(approval_mode),
        effective_config={},
    )


def _resolved_capability(
    key: str,
    *,
    version: int = 1,
    capability_type: CapabilityType | str,
    approval_mode: ApprovalMode | str,
    transport: str | None = None,
) -> ResolvedCapabilityRead:
    return ResolvedCapabilityRead(
        capability_key=key,
        capability_version=version,
        capability_type=_normalize_capability_type(capability_type),
        approval_mode=_normalize_approval_mode(approval_mode),
        transport=transport,
        lifecycle=None,
        effective_config={},
    )


def _normalize_capability_type(value: CapabilityType | str) -> CapabilityType:
    if isinstance(value, CapabilityType):
        return value
    return CapabilityType(value)


def _normalize_approval_mode(value: ApprovalMode | str) -> ApprovalMode:
    if isinstance(value, ApprovalMode):
        return value
    return ApprovalMode(value)


def _workflow_step(
    step_key: str,
    agent_key: str,
    *,
    agent_version: int = 1,
    capability_refs: list[CapabilityRef] | None = None,
    persona_refs: list[PersonaProfileRef] | None = None,
) -> WorkflowAgentRef:
    return WorkflowAgentRef(
        step_key=step_key,
        agent_spec_key=agent_key,
        agent_spec_version=agent_version,
        persona_profile_refs=list(persona_refs or []),
        capability_refs=list(capability_refs or []),
    )


def _trace_summary(event_count: int = 0) -> TraceSummary:
    return TraceSummary(
        event_count=event_count,
        tool_call_count=0,
        warning_count=0,
        last_event_at=None,
    )


def _approval_summary(
    *,
    total_count: int = 0,
    pending_count: int = 0,
    approved_count: int = 0,
    denied_count: int = 0,
    expired_count: int = 0,
) -> ApprovalSummary:
    return ApprovalSummary(
        total_count=total_count,
        pending_count=pending_count,
        approved_count=approved_count,
        denied_count=denied_count,
        expired_count=expired_count,
    )


def _checkpoint(step_key: str, state: dict[str, Any]) -> RuntimeCheckpointRead:
    now = datetime(2026, 4, 13, tzinfo=UTC)
    return RuntimeCheckpointRead.model_validate(
        {
            "checkpointId": 1,
            "runId": 1,
            "checkpointIndex": 0,
            "stepKey": step_key,
            "serializedState": state,
            "createdAt": now,
            "updatedAt": now,
        }
    )


def _approved_approval(step_key: str, capability_key: str) -> ExecutionApprovalState:
    return ExecutionApprovalState(
        approval_id=1,
        step_key=step_key,
        capability_key=capability_key,
        status="APPROVED",
        actor="tester",
        reason="approved",
        resolved_at=datetime(2026, 4, 13, tzinfo=UTC),
    )


def _request(
    snapshot: FrozenExecutionSnapshot,
    *,
    dispatch_mode: str = "start",
    caller_type: str = "api",
    caller_id: int | None = 99,
    caller_scope_key: str | None = "scope-1",
    approvals: tuple[ExecutionApprovalState, ...] = (),
    checkpoints: tuple[RuntimeCheckpointRead, ...] = (),
    current_checkpoint: RuntimeCheckpointRead | None = None,
    approval_summary: ApprovalSummary | None = None,
) -> ExecutionAdapterRequest:
    return ExecutionAdapterRequest(
        dispatch_mode=cast(Any, dispatch_mode),
        run_id=1,
        attempt_number=1,
        caller_type=caller_type,
        caller_id=caller_id,
        caller_scope_key=caller_scope_key,
        caller_identity_key=None,
        snapshot=snapshot,
        trace_summary=_trace_summary(),
        approval_summary=approval_summary or _approval_summary(),
        checkpoints=checkpoints,
        current_checkpoint=current_checkpoint,
        approvals=approvals,
    )


def test_generic_workflow_adapter_executes_from_frozen_step_plan_only(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(
                    key="analysis_agent",
                    version=1,
                    name="Analysis Agent v1",
                    status="DEPRECATED",
                ),
                _build_agent_spec(
                    key="analysis_agent",
                    version=2,
                    name="Analysis Agent v2",
                    status="ACTIVE",
                ),
                _build_agent_spec(
                    key="review_agent",
                    version=1,
                    name="Review Agent v1",
                    status="DEPRECATED",
                ),
                _build_agent_spec(
                    key="review_agent",
                    version=2,
                    name="Review Agent v2",
                    status="ACTIVE",
                ),
                _build_workflow_spec(
                    key="native_workflow",
                    version=1,
                    graph_definition={
                        "entryStepKey": "analysis",
                        "steps": [
                            {
                                "stepKey": "analysis",
                                "agentSpecKey": "analysis_agent",
                                "agentSpecVersion": 1,
                            },
                            {
                                "stepKey": "review",
                                "agentSpecKey": "review_agent",
                                "agentSpecVersion": 1,
                            },
                        ],
                        "edges": [
                            {
                                "fromStepKey": "analysis",
                                "outcome": "success",
                                "toStepKey": "review",
                            },
                            {"fromStepKey": "review", "outcome": "success", "toStepKey": "END"},
                        ],
                    },
                ),
            ]
        )
        session.commit()

        adapter = GenericWorkflowExecutionAdapter(session)
        snapshot = FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key="native_workflow",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs={"topic": "AAPL"},
            resolved_workflow_agent_refs=(
                _workflow_step(
                    "analysis",
                    "analysis_agent",
                    agent_version=1,
                    capability_refs=[
                        _capability_ref(
                            "tool.analysis",
                            capability_type=CapabilityType.TOOL,
                            approval_mode=ApprovalMode.NOT_REQUIRED,
                        )
                    ],
                    persona_refs=[_persona_ref("persona.alpha")],
                ),
                _workflow_step(
                    "review",
                    "review_agent",
                    agent_version=1,
                    capability_refs=[
                        _capability_ref(
                            "tool.review",
                            capability_type=CapabilityType.TOOL,
                            approval_mode=ApprovalMode.NOT_REQUIRED,
                        )
                    ],
                ),
            ),
            resolved_persona_profile_refs=(_persona_ref("persona.alpha"),),
            resolved_capabilities=(
                _resolved_capability(
                    "tool.analysis",
                    capability_type=CapabilityType.TOOL,
                    approval_mode=ApprovalMode.NOT_REQUIRED,
                ),
                _resolved_capability(
                    "tool.review",
                    capability_type=CapabilityType.TOOL,
                    approval_mode=ApprovalMode.NOT_REQUIRED,
                ),
            ),
        )

        result = adapter.execute(_request(snapshot))

        assert result.status == "SUCCEEDED"
        assert result.artifact_patch is not None
        assert result.artifact_patch.final_output == {
            "executionKind": "workflow",
            "workflow": {"key": "native_workflow", "version": 1},
            "inputs": {"topic": "AAPL"},
            "steps": [
                {
                    "stepKey": "analysis",
                    "agentSpecKey": "analysis_agent",
                    "agentSpecVersion": 1,
                    "agentName": "Analysis Agent v1",
                    "personaProfileKeys": ["persona.alpha"],
                    "capabilities": [
                        {
                            "capabilityKey": "tool.analysis",
                            "capabilityVersion": 1,
                            "capabilityType": "tool",
                        }
                    ],
                    "summary": "Executed Analysis Agent v1 using the frozen step plan.",
                },
                {
                    "stepKey": "review",
                    "agentSpecKey": "review_agent",
                    "agentSpecVersion": 1,
                    "agentName": "Review Agent v1",
                    "personaProfileKeys": [],
                    "capabilities": [
                        {
                            "capabilityKey": "tool.review",
                            "capabilityVersion": 1,
                            "capabilityType": "tool",
                        }
                    ],
                    "summary": "Executed Review Agent v1 using the frozen step plan.",
                },
            ],
        }
        assert result.trace_events[0].step_key == "analysis"
        assert result.trace_events[-1].step_key == "review"
        assert result.artifact_patch.report_markdown is not None
        assert "Workflow: native_workflow v1" in result.artifact_patch.report_markdown


def test_generic_workflow_adapter_fails_closed_on_frozen_plan_drift(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(key="analysis_agent", version=1),
                _build_workflow_spec(
                    key="drift_workflow",
                    version=1,
                    graph_definition={
                        "entryStepKey": "analysis",
                        "steps": [
                            {
                                "stepKey": "analysis",
                                "agentSpecKey": "analysis_agent",
                                "agentSpecVersion": 1,
                            }
                        ],
                    },
                ),
            ]
        )
        session.commit()
        workflow = session.query(WorkflowSpec).filter_by(key="drift_workflow", version=1).one()
        workflow.graph_definition = {
            "entryStepKey": "analysis",
            "steps": [
                {
                    "stepKey": "analysis",
                    "agentSpecKey": "other_agent",
                    "agentSpecVersion": 1,
                }
            ],
        }
        session.commit()

        adapter = GenericWorkflowExecutionAdapter(session)
        snapshot = FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key="drift_workflow",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs={},
            resolved_workflow_agent_refs=(
                _workflow_step("analysis", "analysis_agent", agent_version=1),
            ),
        )

        with pytest.raises(ApiError, match="workflow metadata now points to") as exc_info:
            adapter.execute(_request(snapshot))

        assert exc_info.value.code == "runtime_frozen_workflow_plan_drift"


def test_generic_workflow_adapter_rejects_widened_capability_usage(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(key="analysis_agent", version=1),
                _build_workflow_spec(
                    key="capability_drift_workflow",
                    version=1,
                    graph_definition={
                        "entryStepKey": "analysis",
                        "steps": [
                            {
                                "stepKey": "analysis",
                                "agentSpecKey": "analysis_agent",
                                "agentSpecVersion": 1,
                            }
                        ],
                    },
                ),
            ]
        )
        session.commit()

        adapter = GenericWorkflowExecutionAdapter(session)
        snapshot = FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key="capability_drift_workflow",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs={},
            resolved_workflow_agent_refs=(
                _workflow_step(
                    "analysis",
                    "analysis_agent",
                    capability_refs=[
                        _capability_ref(
                            "tool.extra",
                            capability_type=CapabilityType.TOOL,
                            approval_mode=ApprovalMode.NOT_REQUIRED,
                        )
                    ],
                ),
            ),
            resolved_capabilities=(),
        )

        with pytest.raises(
            ApiError, match="outside the flattened frozen capability set"
        ) as exc_info:
            adapter.execute(_request(snapshot))

        assert exc_info.value.code == "runtime_widened_capability_usage"


def test_single_agent_adapter_waits_for_approval_and_uses_pinned_agent_version(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(
                    key="solo_agent",
                    version=1,
                    name="Solo Agent v1",
                    status="DEPRECATED",
                ),
                _build_agent_spec(
                    key="solo_agent",
                    version=2,
                    name="Solo Agent v2",
                    status="ACTIVE",
                ),
            ]
        )
        session.commit()

        adapter = SingleAgentExecutionAdapter(session)
        snapshot = FrozenExecutionSnapshot(
            execution_kind="single_agent",
            workflow_spec_key=None,
            workflow_spec_version=None,
            agent_spec_key="solo_agent",
            agent_spec_version=1,
            inputs={"task": "Summarize portfolio"},
            resolved_persona_profile_refs=(_persona_ref("persona.solo"),),
            resolved_capabilities=(
                _resolved_capability(
                    "connector.market",
                    capability_type=CapabilityType.CONNECTOR,
                    approval_mode=ApprovalMode.REQUIRED,
                    transport="mcp",
                ),
            ),
        )

        waiting = adapter.execute(_request(snapshot, caller_id=None, caller_scope_key=None))

        assert waiting.status == "WAITING_APPROVAL"
        assert waiting.approval_requests[0].step_key == "solo_agent"
        assert waiting.approval_requests[0].capability_key == "connector.market"
        checkpoint = _checkpoint(
            waiting.checkpoints[0].step_key,
            waiting.checkpoints[0].serialized_state,
        )
        resumed = adapter.execute(
            _request(
                snapshot,
                dispatch_mode="resume",
                caller_id=None,
                caller_scope_key=None,
                approvals=(_approved_approval("solo_agent", "connector.market"),),
                checkpoints=(checkpoint,),
                current_checkpoint=checkpoint,
                approval_summary=_approval_summary(total_count=1, approved_count=1),
            )
        )

        assert resumed.status == "SUCCEEDED"
        assert resumed.artifact_patch is not None
        assert resumed.artifact_patch.final_output == {
            "executionKind": "single_agent",
            "agent": {"key": "solo_agent", "version": 1, "name": "Solo Agent v1"},
            "inputs": {"task": "Summarize portfolio"},
            "personaProfileKeys": ["persona.solo"],
            "capabilities": [
                {
                    "capabilityKey": "connector.market",
                    "capabilityVersion": 1,
                    "capabilityType": "connector",
                }
            ],
            "summary": "Executed Solo Agent v1 from frozen pinned refs.",
        }
        assert resumed.artifact_patch.report_markdown is not None
        assert "Solo Agent v1" in resumed.artifact_patch.report_markdown
