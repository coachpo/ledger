from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.core.errors import business_rule_error
from app.schemas.runtime import ApprovalMode, CapabilityRef, ResolvedCapabilityRead
from app.services.execution_adapters.contracts import (
    ExecutionAdapterRequest,
    ExecutionAdapterResult,
    ExecutionAdapterTraceEvent,
    ExecutionApprovalRequest,
    ExecutionCheckpointRecord,
)


def extract_graph_steps(graph_definition: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = graph_definition.get("steps")
    if isinstance(raw_steps, list) and raw_steps:
        extracted_steps: list[dict[str, Any]] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                continue
            step_key = str(raw_step.get("stepKey") or raw_step.get("step_key") or "").strip()
            agent_spec_key = str(
                raw_step.get("agentSpecKey") or raw_step.get("agent_spec_key") or ""
            ).strip()
            if not step_key or not agent_spec_key:
                continue
            raw_version = raw_step.get("agentSpecVersion") or raw_step.get("agent_spec_version")
            agent_spec_version = int(raw_version) if isinstance(raw_version, int) else None
            extracted_steps.append(
                {
                    "step_key": step_key,
                    "agent_spec_key": agent_spec_key,
                    "agent_spec_version": agent_spec_version,
                }
            )
        if extracted_steps:
            return extracted_steps

    kind = str(graph_definition.get("kind") or "").strip()
    raw_agent_order = graph_definition.get("agent_order") or graph_definition.get("agentOrder")
    if (
        kind == "seeded_langgraph_topology"
        and isinstance(raw_agent_order, list)
        and raw_agent_order
    ):
        return [
            {
                "step_key": str(agent_key).strip(),
                "agent_spec_key": str(agent_key).strip(),
                "agent_spec_version": None,
            }
            for agent_key in raw_agent_order
            if str(agent_key).strip()
        ]
    return []


def build_resolved_capability_lookup(
    resolved_capabilities: Sequence[ResolvedCapabilityRead],
) -> dict[tuple[str, int], ResolvedCapabilityRead]:
    return {
        (capability.capability_key, capability.capability_version): capability
        for capability in resolved_capabilities
    }


def resolve_frozen_capability(
    capability_ref: CapabilityRef,
    *,
    step_key: str,
    resolved_lookup: Mapping[tuple[str, int], ResolvedCapabilityRead],
) -> ResolvedCapabilityRead:
    capability_version = capability_ref.capability_version
    if capability_version is None:
        raise business_rule_error(
            "runtime_frozen_capability_missing_version",
            (
                f"Frozen capability {capability_ref.capability_key!r} on step {step_key!r} "
                "is missing a pinned version"
            ),
        )
    resolved = resolved_lookup.get((capability_ref.capability_key, capability_version))
    if resolved is None:
        raise business_rule_error(
            "runtime_widened_capability_usage",
            (
                f"Frozen step {step_key!r} references capability "
                f"{capability_ref.capability_key!r} v{capability_version} outside the "
                "flattened frozen capability set"
            ),
        )
    if (
        capability_ref.capability_type is not None
        and capability_ref.capability_type != resolved.capability_type
    ):
        raise business_rule_error(
            "runtime_frozen_capability_drift",
            (
                f"Frozen capability {capability_ref.capability_key!r} on step {step_key!r} "
                "changed type between step-local and flattened frozen refs"
            ),
        )
    if (
        capability_ref.effective_approval_mode is not None
        and capability_ref.effective_approval_mode != resolved.approval_mode
    ):
        raise business_rule_error(
            "runtime_frozen_capability_drift",
            (
                f"Frozen capability {capability_ref.capability_key!r} on step {step_key!r} "
                "changed approval mode between step-local and flattened frozen refs"
            ),
        )
    return resolved


def next_checkpoint_index(request: ExecutionAdapterRequest) -> int:
    if not request.checkpoints:
        return 0
    return request.checkpoints[-1].checkpoint_index + 1


def load_checkpoint_state(
    request: ExecutionAdapterRequest,
    *,
    adapter_key: str,
) -> dict[str, Any]:
    checkpoint = request.current_checkpoint
    if checkpoint is None:
        raise business_rule_error(
            "runtime_checkpoint_missing",
            f"Run {request.run_id} cannot resume without a checkpoint",
        )
    state = dict(checkpoint.serialized_state)
    if state.get("adapter") != adapter_key:
        raise business_rule_error(
            "runtime_checkpoint_adapter_mismatch",
            (
                f"Run {request.run_id} checkpoint belongs to adapter "
                f"{state.get('adapter')!r}, not {adapter_key!r}"
            ),
        )
    return state


def has_approved_capability(
    request: ExecutionAdapterRequest,
    *,
    step_key: str,
    capability_key: str,
) -> bool:
    return any(
        approval.step_key == step_key
        and approval.capability_key == capability_key
        and approval.status == "APPROVED"
        for approval in request.approvals
    )


def build_waiting_approval_result(
    request: ExecutionAdapterRequest,
    *,
    adapter_key: str,
    step_key: str,
    capability_key: str,
    capability_index: int,
    trace_events: Sequence[ExecutionAdapterTraceEvent] = (),
    extra_state: Mapping[str, Any] | None = None,
) -> ExecutionAdapterResult:
    checkpoint_state: dict[str, Any] = {
        "adapter": adapter_key,
        "phase": "awaiting_approval",
        "step_key": step_key,
        "capability_key": capability_key,
        "capability_index": capability_index,
    }
    if extra_state is not None:
        checkpoint_state.update(dict(extra_state))
    return ExecutionAdapterResult(
        status="WAITING_APPROVAL",
        trace_events=tuple(trace_events),
        approval_requests=(
            ExecutionApprovalRequest(step_key=step_key, capability_key=capability_key),
        ),
        checkpoints=(
            ExecutionCheckpointRecord(
                checkpoint_index=next_checkpoint_index(request),
                step_key=step_key,
                serialized_state=checkpoint_state,
            ),
        ),
    )


def require_text_input(inputs: Mapping[str, str], field_name: str) -> str:
    value = str(inputs.get(field_name, "")).strip()
    if value:
        return value
    raise business_rule_error(
        "runtime_input_missing",
        f"Frozen runtime input {field_name!r} is required",
    )


def optional_text_input(inputs: Mapping[str, str], field_name: str) -> str:
    return str(inputs.get(field_name, ""))


def load_json_input(
    inputs: Mapping[str, str],
    field_name: str,
    *,
    default: Any,
) -> Any:
    raw_value = str(inputs.get(field_name, "")).strip()
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise business_rule_error(
            "runtime_input_invalid",
            f"Frozen runtime input {field_name!r} must be valid JSON",
        ) from exc


def approval_mode_for_capability(
    capability_ref: CapabilityRef,
    resolved_capability: ResolvedCapabilityRead,
) -> ApprovalMode:
    return capability_ref.effective_approval_mode or resolved_capability.approval_mode
