from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.errors import not_found_error
from app.models.agent import Agent
from app.models.run import Run
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.workflow import WorkflowRepository
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanSource,
    ExecutionPlanSourceKind,
    ExecutionPlanStep,
    ExecutionPlanTarget,
)


@dataclass(frozen=True)
class ExecutionPlanBuilderError(Exception):
    code: str
    message: str
    details: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


class ExecutionPlanBuilder:
    def __init__(self, session: Session) -> None:
        self.agent_repository = AgentRepository(session)
        self.workflow_repository = WorkflowRepository(session)

    def build_target_plan(
        self,
        target_kind: str,
        target_id: int,
        *,
        version: int | None = None,
    ) -> ExecutionPlan:
        if target_kind == "workflow":
            workflow = self._resolve_workflow_target(target_id, version=version)
            return self._build_workflow_plan(workflow)
        if target_kind == "agent":
            agent = self._resolve_agent_target(target_id, version=version)
            return self._build_agent_plan(agent)
        raise ValueError(f"Unsupported run target kind {target_kind!r}")

    def build_plan_for_run(self, run: Run) -> ExecutionPlan:
        if run.target_kind == "workflow":
            workflow = self.workflow_repository.get_by_key_version(
                run.target_key, run.target_version
            )
            if workflow is None:
                raise ExecutionPlanBuilderError(
                    code="run_workflow_missing",
                    message=(
                        f"Workflow {run.target_key!r} version {run.target_version} "
                        "is no longer available"
                    ),
                )
            return self._build_workflow_plan(workflow)
        if run.target_kind == "agent":
            agent = self.agent_repository.get_by_key_version(run.target_key, run.target_version)
            if agent is None:
                raise ExecutionPlanBuilderError(
                    code="run_agent_missing",
                    message=(
                        f"Agent {run.target_key!r} version {run.target_version} "
                        "is no longer available"
                    ),
                )
            return self._build_agent_plan(agent)
        raise ExecutionPlanBuilderError(
            code="run_target_kind_invalid",
            message=f"Unsupported run target kind {run.target_kind!r}",
        )

    def _resolve_workflow_target(self, workflow_id: int, *, version: int | None) -> Workflow:
        anchor = self.workflow_repository.get(workflow_id)
        if anchor is None:
            raise not_found_error("Workflow")
        if version is None:
            return anchor
        workflow = self.workflow_repository.get_by_key_version(anchor.key, version)
        if workflow is None:
            raise not_found_error("Workflow")
        return workflow

    def _resolve_agent_target(self, agent_id: int, *, version: int | None) -> Agent:
        anchor = self.agent_repository.get(agent_id)
        if anchor is None:
            raise not_found_error("Agent")
        if version is None:
            return anchor
        agent = self.agent_repository.get_by_key_version(anchor.key, version)
        if agent is None:
            raise not_found_error("Agent")
        return agent

    def _build_workflow_plan(self, workflow: Workflow) -> ExecutionPlan:
        normalized_steps, normalized_output_spec = self._normalize_workflow_steps_and_output_spec(
            workflow.steps,
            workflow.output_spec,
        )
        steps = [self._build_workflow_step(raw_step) for raw_step in normalized_steps]
        final_output = self._build_final_output_selector(normalized_output_spec)

        return ExecutionPlan(
            target=ExecutionPlanTarget(
                kind="workflow",
                id=workflow.id,
                key=workflow.key,
                version=workflow.version,
            ),
            input_schema=deepcopy(workflow.input_schema),
            aggregate_budget_usd=workflow.aggregate_budget_usd,
            steps=tuple(steps),
            final_output=final_output,
        )

    def _normalize_workflow_steps_and_output_spec(
        self,
        raw_steps: list[dict[str, Any]],
        raw_output_spec: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        steps = deepcopy(raw_steps)
        output_spec = deepcopy(raw_output_spec)
        if output_spec.get("kind") != "agent":
            return steps, output_spec

        synthetic_final_step_index = len(steps) + 1
        steps.append(
            {
                "index": synthetic_final_step_index,
                "agents": [
                    {
                        "slot": "final_output",
                        "agentId": int(output_spec["agentId"]),
                        "agentKey": str(output_spec["agentKey"]),
                        "agentVersion": int(output_spec["agentVersion"]),
                        "outputSchemaId": int(output_spec["outputSchemaId"]),
                        "outputSchemaVersion": int(output_spec["outputSchemaVersion"]),
                        "wiring": deepcopy(output_spec.get("wiring") or {}),
                        "optional": False,
                    }
                ],
            }
        )
        return steps, {
            "kind": "slot",
            "stepIndex": synthetic_final_step_index,
            "slot": "final_output",
        }

    def _build_agent_plan(self, agent: Agent) -> ExecutionPlan:
        step = ExecutionPlanStep(
            index=1,
            agents=(
                ExecutionPlanAgent(
                    slot="final_output",
                    agent_id=agent.id,
                    agent_key=agent.key,
                    agent_version=agent.version,
                    output_schema_id=agent.output_schema_id,
                    output_schema_version=agent.output_schema_version,
                    wiring={},
                    optional=False,
                    input_mode="passthrough",
                ),
            ),
        )
        return ExecutionPlan(
            target=ExecutionPlanTarget(
                kind="agent",
                id=agent.id,
                key=agent.key,
                version=agent.version,
            ),
            input_schema=deepcopy(agent.input_schema),
            aggregate_budget_usd=agent.budget_usd,
            steps=(step,),
            final_output=ExecutionPlanFinalOutput(step_index=1, slot="final_output"),
        )

    def _build_workflow_step(self, raw_step: dict[str, Any]) -> ExecutionPlanStep:
        return ExecutionPlanStep(
            index=int(raw_step["index"]),
            agents=tuple(
                ExecutionPlanAgent(
                    slot=str(raw_agent["slot"]),
                    agent_id=int(raw_agent["agentId"]),
                    agent_key=str(raw_agent["agentKey"]),
                    agent_version=int(raw_agent["agentVersion"]),
                    output_schema_id=int(raw_agent["outputSchemaId"]),
                    output_schema_version=int(raw_agent["outputSchemaVersion"]),
                    wiring=self._build_wiring(raw_agent.get("wiring") or {}),
                    optional=bool(raw_agent.get("optional", False)),
                )
                for raw_agent in raw_step.get("agents") or []
            ),
        )

    @staticmethod
    def _build_final_output_selector(output_spec: dict[str, Any]) -> ExecutionPlanFinalOutput:
        return ExecutionPlanFinalOutput(
            step_index=int(output_spec["stepIndex"]),
            slot=str(output_spec["slot"]),
            path=None if output_spec.get("path") is None else str(output_spec["path"]),
        )

    @staticmethod
    def _build_wiring(raw_wiring: dict[str, Any]) -> dict[str, ExecutionPlanSource]:
        return {
            str(target_name): ExecutionPlanSource(
                source=cast(
                    ExecutionPlanSourceKind,
                    str(raw_source.get("from", raw_source.get("source", ""))),
                ),
                path=None if raw_source.get("path") is None else str(raw_source["path"]),
                step_index=(
                    None if raw_source.get("stepIndex") is None else int(raw_source["stepIndex"])
                ),
                slot=None if raw_source.get("slot") is None else str(raw_source["slot"]),
            )
            for target_name, raw_source in raw_wiring.items()
        }


__all__ = ["ExecutionPlanBuilder", "ExecutionPlanBuilderError"]
