from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error
from app.models.agent_spec import AgentSpec
from app.models.workflow_spec import WorkflowSpec
from app.repositories.agent_spec import AgentSpecRepository
from app.repositories.workflow_spec import WorkflowSpecRepository
from app.schemas.runtime import ApprovalMode, WorkflowAgentRef
from app.services.execution_adapters._shared import (
    approval_mode_for_capability,
    build_resolved_capability_lookup,
    build_waiting_approval_result,
    extract_graph_steps,
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

_ADAPTER_KEY = "generic_workflow"


class GenericWorkflowExecutionAdapter(ExecutionAdapter):
    def __init__(self, session: Session) -> None:
        self.session = session
        self.workflow_repository = WorkflowSpecRepository(session)
        self.agent_repository = AgentSpecRepository(session)

    def execute(self, request: ExecutionAdapterRequest) -> ExecutionAdapterResult:
        if request.snapshot.execution_kind != "workflow":
            raise business_rule_error(
                "runtime_workflow_adapter_invalid_kind",
                "Generic workflow adapter requires executionKind=workflow",
            )
        workflow = self._load_workflow(request)
        frozen_steps = tuple(request.snapshot.resolved_workflow_agent_refs)
        if not frozen_steps:
            raise business_rule_error(
                "runtime_frozen_workflow_plan_missing",
                f"Run {request.run_id} is missing its frozen workflow step plan",
            )
        self._validate_frozen_plan(workflow, frozen_steps)
        ordered_steps = self._ordered_steps(workflow, frozen_steps)
        capability_lookup = build_resolved_capability_lookup(request.snapshot.resolved_capabilities)
        step_outputs: list[dict[str, Any]] = []
        trace_events: list[ExecutionAdapterTraceEvent] = []

        resume_state = None
        resume_step_index = 0
        resume_capability_index = 0
        if request.dispatch_mode == "resume":
            resume_state = load_checkpoint_state(request, adapter_key=_ADAPTER_KEY)
            resume_step_index = int(resume_state.get("step_index", 0))
            resume_capability_index = int(resume_state.get("capability_index", 0))

        for step_index, step in enumerate(ordered_steps):
            agent = self._load_agent(step)
            if step_index < resume_step_index:
                continue

            emit_step_started = not (
                request.dispatch_mode == "resume" and step_index == resume_step_index
            )
            if emit_step_started:
                trace_events.append(
                    ExecutionAdapterTraceEvent(
                        event_type="STEP_STARTED",
                        step_key=step.step_key,
                        payload={
                            "agentSpecKey": step.agent_spec_key,
                            "agentSpecVersion": step.agent_spec_version,
                        },
                    )
                )

            capability_start = resume_capability_index if step_index == resume_step_index else 0
            executed_capabilities: list[dict[str, Any]] = []
            for capability_index, capability_ref in enumerate(
                step.capability_refs[capability_start:],
                start=capability_start,
            ):
                resolved_capability = resolve_frozen_capability(
                    capability_ref,
                    step_key=step.step_key,
                    resolved_lookup=capability_lookup,
                )
                if (
                    approval_mode_for_capability(capability_ref, resolved_capability)
                    == ApprovalMode.REQUIRED
                ):
                    if not has_approved_capability(
                        request,
                        step_key=step.step_key,
                        capability_key=resolved_capability.capability_key,
                    ):
                        return build_waiting_approval_result(
                            request,
                            adapter_key=_ADAPTER_KEY,
                            step_key=step.step_key,
                            capability_key=resolved_capability.capability_key,
                            capability_index=capability_index,
                            trace_events=tuple(trace_events),
                            extra_state={
                                "workflow_spec_key": request.snapshot.workflow_spec_key,
                                "workflow_spec_version": request.snapshot.workflow_spec_version,
                                "step_index": step_index,
                            },
                        )

                trace_events.append(
                    ExecutionAdapterTraceEvent(
                        event_type="TOOL_CALLED",
                        step_key=step.step_key,
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

            step_outputs.append(
                {
                    "stepKey": step.step_key,
                    "agentSpecKey": step.agent_spec_key,
                    "agentSpecVersion": step.agent_spec_version,
                    "agentName": agent.name,
                    "personaProfileKeys": [
                        persona.persona_profile_key for persona in step.persona_profile_refs
                    ],
                    "capabilities": executed_capabilities,
                    "summary": f"Executed {agent.name} using the frozen step plan.",
                }
            )
            trace_events.append(
                ExecutionAdapterTraceEvent(
                    event_type="STEP_COMPLETED",
                    step_key=step.step_key,
                    payload={
                        "agentSpecKey": step.agent_spec_key,
                        "capabilityCount": len(executed_capabilities),
                    },
                )
            )

        final_output = {
            "executionKind": "workflow",
            "workflow": {
                "key": request.snapshot.workflow_spec_key,
                "version": request.snapshot.workflow_spec_version,
            },
            "inputs": dict(request.snapshot.inputs),
            "steps": step_outputs,
        }
        return ExecutionAdapterResult(
            status="SUCCEEDED",
            trace_events=tuple(trace_events),
            artifact_patch=ExecutionArtifactPatch(
                final_output=final_output,
                report_markdown=self._render_report(workflow, step_outputs),
            ),
        )

    def _load_workflow(self, request: ExecutionAdapterRequest) -> WorkflowSpec:
        workflow_key = request.snapshot.workflow_spec_key
        workflow_version = request.snapshot.workflow_spec_version
        if workflow_key is None or workflow_version is None:
            raise business_rule_error(
                "runtime_workflow_adapter_missing_target",
                f"Run {request.run_id} is missing its pinned workflow target",
            )
        workflow = self.workflow_repository.get_by_key_version(workflow_key, workflow_version)
        if workflow is None:
            raise business_rule_error(
                "runtime_workflow_not_found",
                f"Workflow spec {workflow_key!r} v{workflow_version} was not found",
            )
        return workflow

    def _load_agent(self, step: WorkflowAgentRef) -> AgentSpec:
        agent = self.agent_repository.get_by_key_version(
            step.agent_spec_key, step.agent_spec_version
        )
        if agent is None:
            raise business_rule_error(
                "runtime_step_agent_not_found",
                f"Workflow step {step.step_key!r} references unknown agent {step.agent_spec_key!r}",
            )
        return agent

    def _validate_frozen_plan(
        self,
        workflow: WorkflowSpec,
        frozen_steps: Sequence[WorkflowAgentRef],
    ) -> None:
        expected_steps = self._extract_graph_steps(workflow.graph_definition)
        if len(expected_steps) != len(frozen_steps):
            raise business_rule_error(
                "runtime_frozen_workflow_plan_drift",
                f"Workflow {workflow.key!r} no longer matches its frozen step plan",
            )
        for frozen_step, expected_step in zip(frozen_steps, expected_steps, strict=True):
            if frozen_step.step_key != expected_step["step_key"]:
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    (
                        f"Frozen workflow step {frozen_step.step_key!r} "
                        "no longer matches workflow metadata"
                    ),
                )
            if frozen_step.agent_spec_key != expected_step["agent_spec_key"]:
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    (
                        f"Frozen workflow step {frozen_step.step_key!r} points to agent "
                        f"{frozen_step.agent_spec_key!r}, but workflow metadata now points to "
                        f"{expected_step['agent_spec_key']!r}"
                    ),
                )
            expected_version = expected_step.get("agent_spec_version")
            if expected_version is not None and frozen_step.agent_spec_version != expected_version:
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    (
                        f"Frozen workflow step {frozen_step.step_key!r} pins agent version "
                        f"{frozen_step.agent_spec_version}, but workflow metadata now points to "
                        f"version {expected_version}"
                    ),
                )

    def _ordered_steps(
        self,
        workflow: WorkflowSpec,
        frozen_steps: Sequence[WorkflowAgentRef],
    ) -> tuple[WorkflowAgentRef, ...]:
        steps_by_key = {step.step_key: step for step in frozen_steps}
        ordered_keys = [step.step_key for step in frozen_steps]
        success_edges = self._extract_success_edges(workflow.graph_definition)
        entry_step_key = str(
            workflow.graph_definition.get("entryStepKey") or ordered_keys[0]
        ).strip()
        if entry_step_key not in steps_by_key:
            raise business_rule_error(
                "runtime_frozen_workflow_plan_drift",
                (f"Workflow entry step {entry_step_key!r} does not exist in the frozen step plan"),
            )

        ordered: list[WorkflowAgentRef] = []
        seen: set[str] = set()
        current = entry_step_key
        index_lookup = {step_key: index for index, step_key in enumerate(ordered_keys)}
        while current not in seen:
            step = steps_by_key[current]
            ordered.append(step)
            seen.add(current)
            next_step = success_edges.get(current)
            if next_step == "END":
                break
            if next_step is None:
                next_index = index_lookup[current] + 1
                if next_index >= len(ordered_keys):
                    break
                current = ordered_keys[next_index]
                continue
            if next_step not in steps_by_key:
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    (
                        f"Workflow success edge from {current!r} points to unknown step "
                        f"{next_step!r}"
                    ),
                )
            current = next_step
        return tuple(ordered)

    @staticmethod
    def _extract_graph_steps(graph_definition: dict[str, Any]) -> list[dict[str, Any]]:
        return extract_graph_steps(graph_definition)

    @staticmethod
    def _extract_success_edges(graph_definition: dict[str, Any]) -> dict[str, str]:
        raw_edges = graph_definition.get("edges")
        if not isinstance(raw_edges, list):
            return {}
        success_edges: dict[str, str] = {}
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            outcome = str(raw_edge.get("outcome") or "").strip().lower()
            if outcome != "success":
                continue
            from_step_key = str(
                raw_edge.get("fromStepKey") or raw_edge.get("from_step_key") or ""
            ).strip()
            to_step_key = str(
                raw_edge.get("toStepKey") or raw_edge.get("to_step_key") or ""
            ).strip()
            if from_step_key and to_step_key:
                success_edges[from_step_key] = to_step_key
        return success_edges

    @staticmethod
    def _render_report(workflow: WorkflowSpec, step_outputs: Sequence[dict[str, Any]]) -> str:
        lines = [
            "# Workflow Execution",
            "",
            f"- Workflow: {workflow.key} v{workflow.version}",
            f"- Steps executed: {len(step_outputs)}",
            "",
        ]
        for step in step_outputs:
            persona_keys = ", ".join(step["personaProfileKeys"]) or "none"
            capability_keys = (
                ", ".join(cap["capabilityKey"] for cap in step["capabilities"]) or "none"
            )
            lines.extend(
                [
                    f"## {step['stepKey']}",
                    (
                        f"- Agent: {step['agentName']} ("
                        f"{step['agentSpecKey']} v{step['agentSpecVersion']})"
                    ),
                    f"- Personas: {persona_keys}",
                    f"- Capabilities: {capability_keys}",
                    f"- Summary: {step['summary']}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip()
