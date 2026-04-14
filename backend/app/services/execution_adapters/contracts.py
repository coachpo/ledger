from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from app.schemas.runtime import (
    ApprovalSummary,
    PersonaProfileRef,
    ResolvedBundleVersionRead,
    ResolvedCapabilityRead,
    ResolvedConnectorVersionRead,
    ResolvedToolVersionRead,
    RuntimeCheckpointRead,
    TraceSummary,
    WorkflowAgentRef,
)

ExecutionAdapterDispatchMode = Literal["start", "resume", "retry"]
ExecutionAdapterResultStatus = Literal["SUCCEEDED", "WAITING_APPROVAL"]


@dataclass(frozen=True)
class FrozenExecutionSnapshot:
    execution_kind: Literal["workflow", "single_agent"]
    workflow_spec_key: str | None
    workflow_spec_version: int | None
    agent_spec_key: str | None
    agent_spec_version: int | None
    inputs: Mapping[str, str]
    resolved_workflow_agent_refs: tuple[WorkflowAgentRef, ...] = ()
    resolved_persona_profile_refs: tuple[PersonaProfileRef, ...] = ()
    resolved_capabilities: tuple[ResolvedCapabilityRead, ...] = ()
    resolved_bundle_versions: tuple[ResolvedBundleVersionRead, ...] = ()
    resolved_tool_versions: tuple[ResolvedToolVersionRead, ...] = ()
    resolved_connector_versions: tuple[ResolvedConnectorVersionRead, ...] = ()


@dataclass(frozen=True)
class ExecutionApprovalState:
    approval_id: int
    step_key: str
    capability_key: str
    status: Literal["PENDING", "APPROVED", "DENIED", "EXPIRED"]
    actor: str | None = None
    reason: str | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionAdapterRequest:
    dispatch_mode: ExecutionAdapterDispatchMode
    run_id: int
    attempt_number: int
    caller_type: str
    caller_id: int | None
    caller_scope_key: str | None
    caller_identity_key: str | None
    snapshot: FrozenExecutionSnapshot
    trace_summary: TraceSummary
    approval_summary: ApprovalSummary
    checkpoints: tuple[RuntimeCheckpointRead, ...] = ()
    current_checkpoint: RuntimeCheckpointRead | None = None
    approvals: tuple[ExecutionApprovalState, ...] = ()


@dataclass(frozen=True)
class ExecutionAdapterTraceEvent:
    event_type: str
    step_key: str | None = None
    capability_key: str | None = None
    approval_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionApprovalRequest:
    step_key: str
    capability_key: str


@dataclass(frozen=True)
class ExecutionCheckpointRecord:
    checkpoint_index: int
    step_key: str
    serialized_state: dict[str, Any]


@dataclass(frozen=True)
class ExecutionArtifactPatch:
    final_output: Any | None = None
    report_markdown: str | None = None
    normalized_trade_decisions: tuple[dict[str, Any], ...] | None = None


@dataclass(frozen=True)
class ExecutionAdapterResult:
    status: ExecutionAdapterResultStatus
    trace_events: tuple[ExecutionAdapterTraceEvent, ...] = ()
    approval_requests: tuple[ExecutionApprovalRequest, ...] = ()
    checkpoints: tuple[ExecutionCheckpointRecord, ...] = ()
    artifact_patch: ExecutionArtifactPatch | None = None


class ExecutionAdapter(Protocol):
    def execute(self, request: ExecutionAdapterRequest) -> ExecutionAdapterResult: ...
