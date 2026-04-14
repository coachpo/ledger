from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error
from app.models.agent_spec import AgentSpec
from app.repositories.agent_spec import AgentSpecRepository
from app.schemas.runtime import ApprovalMode, CapabilityRef
from app.services.execution_adapters._shared import (
    approval_mode_for_capability,
    build_resolved_capability_lookup,
    build_waiting_approval_result,
    has_approved_capability,
    load_checkpoint_state,
    resolve_frozen_capability,
)
from app.services.execution_adapters.contracts import (
    ExecutionAdapter,
    ExecutionAdapterRequest,
    ExecutionAdapterResult,
    ExecutionAdapterTraceEvent,
    ExecutionArtifactPatch,
)

_ADAPTER_KEY = "single_agent"


class SingleAgentExecutionAdapter(ExecutionAdapter):
    def __init__(self, session: Session) -> None:
        self.session = session
        self.agent_repository = AgentSpecRepository(session)

    def execute(self, request: ExecutionAdapterRequest) -> ExecutionAdapterResult:
        if request.snapshot.execution_kind != "single_agent":
            raise business_rule_error(
                "runtime_single_agent_adapter_invalid_kind",
                "Single-agent adapter requires executionKind=single_agent",
            )
        agent = self._load_agent(request)
        step_key = agent.key
        capability_lookup = build_resolved_capability_lookup(request.snapshot.resolved_capabilities)
        trace_events: list[ExecutionAdapterTraceEvent] = []

        resume_capability_index = 0
        if request.dispatch_mode == "resume":
            state = load_checkpoint_state(request, adapter_key=_ADAPTER_KEY)
            if str(state.get("step_key") or "") != step_key:
                raise business_rule_error(
                    "runtime_checkpoint_mismatch",
                    (
                        f"Run {request.run_id} checkpoint targets step {state.get('step_key')!r}, "
                        f"not single-agent step {step_key!r}"
                    ),
                )
            resume_capability_index = int(state.get("capability_index", 0))
        else:
            trace_events.append(
                ExecutionAdapterTraceEvent(
                    event_type="STEP_STARTED",
                    step_key=step_key,
                    payload={
                        "agentSpecKey": agent.key,
                        "agentSpecVersion": agent.version,
                    },
                )
            )

        executed_capabilities: list[dict[str, Any]] = []
        for capability_index, capability in enumerate(
            request.snapshot.resolved_capabilities[resume_capability_index:],
            start=resume_capability_index,
        ):
            capability_ref = CapabilityRef(
                capability_key=capability.capability_key,
                capability_version=capability.capability_version,
                capability_type=capability.capability_type,
                effective_approval_mode=capability.approval_mode,
                effective_config=dict(capability.effective_config),
                selection_source="run_resolution",
            )
            resolved_capability = resolve_frozen_capability(
                capability_ref,
                step_key=step_key,
                resolved_lookup=capability_lookup,
            )
            if approval_mode_for_capability(
                capability_ref,
                resolved_capability,
            ) == ApprovalMode.REQUIRED and not has_approved_capability(
                request,
                step_key=step_key,
                capability_key=resolved_capability.capability_key,
            ):
                return build_waiting_approval_result(
                    request,
                    adapter_key=_ADAPTER_KEY,
                    step_key=step_key,
                    capability_key=resolved_capability.capability_key,
                    capability_index=capability_index,
                    trace_events=tuple(trace_events),
                    extra_state={
                        "agent_spec_key": agent.key,
                        "agent_spec_version": agent.version,
                    },
                )

            trace_events.append(
                ExecutionAdapterTraceEvent(
                    event_type="TOOL_CALLED",
                    step_key=step_key,
                    capability_key=resolved_capability.capability_key,
                    payload={
                        "capabilityVersion": resolved_capability.capability_version,
                        "capabilityType": resolved_capability.capability_type.value,
                        "approvalMode": resolved_capability.approval_mode.value,
                    },
                )
            )
            executed_capabilities.append(
                {
                    "capabilityKey": resolved_capability.capability_key,
                    "capabilityVersion": resolved_capability.capability_version,
                    "capabilityType": resolved_capability.capability_type.value,
                }
            )

        trace_events.append(
            ExecutionAdapterTraceEvent(
                event_type="STEP_COMPLETED",
                step_key=step_key,
                payload={"agentSpecKey": agent.key, "capabilityCount": len(executed_capabilities)},
            )
        )
        persona_profile_keys = [
            persona.persona_profile_key
            for persona in request.snapshot.resolved_persona_profile_refs
        ]
        final_output = {
            "executionKind": "single_agent",
            "agent": {"key": agent.key, "version": agent.version, "name": agent.name},
            "inputs": dict(request.snapshot.inputs),
            "personaProfileKeys": persona_profile_keys,
            "capabilities": executed_capabilities,
            "summary": f"Executed {agent.name} from frozen pinned refs.",
        }
        capability_keys = ", ".join(cap["capabilityKey"] for cap in executed_capabilities) or "none"
        report_markdown = "\n".join(
            [
                "# Single-Agent Execution",
                "",
                f"- Agent: {agent.name} ({agent.key} v{agent.version})",
                f"- Personas: {', '.join(persona_profile_keys) or 'none'}",
                f"- Capabilities: {capability_keys}",
                f"- Summary: {final_output['summary']}",
            ]
        )
        return ExecutionAdapterResult(
            status="SUCCEEDED",
            trace_events=tuple(trace_events),
            artifact_patch=ExecutionArtifactPatch(
                final_output=final_output,
                report_markdown=report_markdown,
            ),
        )

    def _load_agent(self, request: ExecutionAdapterRequest) -> AgentSpec:
        agent_key = request.snapshot.agent_spec_key
        agent_version = request.snapshot.agent_spec_version
        if agent_key is None or agent_version is None:
            raise business_rule_error(
                "runtime_single_agent_adapter_missing_target",
                f"Run {request.run_id} is missing its pinned single-agent target",
            )
        agent = self.agent_repository.get_by_key_version(agent_key, agent_version)
        if agent is None:
            raise business_rule_error(
                "runtime_agent_not_found",
                f"Agent spec {agent_key!r} v{agent_version} was not found",
            )
        return agent
