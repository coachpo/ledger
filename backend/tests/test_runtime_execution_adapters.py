from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.langgraph.runner import BacktestLangGraphResult, BacktestLangGraphToolRuntime
from app.models.agent_spec import AgentSpec
from app.models.workflow_spec import WorkflowSpec
from app.schemas.backtest import TradeDecision
from app.schemas.runtime import (
    ApprovalMode,
    ApprovalSummary,
    CapabilityRef,
    CapabilityType,
    PersonaProfileKind,
    PersonaProfileRef,
    ResolvedCapabilityRead,
    ResolvedConnectorVersionRead,
    ResolvedToolVersionRead,
    RuntimeCheckpointRead,
    SpecOrigin,
    TraceSummary,
    WorkflowAgentRef,
)
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.backtest_engine import BacktestEngine
from app.services.execution_adapters import (
    BacktestLangGraphExecutionAdapter,
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
        persona_kind=PersonaProfileKind.MANAGED_PERSONA,
        origin=SpecOrigin.MANAGED,
        selection_source="test",
    )


def _capability_ref(
    key: str,
    *,
    version: int = 1,
    capability_type: CapabilityType,
    approval_mode: ApprovalMode,
    selection_source: str = "test",
) -> CapabilityRef:
    return CapabilityRef(
        capability_key=key,
        capability_version=version,
        capability_type=capability_type,
        selection_source=selection_source,
        effective_approval_mode=approval_mode,
        effective_config={},
    )


def _resolved_capability(
    key: str,
    *,
    version: int = 1,
    capability_type: CapabilityType,
    approval_mode: ApprovalMode,
    transport: str | None = None,
) -> ResolvedCapabilityRead:
    return ResolvedCapabilityRead(
        capability_key=key,
        capability_version=version,
        capability_type=capability_type,
        approval_mode=approval_mode,
        transport=transport,
        lifecycle=None,
        effective_config={},
    )


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


class RecordingRunner:
    def __init__(self, result: BacktestLangGraphResult) -> None:
        self.result = result
        self.requests: list[Any] = []

    def run_cycle(self, request: Any) -> BacktestLangGraphResult:
        self.requests.append(request)
        return self.result


def test_backtest_adapter_translates_to_runner_boundary_and_avoids_side_effects(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(key="backtest_agent", version=1),
                _build_workflow_spec(
                    key="backtest_runtime_flow",
                    version=1,
                    execution_mode="structured_output",
                    graph_definition={
                        "entryStepKey": "analysis",
                        "steps": [
                            {
                                "stepKey": "analysis",
                                "agentSpecKey": "backtest_agent",
                                "agentSpecVersion": 1,
                            }
                        ],
                    },
                ),
            ]
        )
        session.commit()

        monkeypatch.setattr(
            session,
            "commit",
            lambda: (_ for _ in ()).throw(AssertionError("adapter must not commit")),
        )
        monkeypatch.setattr(
            BacktestEngine,
            "apply_cycle_trades",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("adapter must not apply trades")
            ),
        )
        monkeypatch.setattr(
            BacktestEngine,
            "finalize",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("adapter must not finalize backtests")
            ),
        )
        monkeypatch.setattr(
            BacktestCycleService,
            "_store_orchestration_snapshot",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("adapter must not write snapshot rows")
            ),
        )

        runner = RecordingRunner(
            BacktestLangGraphResult(
                report_content="# Analysis\n\nUse the frozen prompt report.",
                decisions=[
                    TradeDecision(
                        symbol="AAPL",
                        action="BUY",
                        quantity=1,
                        reasoning="Momentum is improving.",
                    )
                ],
                tool_call_trace=[
                    {
                        "call_index": 0,
                        "tool_id": "ledger.report_lookup",
                        "status": "success",
                        "latency_ms": 4,
                        "argument_hash": "a" * 64,
                        "result_hash": "b" * 64,
                    }
                ],
                approval_trace="not_required",
            )
        )
        adapter = BacktestLangGraphExecutionAdapter(
            session,
            runner_factory=lambda _: cast(Any, runner),
        )
        snapshot = FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key="backtest_runtime_flow",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs={
                "prompt_report_slug": "prompt-77",
                "prompt_report": "# Prompt\n\nPositions:\n- AAPL: 5 shares @ 180.00 USD\n",
                "authored_entry_prompt_body": "# authored",
                "compiled_entry_prompt_body": "# compiled",
                "execution_context_body": "# context",
                "full_user_prompt": "# full prompt",
                "resolved_mentions_json": "[]",
                "mentioned_target_outputs_json": "[]",
                "cycle_market_data_json": "{}",
            },
            resolved_workflow_agent_refs=(
                _workflow_step("analysis", "backtest_agent", agent_version=1),
            ),
            resolved_persona_profile_refs=(_persona_ref("persona.alpha"),),
            resolved_capabilities=(
                _resolved_capability(
                    "ledger.report_lookup",
                    capability_type=CapabilityType.TOOL,
                    approval_mode=ApprovalMode.NOT_REQUIRED,
                ),
            ),
            resolved_tool_versions=(
                ResolvedToolVersionRead(tool_id="ledger.report_lookup", revision=1),
            ),
        )

        result = adapter.execute(
            _request(
                snapshot,
                caller_type="backtest",
                caller_id=77,
                caller_scope_key="2024-07-01",
            )
        )

        runner_request = runner.requests[0]
        assert runner_request.backtest_id == 77
        assert runner_request.cycle_date == date(2024, 7, 1)
        assert runner_request.prompt_report_slug == "prompt-77"
        assert runner_request.authored_entry_prompt_body == "# authored"
        assert runner_request.execution_mode == "structured_output"
        assert isinstance(runner_request.tool_runtime, BacktestLangGraphToolRuntime)
        assert runner_request.tool_runtime.tool_ids == ("ledger.report_lookup",)
        assert result.status == "SUCCEEDED"
        assert result.artifact_patch is not None
        assert (
            result.artifact_patch.report_markdown == "# Analysis\n\nUse the frozen prompt report."
        )
        assert result.artifact_patch.final_output == {
            "analysis_report": "# Analysis\n\nUse the frozen prompt report.",
            "trade_decisions": [
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 1,
                    "targetPrice": None,
                    "reasoning": "Momentum is improving.",
                }
            ],
        }
        assert result.trace_events[0].event_type == "STEP_STARTED"
        assert result.trace_events[1].event_type == "TOOL_CALLED"
        assert result.trace_events[-1].event_type == "STEP_COMPLETED"


def test_backtest_adapter_waits_for_required_connector_and_resume_reuses_checkpoint(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(key="backtest_agent", version=1),
                _build_workflow_spec(
                    key="backtest_tool_flow",
                    version=1,
                    execution_mode="tool_enabled",
                    graph_definition={
                        "entryStepKey": "analysis",
                        "steps": [
                            {
                                "stepKey": "analysis",
                                "agentSpecKey": "backtest_agent",
                                "agentSpecVersion": 1,
                            }
                        ],
                    },
                ),
            ]
        )
        session.commit()

        runner = RecordingRunner(
            BacktestLangGraphResult(
                report_content="# Approved",
                decisions=[],
                tool_call_trace=[],
                approval_trace=[
                    {
                        "call_index": 0,
                        "tool_id": "ledger.mcp.market_data",
                        "status": "approved",
                        "kind": "connector",
                        "transport": "mcp",
                    }
                ],
            )
        )
        adapter = BacktestLangGraphExecutionAdapter(
            session,
            runner_factory=lambda _: cast(Any, runner),
        )
        snapshot = FrozenExecutionSnapshot(
            execution_kind="workflow",
            workflow_spec_key="backtest_tool_flow",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            inputs={
                "prompt_report_slug": "prompt-88",
                "prompt_report": "# Prompt\n\nPositions:\n- NVDA: 3 shares @ 1200.00 USD\n",
                "cycle_market_data_json": json.dumps({"NVDA": {"close": "1200.00"}}),
            },
            resolved_workflow_agent_refs=(
                _workflow_step("analysis", "backtest_agent", agent_version=1),
            ),
            resolved_capabilities=(
                _resolved_capability(
                    "ledger.mcp.market_data",
                    capability_type=CapabilityType.CONNECTOR,
                    approval_mode=ApprovalMode.REQUIRED,
                    transport="mcp",
                ),
            ),
            resolved_connector_versions=(
                ResolvedConnectorVersionRead(connector_id="ledger.mcp.market_data", revision=1),
            ),
        )

        waiting = adapter.execute(
            _request(
                snapshot,
                caller_type="backtest",
                caller_id=88,
                caller_scope_key="2024-07-08",
            )
        )

        assert waiting.status == "WAITING_APPROVAL"
        assert runner.requests == []
        assert waiting.approval_requests[0].step_key == "tool_runtime"
        assert waiting.approval_requests[0].capability_key == "ledger.mcp.market_data"
        checkpoint = _checkpoint(
            waiting.checkpoints[0].step_key,
            waiting.checkpoints[0].serialized_state,
        )
        resumed = adapter.execute(
            _request(
                snapshot,
                dispatch_mode="resume",
                caller_type="backtest",
                caller_id=88,
                caller_scope_key="2024-07-08",
                approvals=(_approved_approval("tool_runtime", "ledger.mcp.market_data"),),
                checkpoints=(checkpoint,),
                current_checkpoint=checkpoint,
                approval_summary=_approval_summary(total_count=1, approved_count=1),
            )
        )

        runner_request = runner.requests[0]
        connector_adapter = runner_request.tool_runtime.adapters[0]
        assert connector_adapter.tool_id == "ledger.mcp.market_data"
        assert connector_adapter.approval_required is True
        assert connector_adapter.approval_granted is True
        assert resumed.status == "SUCCEEDED"
        assert resumed.artifact_patch is not None
        assert resumed.artifact_patch.report_markdown == "# Approved"


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
