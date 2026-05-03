from __future__ import annotations

import asyncio
import logging
import threading
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import decimal_to_string, utcnow
from app.core.telemetry import (
    configure_logfire,
    create_logfire_span,
    format_current_span_id,
    format_current_trace_id,
)
from app.db.engine import get_session_factory
from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.repositories.run_agent_invocation import RunAgentInvocationRepository
from app.repositories.run_step import RunStepRepository
from app.schemas.run import (
    RunCreatedRead,
    RunForkCreateRequest,
    RunForkDraftRead,
    RunForkInvocationEdit,
    RunListItemRead,
    RunListRead,
    RunRead,
    RunStatus,
    RunTargetKind,
)
from app.services.agent_execution_service import (
    AgentExecutionService,
    RunAgentInvocationResult,
    RunExecutionError,
    normalize_agent_invocation_result,
)
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanSource,
    ExecutionPlanStep,
)
from app.services.execution_plan_builder import ExecutionPlanBuilder, ExecutionPlanBuilderError
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    SchemaField,
    SchemaNode,
    SchemaObject,
    SchemaRef,
)
from app.services.quote_provider import QuoteProvider

logger = logging.getLogger(__name__)

_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class _RuntimeInvocationContext:
    run_id: int
    target_kind: str
    target_key: str
    target_version: int


@dataclass
class _PreparedAgentInvocation:
    agent: Agent
    output_model: type[BaseModel]
    resolved_input: dict[str, Any]
    invocation: RunAgentInvocation
    optional: bool
    step_index: int
    slot: str
    runtime_context: _RuntimeInvocationContext


_CURRENT_RUNTIME_INVOCATION_CONTEXT: ContextVar[_RuntimeInvocationContext | None] = ContextVar(
    "ledger_runtime_invocation_context",
    default=None,
)


class RunService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        quote_provider: QuoteProvider | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.quote_provider: QuoteProvider | None = quote_provider
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.run_repository = RunRepository(session)
        self.run_step_repository = RunStepRepository(session)
        self.run_agent_invocation_repository = RunAgentInvocationRepository(session)
        self.execution_plan_builder = ExecutionPlanBuilder(session)
        self.agent_execution_service = AgentExecutionService(
            self.session_factory,
            quote_provider=quote_provider,
        )
        self.schema_compiler = OutputSchemaCompiler(self.output_schema_repository)
        self._stored_schema_node_cache: dict[tuple[str, int], SchemaNode] = {}

    def list_runs(
        self,
        *,
        target_kind: RunTargetKind | None = None,
        target_id: int | None = None,
        target_key: str | None = None,
        target_version: int | None = None,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
        status_filter: RunStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> RunListRead:
        runs = self.run_repository.list_all(
            target_kind=target_kind.value if target_kind is not None else None,
            target_id=target_id,
            target_key=target_key,
            target_version=target_version,
            workflow_id=workflow_id,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
            status=status_filter.value if status_filter is not None else None,
            limit=limit,
            offset=offset,
        )
        return RunListRead(items=[self._to_list_item(run) for run in runs])

    def get_run(self, run_id: int) -> RunRead:
        return self._to_read_model(self._get_run_or_raise(run_id))

    def create_run(
        self,
        workflow_id: int,
        input_payload: dict[str, Any],
        *,
        version: int | None = None,
    ) -> RunCreatedRead:
        return self.create_target_run("workflow", workflow_id, input_payload, version=version)

    def create_target_run(
        self,
        target_kind: str,
        target_id: int,
        input_payload: dict[str, Any],
        *,
        version: int | None = None,
    ) -> RunCreatedRead:
        plan = self.execution_plan_builder.build_target_plan(
            target_kind, target_id, version=version
        )
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=input_payload,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        run = Run(
            target_kind=plan.target.kind,
            target_id=plan.target.id,
            target_key=plan.target.key,
            target_version=plan.target.version,
            input=validated_input,
            status=_RUN_STATUS_RUNNING,
            resume_step_index=1,
            final_output=None,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
            inherited_tokens=0,
            inherited_cost_usd=Decimal("0"),
            executed_tokens=0,
            executed_cost_usd=Decimal("0"),
            trace_id=None,
            error=None,
            finished_at=None,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
            )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        try:
            self._dispatch_run_in_background(run.id)
        except Exception as exc:
            self._mark_run_failed_in_fresh_session(
                run.id,
                code="run_dispatch_failed",
                message=f"Failed to dispatch run {run.id}: {exc}",
            )
            raise
        return self._to_created_read(run)

    def build_fork_draft(self, source_run_id: int, fork_step_index: int) -> RunForkDraftRead:
        source_run, _plan, source_steps = self._prepare_fork_source(
            source_run_id,
            fork_step_index,
        )
        return RunForkDraftRead.model_validate(
            {
                "sourceRunId": source_run.id,
                "forkStepIndex": fork_step_index,
                "targetKind": source_run.target_kind,
                "targetId": source_run.target_id,
                "targetKey": source_run.target_key,
                "targetVersion": source_run.target_version,
                "input": deepcopy(source_run.input),
                "steps": [
                    {
                        "sourceRunStepId": step.id,
                        "index": step.step_index,
                        "invocations": [
                            {
                                "sourceInvocationId": invocation.id,
                                "stepIndex": invocation.step_index,
                                "slot": invocation.slot,
                                "agentKey": invocation.agent_key,
                                "resolvedInput": deepcopy(invocation.resolved_input),
                                "output": deepcopy(invocation.output),
                            }
                            for invocation in sorted(
                                cast(list[RunAgentInvocation], step.invocations),
                                key=lambda item: (item.position, item.id),
                            )
                        ],
                    }
                    for step in source_steps
                ],
            }
        )

    def create_fork_run(
        self,
        source_run_id: int,
        payload: RunForkCreateRequest,
    ) -> RunCreatedRead:
        fork_step_index = payload.fork_step_index
        source_run, plan, source_steps = self._prepare_fork_source(
            source_run_id,
            fork_step_index,
        )
        edit_map = self._validate_fork_invocation_edits(
            plan=plan,
            source_steps=source_steps,
            edits=payload.invocation_edits,
        )
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=payload.input if payload.input is not None else source_run.input,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        inherited_tokens, inherited_cost = self._copied_invocation_totals(source_steps)
        run = Run(
            target_kind=source_run.target_kind,
            target_id=source_run.target_id,
            target_key=source_run.target_key,
            target_version=source_run.target_version,
            input=validated_input,
            status=_RUN_STATUS_RUNNING,
            source_run_id=source_run.id,
            lineage_root_run_id=source_run.lineage_root_run_id or source_run.id,
            forked_from_step_index=fork_step_index,
            resume_step_index=fork_step_index + 1,
            final_output=None,
            total_tokens=inherited_tokens,
            total_cost_usd=inherited_cost,
            inherited_tokens=inherited_tokens,
            inherited_cost_usd=inherited_cost,
            executed_tokens=0,
            executed_cost_usd=Decimal("0"),
            trace_id=None,
            error=None,
            finished_at=None,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._copy_fork_source_rows(
                run=run,
                source_steps=source_steps,
                edit_map=edit_map,
            )
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
                min_step_index=fork_step_index + 1,
            )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        try:
            self._dispatch_run_in_background(run.id)
        except Exception as exc:
            self._mark_run_failed_in_fresh_session(
                run.id,
                code="run_dispatch_failed",
                message=f"Failed to dispatch run {run.id}: {exc}",
            )
            raise
        return self._to_created_read(run)

    def _create_planned_run_rows(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        validated_input: dict[str, Any],
        min_step_index: int = 1,
    ) -> None:
        plan_steps = [step for step in plan.steps if step.index >= min_step_index]
        planned_steps = self.run_step_repository.create_planned_steps(
            run_id=run.id,
            step_indexes=(step.index for step in plan_steps),
        )
        self.session.flush()
        steps_by_index = {step.step_index: step for step in planned_steps}
        for plan_step in plan_steps:
            run_step = steps_by_index[plan_step.index]
            for position, plan_agent in enumerate(plan_step.agents):
                resolved_input, resolved_input_origin = self._planned_resolved_input(
                    plan_agent=plan_agent,
                    validated_input=validated_input,
                )
                _ = self.run_agent_invocation_repository.create_invocation(
                    run_step_id=run_step.id,
                    run_id=run.id,
                    step_index=plan_step.index,
                    slot=plan_agent.slot,
                    position=position,
                    agent_id=plan_agent.agent_id,
                    agent_key=plan_agent.agent_key,
                    agent_version=plan_agent.agent_version,
                    output_schema_id=plan_agent.output_schema_id,
                    output_schema_version=plan_agent.output_schema_version,
                    input_mode=plan_agent.input_mode,
                    wiring={
                        target_name: self._plan_source_payload(source)
                        for target_name, source in plan_agent.wiring.items()
                    },
                    optional=plan_agent.optional,
                    resolved_input=resolved_input,
                    resolved_input_origin=resolved_input_origin,
                )

    @staticmethod
    def _planned_resolved_input(
        *,
        plan_agent: ExecutionPlanAgent,
        validated_input: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if plan_agent.input_mode == "passthrough":
            return dict(validated_input), "passthrough"
        return {}, "derived"

    def _prepare_fork_source(
        self,
        source_run_id: int,
        fork_step_index: int,
    ) -> tuple[Run, ExecutionPlan, list[RunStep]]:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind != "workflow":
            raise business_rule_error(
                "run_fork_target_kind_unsupported",
                "Workflow-step forks are only supported for workflow runs",
                details=[
                    {
                        "field": "targetKind",
                        "issue": "Workflow-step forks require a workflow source run",
                    }
                ],
            )
        if source_run.status != _RUN_STATUS_SUCCEEDED:
            raise business_rule_error(
                "run_fork_source_not_succeeded",
                "Only succeeded runs can be forked",
            )
        plan = self.execution_plan_builder.build_plan_for_run(source_run)
        plan_step_indexes = {step.index for step in plan.steps}
        final_step_index = max(plan_step_indexes)
        if fork_step_index > final_step_index:
            raise business_rule_error(
                "run_fork_step_not_continuable",
                f"Fork step {fork_step_index} has no following executable workflow step",
                details=[
                    {
                        "field": "forkStepIndex",
                        "issue": "Fork step must have a following workflow step",
                    }
                ],
            )
        if fork_step_index not in plan_step_indexes:
            raise business_rule_error(
                "run_fork_step_not_found",
                f"Fork step {fork_step_index} does not exist on the source run plan",
            )

        source_steps_by_index = {
            step.step_index: step for step in cast(list[RunStep], source_run.steps)
        }
        source_step = source_steps_by_index.get(fork_step_index)
        if source_step is None:
            raise business_rule_error(
                "run_fork_step_not_found",
                f"Fork step {fork_step_index} does not exist on the source run",
            )
        if source_step.status != _RUN_STATUS_SUCCEEDED:
            raise business_rule_error(
                "run_fork_step_not_succeeded",
                f"Fork step {fork_step_index} must be succeeded before it can be copied",
            )

        copied_steps: list[RunStep] = []
        for step_index in sorted(index for index in plan_step_indexes if index <= fork_step_index):
            step = source_steps_by_index.get(step_index)
            if step is None or step.status != _RUN_STATUS_SUCCEEDED or step.persisted_at is None:
                raise business_rule_error(
                    "run_fork_copied_step_not_persisted",
                    "All copied source steps must be succeeded and persisted",
                    details=[{"field": f"steps.{step_index}", "issue": "Step is not persisted"}],
                )
            invocations = cast(list[RunAgentInvocation], step.invocations)
            for invocation in invocations:
                if (
                    invocation.status != _RUN_STATUS_SUCCEEDED
                    or invocation.persisted_at is None
                    or invocation.output_origin is None
                ):
                    raise business_rule_error(
                        "run_fork_copied_output_not_persisted",
                        "All copied source invocation outputs must be succeeded and persisted",
                        details=[
                            {
                                "field": f"steps.{step_index}.{invocation.slot}",
                                "issue": "Invocation output is not persisted",
                            }
                        ],
                    )
            copied_steps.append(step)
        if fork_step_index == final_step_index:
            raise business_rule_error(
                "run_fork_step_not_continuable",
                f"Fork step {fork_step_index} is the final executable workflow step",
                details=[
                    {
                        "field": "forkStepIndex",
                        "issue": "Fork step must have a following workflow step",
                    }
                ],
            )
        return source_run, plan, copied_steps

    def _validate_fork_invocation_edits(
        self,
        *,
        plan: ExecutionPlan,
        source_steps: list[RunStep],
        edits: list[RunForkInvocationEdit],
    ) -> dict[tuple[int, str], RunForkInvocationEdit]:
        source_invocations = {
            (invocation.step_index, invocation.slot): invocation
            for step in source_steps
            for invocation in cast(list[RunAgentInvocation], step.invocations)
        }
        plan_agents = {
            (step.index, agent.slot): agent for step in plan.steps for agent in step.agents
        }
        edit_map: dict[tuple[int, str], RunForkInvocationEdit] = {}
        for edit in edits:
            key = (edit.step_index, edit.slot)
            if key in edit_map:
                raise business_rule_error(
                    "run_fork_duplicate_invocation_edit",
                    "Fork invocation edits must target each slot at most once",
                    details=[{"field": "invocationEdits", "issue": "Duplicate invocation edit"}],
                )
            source_invocation = source_invocations.get(key)
            plan_agent = plan_agents.get(key)
            if source_invocation is None or plan_agent is None:
                raise business_rule_error(
                    "run_fork_invocation_edit_not_found",
                    "Fork invocation edit must target a copied source invocation",
                    details=[
                        {
                            "field": f"steps.{edit.step_index}.{edit.slot}",
                            "issue": "Invocation is not available for copying",
                        }
                    ],
                )
            agent = self._resolve_agent_row(plan_agent)
            if "resolved_input" in edit.model_fields_set:
                input_model = self._build_input_model(
                    agent.input_schema,
                    candidate_key=f"{agent.key}_input",
                )
                try:
                    _ = input_model.model_validate(edit.resolved_input)
                except ValidationError as exc:
                    raise business_rule_error(
                        "run_fork_invalid_resolved_input",
                        "Edited invocation input failed agent input schema validation",
                        details=self._validation_details_from_pydantic_error(exc),
                    ) from exc
            if "output" in edit.model_fields_set:
                output_schema = self._resolve_agent_output_schema(agent)
                output_model = self.schema_compiler.build_runtime_model(output_schema)
                try:
                    _ = output_model.model_validate(edit.output)
                except ValidationError as exc:
                    raise business_rule_error(
                        "run_fork_invalid_output",
                        "Edited invocation output failed agent output schema validation",
                        details=self._validation_details_from_pydantic_error(exc),
                    ) from exc
            edit_map[key] = edit
        return edit_map

    @staticmethod
    def _copied_invocation_totals(source_steps: list[RunStep]) -> tuple[int, Decimal]:
        tokens = 0
        cost = Decimal("0")
        for step in source_steps:
            for invocation in cast(list[RunAgentInvocation], step.invocations):
                tokens += int(invocation.tokens or 0)
                cost += Decimal(invocation.cost_usd or 0)
        return tokens, cost

    def _copy_fork_source_rows(
        self,
        *,
        run: Run,
        source_steps: list[RunStep],
        edit_map: dict[tuple[int, str], RunForkInvocationEdit],
    ) -> None:
        copied_at = utcnow()
        copied_steps: dict[int, RunStep] = {}
        for source_step in source_steps:
            copied_step = RunStep(
                run_id=run.id,
                step_index=source_step.step_index,
                status=source_step.status,
                origin="copied",
                source_run_step_id=source_step.id,
                source_run_id=source_step.run_id,
                source_step_index=source_step.step_index,
                error=source_step.error,
                started_at=source_step.started_at,
                finished_at=source_step.finished_at,
                persisted_at=copied_at,
            )
            self.session.add(copied_step)
            copied_steps[source_step.step_index] = copied_step
        self.session.flush()

        for source_step in source_steps:
            copied_step = copied_steps[source_step.step_index]
            for source_invocation in cast(list[RunAgentInvocation], source_step.invocations):
                edit = edit_map.get((source_invocation.step_index, source_invocation.slot))
                resolved_input_edited = (
                    edit is not None and "resolved_input" in edit.model_fields_set
                )
                output_edited = edit is not None and "output" in edit.model_fields_set
                resolved_input = (
                    edit.resolved_input
                    if resolved_input_edited and edit is not None
                    else source_invocation.resolved_input
                )
                output = (
                    edit.output if output_edited and edit is not None else source_invocation.output
                )
                copied_invocation = self.run_agent_invocation_repository.create_invocation(
                    run_step_id=copied_step.id,
                    run_id=run.id,
                    step_index=source_invocation.step_index,
                    slot=source_invocation.slot,
                    position=source_invocation.position,
                    agent_id=source_invocation.agent_id,
                    agent_key=source_invocation.agent_key,
                    agent_version=source_invocation.agent_version,
                    output_schema_id=source_invocation.output_schema_id,
                    output_schema_version=source_invocation.output_schema_version,
                    input_mode=source_invocation.input_mode,
                    wiring=deepcopy(source_invocation.wiring),
                    optional=source_invocation.optional,
                    resolved_input=deepcopy(resolved_input) if resolved_input is not None else {},
                    resolved_input_origin="edited" if resolved_input_edited else "copied",
                    status=source_invocation.status,
                    output=deepcopy(output),
                    output_origin="edited" if output_edited else "copied",
                    source_invocation_id=source_invocation.id,
                )
                copied_invocation.tokens = source_invocation.tokens
                copied_invocation.cost_usd = source_invocation.cost_usd
                copied_invocation.duration_ms = source_invocation.duration_ms
                copied_invocation.trace_span_id = source_invocation.trace_span_id
                copied_invocation.started_at = source_invocation.started_at
                copied_invocation.finished_at = source_invocation.finished_at
                copied_invocation.persisted_at = copied_at

    def execute_run(self, run_id: int) -> None:
        try:
            asyncio.run(self._execute_run_async(run_id))
        except Exception as exc:
            logger.exception("Agent platform run %d failed", run_id)
            self.session.rollback()
            failure = self._coerce_execution_error(exc)
            self._mark_run_failed_in_fresh_session(
                run_id,
                code=failure.code,
                message=failure.message,
            )

    async def _execute_run_async(self, run_id: int) -> None:
        run = self._get_run_or_raise(run_id)
        plan = self.execution_plan_builder.build_plan_for_run(run)
        try:
            trace_session = self._start_trace_session(run=run, plan=plan)
        except Exception:
            await self._execute_run_with_trace(run=run, plan=plan, trace_id=None)
            return

        with trace_session as run_span:
            trace_id = format_current_trace_id(run_span)
            await self._execute_run_with_trace(run=run, plan=plan, trace_id=trace_id)

    async def _execute_run_with_trace(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        trace_id: str | None,
    ) -> None:
        total_tokens = int(run.inherited_tokens or 0)
        total_cost = Decimal(run.inherited_cost_usd or 0)
        executed_tokens = 0
        executed_cost = Decimal("0")

        for step in plan.steps:
            if step.index < run.resume_step_index:
                continue
            slot_outputs = self._hydrate_slot_outputs(run.id, before_step_index=step.index)
            run_step = self._get_planned_step_or_raise(run_id=run.id, step_index=step.index)
            self._assert_planned_invocations_exist(run_id=run.id, step=step)
            _ = self.run_step_repository.mark_running(run_step)
            self.session.commit()
            step_slot_outputs, step_tokens, step_cost, fatal_error = await self._execute_step(
                run=run,
                plan=plan,
                step=step,
                initial_input=run.input,
                slot_outputs=slot_outputs,
                current_total_cost=total_cost,
                trace_id=trace_id,
            )
            if fatal_error is None:
                _ = self.run_step_repository.persist_success(run_step)
            else:
                _ = self.run_step_repository.persist_failure(run_step, error=fatal_error)
            executed_tokens += step_tokens
            executed_cost += step_cost
            total_tokens += step_tokens
            total_cost += step_cost
            self._sync_run_totals(
                run,
                total_tokens=total_tokens,
                total_cost=total_cost,
                executed_tokens=executed_tokens,
                executed_cost=executed_cost,
            )
            self.session.commit()
            if fatal_error is not None:
                self._skip_pending_steps_after_failure(run_id=run.id, after_step_index=step.index)
                run.status = _RUN_STATUS_FAILED
                run.error = fatal_error
                run.finished_at = utcnow()
                self.session.commit()
                return
            for slot, value in step_slot_outputs.items():
                slot_outputs[(step.index, slot)] = value

        slot_outputs = self._hydrate_slot_outputs(run.id)
        final_output, final_error = self._resolve_final_output(
            plan=plan,
            slot_outputs=slot_outputs,
        )
        self._sync_run_totals(
            run,
            total_tokens=total_tokens,
            total_cost=total_cost,
            executed_tokens=executed_tokens,
            executed_cost=executed_cost,
        )
        if final_error is not None:
            run.status = _RUN_STATUS_FAILED
            run.error = final_error
            run.finished_at = utcnow()
            self.session.commit()
            return

        run.final_output = final_output
        run.status = _RUN_STATUS_SUCCEEDED
        run.trace_id = trace_id
        run.error = None
        run.finished_at = utcnow()
        self.session.commit()

    def _hydrate_slot_outputs(
        self,
        run_id: int,
        *,
        before_step_index: int | None = None,
    ) -> dict[tuple[int, str], Any]:
        slot_outputs = self.run_agent_invocation_repository.hydrate_successful_outputs(
            run_id,
            before_step_index=before_step_index,
        )
        for invocation in self.run_agent_invocation_repository.list_by_run(run_id):
            if before_step_index is not None and invocation.step_index >= before_step_index:
                continue
            if invocation.optional and invocation.status in {"failed", "skipped"}:
                slot_outputs[(invocation.step_index, invocation.slot)] = None
        return slot_outputs

    def _get_planned_step_or_raise(self, *, run_id: int, step_index: int) -> RunStep:
        run_step = self.run_step_repository.get_by_run_step_index(run_id, step_index)
        if run_step is None:
            raise RunExecutionError(
                code="run_planned_step_missing",
                message=f"Run {run_id} is missing planned step {step_index}",
            )
        return run_step

    def _get_planned_invocation_or_raise(
        self,
        *,
        run_id: int,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocation:
        invocation = self.run_agent_invocation_repository.get_by_run_step_slot(
            run_id,
            step_index,
            slot,
        )
        if invocation is None:
            raise RunExecutionError(
                code="run_planned_invocation_missing",
                message=f"Run {run_id} is missing planned invocation {step_index}.{slot}",
            )
        return invocation

    def _assert_planned_invocations_exist(self, *, run_id: int, step: ExecutionPlanStep) -> None:
        for plan_agent in step.agents:
            _ = self._get_planned_invocation_or_raise(
                run_id=run_id,
                step_index=step.index,
                slot=plan_agent.slot,
            )

    def _persist_failed_invocation(
        self,
        invocation: RunAgentInvocation,
        failure: RunExecutionError,
        *,
        tokens: int,
        cost_usd: Decimal,
        duration_ms: int | None,
        trace_span_id: str | None,
    ) -> None:
        _ = self.run_agent_invocation_repository.persist_failure(
            invocation,
            error_code=failure.code,
            error_message=failure.message,
            error_details=list(failure.details),
            tokens=tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            trace_span_id=trace_span_id,
        )

    def _skip_pending_steps_after_failure(self, *, run_id: int, after_step_index: int) -> None:
        for step in self.run_step_repository.list_by_run(run_id):
            if step.step_index <= after_step_index or step.status != "pending":
                continue
            _ = self.run_step_repository.persist_skipped(
                step,
                error="Run failed before this step started",
            )
            for invocation in self.run_agent_invocation_repository.list_by_run_step(
                run_id,
                step.step_index,
            ):
                if invocation.status == "pending":
                    _ = self.run_agent_invocation_repository.persist_skipped(
                        invocation,
                        error_code="run_step_skipped",
                        error_message="Run failed before this invocation started",
                    )

    @staticmethod
    def _runtime_resolved_input_origin(plan_agent: ExecutionPlanAgent) -> str:
        if plan_agent.input_mode == "passthrough":
            return "passthrough"
        return "derived"

    @staticmethod
    def _sync_run_totals(
        run: Run,
        *,
        total_tokens: int,
        total_cost: Decimal,
        executed_tokens: int,
        executed_cost: Decimal,
    ) -> None:
        run.total_tokens = total_tokens
        run.total_cost_usd = total_cost
        run.executed_tokens = executed_tokens
        run.executed_cost_usd = executed_cost
        if run.source_run_id is None:
            run.inherited_tokens = 0
            run.inherited_cost_usd = Decimal("0")
            run.total_tokens = executed_tokens
            run.total_cost_usd = executed_cost

    def _resolve_final_output(
        self,
        *,
        plan: ExecutionPlan,
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any | None, str | None]:
        try:
            source_value, optional_null = self._resolve_final_output_value(
                plan.final_output,
                slot_outputs=slot_outputs,
            )
        except RunExecutionError as exc:
            return None, exc.message
        if optional_null:
            return None, "Final output cannot resolve from a null slot"
        return source_value, None

    async def _execute_step(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        step: ExecutionPlanStep,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        current_total_cost: Decimal,
        trace_id: str | None,
    ) -> tuple[dict[str, Any], int, Decimal, str | None]:
        step_index = step.index
        prepared_invocations: list[_PreparedAgentInvocation] = []
        step_slot_outputs: dict[str, Any] = {}
        fatal_error: str | None = None

        for plan_agent in step.agents:
            invocation = self._get_planned_invocation_or_raise(
                run_id=run.id,
                step_index=step_index,
                slot=plan_agent.slot,
            )
            prepared, failure = self._prepare_agent_invocation(
                runtime_context=_RuntimeInvocationContext(
                    run_id=run.id,
                    target_kind=plan.target.kind,
                    target_key=plan.target.key,
                    target_version=plan.target.version,
                ),
                step_index=step_index,
                plan_agent=plan_agent,
                invocation=invocation,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if prepared is None:
                assert failure is not None
                self._persist_failed_invocation(
                    invocation,
                    failure,
                    tokens=0,
                    cost_usd=Decimal("0"),
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[plan_agent.slot] = None
                if not plan_agent.optional and fatal_error is None:
                    fatal_error = failure.message
                continue
            _ = self.run_agent_invocation_repository.mark_running(
                invocation,
                resolved_input=prepared.resolved_input,
                resolved_input_origin=self._runtime_resolved_input_origin(plan_agent),
            )
            prepared_invocations.append(prepared)

        self.session.commit()
        results = await asyncio.gather(
            *(
                self._execute_invocation(prepared, trace_id=trace_id)
                for prepared in prepared_invocations
            ),
            return_exceptions=True,
        )

        step_tokens = 0
        step_cost = Decimal("0")
        for index, prepared in enumerate(prepared_invocations):
            result = results[index]
            if isinstance(result, Exception):
                failure = self._coerce_execution_error(result)
                self._persist_failed_invocation(
                    prepared.invocation,
                    failure,
                    tokens=0,
                    cost_usd=Decimal("0"),
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[prepared.slot] = None
                if not prepared.optional and fatal_error is None:
                    fatal_error = failure.message
                continue

            assert isinstance(result, RunAgentInvocationResult)
            step_tokens += result.tokens
            step_cost += result.cost_usd
            budget_failure = self._check_budget(
                agent=prepared.agent,
                aggregate_budget_usd=plan.aggregate_budget_usd,
                agent_cost=result.cost_usd,
                projected_total_cost=current_total_cost + step_cost,
            )
            if budget_failure is not None:
                if budget_failure.trace_span_id is None:
                    budget_failure.trace_span_id = result.trace_span_id
                self._persist_failed_invocation(
                    prepared.invocation,
                    budget_failure,
                    tokens=result.tokens,
                    cost_usd=result.cost_usd,
                    duration_ms=result.duration_ms,
                    trace_span_id=result.trace_span_id,
                )
                step_slot_outputs[prepared.slot] = None
                if fatal_error is None:
                    fatal_error = budget_failure.message
                continue

            _ = self.run_agent_invocation_repository.persist_success(
                prepared.invocation,
                output=result.output,
                output_origin="executed",
                tokens=result.tokens,
                cost_usd=result.cost_usd,
                duration_ms=result.duration_ms,
                trace_span_id=result.trace_span_id,
            )
            step_slot_outputs[prepared.slot] = result.output

        return step_slot_outputs, step_tokens, step_cost, fatal_error

    def _prepare_agent_invocation(
        self,
        *,
        runtime_context: _RuntimeInvocationContext,
        step_index: int,
        plan_agent: ExecutionPlanAgent,
        invocation: RunAgentInvocation,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[_PreparedAgentInvocation | None, RunExecutionError | None]:
        try:
            agent = self._resolve_agent_row(plan_agent)
            output_schema = self._resolve_agent_output_schema(agent)
            output_model = self.schema_compiler.build_runtime_model(output_schema)
            input_model = self._build_input_model(
                agent.input_schema,
                candidate_key=f"{agent.key}_input",
            )
            input_node = self.schema_compiler.parse_json_schema_node(
                agent.input_schema,
                path=f"steps[{step_index - 1}].{agent.key}.inputSchema",
            )
            resolved_input = self._resolve_agent_input(
                step_index=step_index,
                plan_agent=plan_agent,
                input_node=input_node,
                input_model=input_model,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            return (
                _PreparedAgentInvocation(
                    agent=agent,
                    output_model=output_model,
                    resolved_input=resolved_input,
                    invocation=invocation,
                    optional=plan_agent.optional,
                    step_index=step_index,
                    slot=plan_agent.slot,
                    runtime_context=runtime_context,
                ),
                None,
            )
        except RunExecutionError as exc:
            return None, exc
        except OutputSchemaCompilerError as exc:
            failure = RunExecutionError(
                code="agent_schema_build_failed",
                message=str(exc),
            )
            return None, failure

    def _resolve_agent_input(
        self,
        *,
        step_index: int,
        plan_agent: ExecutionPlanAgent,
        input_node: SchemaNode,
        input_model: type[BaseModel],
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> dict[str, Any]:
        if plan_agent.input_mode == "passthrough":
            try:
                validated = input_model.model_validate(initial_input)
            except ValidationError as exc:
                raise RunExecutionError(
                    code="agent_input_validation_failed",
                    message="Resolved agent input failed schema validation",
                    details=self._validation_details_from_pydantic_error(exc),
                ) from exc
            return validated.model_dump(mode="json", exclude_none=True)

        if plan_agent.input_mode != "wired":
            raise RunExecutionError(
                code="agent_input_mode_invalid",
                message=f"Unsupported plan input mode {plan_agent.input_mode!r}",
            )

        target_fields = self._object_field_map(input_node)
        wiring = dict(plan_agent.wiring)
        agent_field_prefix = f"steps[{step_index - 1}].agents.{plan_agent.slot}.wiring"
        for target_name in wiring:
            if target_name not in target_fields:
                raise RunExecutionError(
                    code="agent_input_unknown_field",
                    message=f"Input field {target_name!r} is not defined on the agent schema",
                    details=[
                        {
                            "field": f"{agent_field_prefix}.{target_name}",
                            "issue": "Input field is not defined on the agent schema",
                        }
                    ],
                )

        payload: dict[str, Any] = {}
        for target_name, target_field in target_fields.items():
            source = wiring.get(target_name)
            if source is None:
                if target_field.required:
                    raise RunExecutionError(
                        code="agent_input_missing_required_field",
                        message=f"Required input field {target_name!r} is not wired",
                        details=[
                            {
                                "field": f"{agent_field_prefix}.{target_name}",
                                "issue": "Required input field is not wired",
                            }
                        ],
                    )
                continue

            value, optional_null = self._resolve_source_value(
                self._plan_source_payload(source),
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if optional_null:
                if target_field.required:
                    raise RunExecutionError(
                        code="agent_optional_source_required",
                        message="Optional slot failure left a required downstream field unresolved",
                        details=[
                            {
                                "field": f"{agent_field_prefix}.{target_name}",
                                "issue": (
                                    "Optional slot failure cannot satisfy a required " "input field"
                                ),
                            }
                        ],
                    )
                continue
            payload[target_name] = value

        try:
            validated = input_model.model_validate(payload)
        except ValidationError as exc:
            raise RunExecutionError(
                code="agent_input_validation_failed",
                message="Resolved agent input failed schema validation",
                details=self._validation_details_from_pydantic_error(exc),
            ) from exc
        return validated.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _plan_source_payload(source: ExecutionPlanSource) -> dict[str, Any]:
        payload: dict[str, Any] = {"from": source.source}
        if source.path is not None:
            payload["path"] = source.path
        if source.step_index is not None:
            payload["stepIndex"] = source.step_index
        if source.slot is not None:
            payload["slot"] = source.slot
        return payload

    def _resolve_final_output_value(
        self,
        final_output: ExecutionPlanFinalOutput,
        *,
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any, bool]:
        key = (final_output.step_index, final_output.slot)
        if key not in slot_outputs:
            raise RunExecutionError(
                code="run_source_slot_missing",
                message=(
                    f"Slot {final_output.slot!r} from step {final_output.step_index} "
                    "is not available"
                ),
                details=[
                    {
                        "field": f"step.{final_output.step_index}.{final_output.slot}",
                        "issue": "Referenced slot is not available in the current run state",
                    }
                ],
            )

        base_value = slot_outputs[key]
        if base_value is None:
            return None, True
        if final_output.path is None:
            return base_value, False
        return self._resolve_value_path(base_value, final_output.path), False

    def _resolve_source_value(
        self,
        source: dict[str, Any],
        *,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any, bool]:
        source_kind = str(source.get("from", "")).strip().lower()
        path = source.get("path")
        if source_kind == "input":
            base_value = initial_input
        elif source_kind == "step":
            step_index = int(source["stepIndex"])
            slot = str(source["slot"])
            key = (step_index, slot)
            if key not in slot_outputs:
                raise RunExecutionError(
                    code="run_source_slot_missing",
                    message=f"Slot {slot!r} from step {step_index} is not available",
                    details=[
                        {
                            "field": f"step.{step_index}.{slot}",
                            "issue": "Referenced slot is not available in the current run state",
                        }
                    ],
                )
            base_value = slot_outputs[key]
            if base_value is None:
                return None, True
        else:
            raise RunExecutionError(
                code="run_source_kind_invalid",
                message=f"Unsupported workflow source kind {source_kind!r}",
            )

        if path is None:
            return base_value, False
        if base_value is None:
            return None, True
        return self._resolve_value_path(base_value, str(path)), False

    @staticmethod
    def _resolve_value_path(value: Any, path: str) -> Any:
        current = value
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                raise RunExecutionError(
                    code="run_source_path_invalid",
                    message=f"Resolved source path {path!r} is not available in the source payload",
                )
            current = current[segment]
        return current

    async def _execute_invocation(
        self,
        prepared: _PreparedAgentInvocation,
        *,
        trace_id: str | None,
    ) -> RunAgentInvocationResult:
        if trace_id is None:
            return await self._execute_invocation_with_trace_span(
                prepared,
                trace_id=trace_id,
                trace_span_id=None,
            )

        with create_logfire_span(
            "Run step {step_index} slot {slot} agent {agent_key}",
            step_index=prepared.step_index,
            slot=prepared.slot,
            agent_key=prepared.agent.key,
            run_trace_id=trace_id,
        ) as invocation_span:
            return await self._execute_invocation_with_trace_span(
                prepared,
                trace_id=trace_id,
                trace_span_id=format_current_span_id(invocation_span),
            )

    async def _execute_invocation_with_trace_span(
        self,
        prepared: _PreparedAgentInvocation,
        *,
        trace_id: str | None,
        trace_span_id: str | None,
    ) -> RunAgentInvocationResult:
        try:
            context_token = _CURRENT_RUNTIME_INVOCATION_CONTEXT.set(prepared.runtime_context)
            try:
                raw_result = await self._invoke_agent(
                    agent=prepared.agent,
                    resolved_input=prepared.resolved_input,
                    output_model=prepared.output_model,
                    trace_id=trace_id,
                    step_index=prepared.step_index,
                    slot=prepared.slot,
                )
            finally:
                _CURRENT_RUNTIME_INVOCATION_CONTEXT.reset(context_token)
            result = self._coerce_invocation_result(raw_result)
            validated_output = prepared.output_model.model_validate(result.output)
        except ValidationError as exc:
            raise RunExecutionError(
                code="agent_output_validation_failed",
                message="Agent output failed schema validation",
                details=self._validation_details_from_pydantic_error(exc),
                trace_span_id=trace_span_id,
            ) from exc
        except RunExecutionError as exc:
            if exc.trace_span_id is None:
                exc.trace_span_id = trace_span_id
            raise
        except Exception as exc:
            raise RunExecutionError(
                code="agent_execution_failed",
                message=str(exc),
                trace_span_id=trace_span_id,
            ) from exc
        return RunAgentInvocationResult(
            output=validated_output.model_dump(mode="json"),
            tokens=result.tokens,
            cost_usd=result.cost_usd,
            duration_ms=result.duration_ms,
            trace_span_id=trace_span_id,
        )

    async def _invoke_agent(
        self,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocationResult:
        runtime_context = _CURRENT_RUNTIME_INVOCATION_CONTEXT.get()
        workflow_key = (
            runtime_context.target_key
            if runtime_context is not None and runtime_context.target_kind == "workflow"
            else None
        )
        workflow_version = (
            runtime_context.target_version
            if runtime_context is not None and runtime_context.target_kind == "workflow"
            else None
        )
        return await self.agent_execution_service.invoke(
            agent=agent,
            resolved_input=resolved_input,
            output_model=output_model,
            trace_id=trace_id,
            step_index=step_index,
            slot=slot,
            openai_client_factory=OpenAI,
            run_id=None if runtime_context is None else runtime_context.run_id,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
        )

    @staticmethod
    def _coerce_invocation_result(raw_result: Any) -> RunAgentInvocationResult:
        return normalize_agent_invocation_result(raw_result)

    def _check_budget(
        self,
        *,
        agent: Agent,
        aggregate_budget_usd: Decimal,
        agent_cost: Decimal,
        projected_total_cost: Decimal,
    ) -> RunExecutionError | None:
        if agent_cost > agent.budget_usd:
            budget_text = decimal_to_string(agent.budget_usd)
            return RunExecutionError(
                code="agent_budget_exceeded",
                message=f"Agent {agent.key!r} exceeded its budget of {budget_text} USD",
            )
        if projected_total_cost > aggregate_budget_usd:
            return RunExecutionError(
                code="run_budget_exceeded",
                message=(
                    f"Run exceeded the workflow aggregate budget of "
                    f"{decimal_to_string(aggregate_budget_usd)} USD"
                ),
            )
        return None

    @staticmethod
    def _apply_failed_entry(
        entry: dict[str, Any],
        failure: RunExecutionError,
        *,
        tokens: int,
        cost_usd: Decimal,
        duration_ms: int | None,
        trace_span_id: str | None,
    ) -> None:
        entry["output"] = None
        entry["error"] = {
            "code": failure.code,
            "message": failure.message,
            "details": list(failure.details),
        }
        entry["status"] = _RUN_STATUS_FAILED
        entry["tokens"] = tokens
        entry["costUsd"] = decimal_to_string(cost_usd)
        entry["durationMs"] = duration_ms
        entry["traceSpanId"] = trace_span_id

    def _resolve_agent_row(self, plan_agent: ExecutionPlanAgent) -> Agent:
        agent = self.agent_repository.get_by_key_version(
            plan_agent.agent_key,
            plan_agent.agent_version,
        )
        if agent is None:
            raise RunExecutionError(
                code="run_agent_missing",
                message=(
                    f"Agent {plan_agent.agent_key!r} version "
                    f"{plan_agent.agent_version} was not found"
                ),
            )
        return agent

    def _resolve_agent_output_schema(self, agent: Agent) -> OutputSchema:
        output_schema = self.output_schema_repository.get(agent.output_schema_id)
        if output_schema is None or output_schema.version != agent.output_schema_version:
            raise RunExecutionError(
                code="run_output_schema_missing",
                message=f"Agent {agent.key!r} references a missing output schema version",
            )
        return output_schema

    def _validate_run_input(
        self,
        *,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
        candidate_key: str,
        resource_name: str,
    ) -> dict[str, Any]:
        input_model = self._build_input_model(input_schema, candidate_key=candidate_key)
        try:
            validated = input_model.model_validate(input_payload)
        except ValidationError as exc:
            raise business_rule_error(
                "run_invalid_input",
                f"Run input failed {resource_name} input schema validation",
                details=self._validation_details_from_pydantic_error(exc),
            ) from exc
        return validated.model_dump(mode="json")

    def _build_input_model(
        self,
        input_schema: dict[str, Any],
        *,
        candidate_key: str,
    ) -> type[BaseModel]:
        candidate = OutputSchema(
            key=candidate_key,
            version=1,
            status="published",
            kind="standalone",
            name="Run Input Schema",
            description="Run input schema validation candidate",
            json_schema=input_schema,
            registry_refs=[],
        )
        return self.schema_compiler.build_runtime_model(candidate)

    def _object_field_map(self, node: SchemaNode) -> dict[str, SchemaField]:
        dereferenced = self._dereference_node(node)
        if not isinstance(dereferenced, SchemaObject):
            raise RunExecutionError(
                code="agent_input_schema_invalid",
                message="Agent input schema must be an object schema",
            )
        return {field.name: field for field in dereferenced.fields}

    def _dereference_node(self, node: SchemaNode) -> SchemaNode:
        current = node
        while isinstance(current, SchemaRef):
            cache_key = (current.key, current.version)
            cached = self._stored_schema_node_cache.get(cache_key)
            if cached is None:
                row = self.output_schema_repository.resolve_registry_ref(
                    current.key,
                    current.version,
                )
                if row is None:
                    raise RunExecutionError(
                        code="run_registry_ref_missing",
                        message=(
                            f"Shared registry ref {current.key!r} v{current.version} "
                            "was not found"
                        ),
                    )
                cached = self.schema_compiler.parse_stored_schema_node(row)
                self._stored_schema_node_cache[cache_key] = cached
            current = cached
        return current

    def _dispatch_run_in_background(self, run_id: int) -> None:
        def _run() -> None:
            with self.session_factory() as session:
                RunService(
                    session,
                    self.session_factory,
                    quote_provider=self.quote_provider,
                ).execute_run(run_id)

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"ledger-agent-platform-run-{run_id}",
        )
        thread.start()

    def _mark_run_failed_in_fresh_session(self, run_id: int, *, code: str, message: str) -> None:
        with self.session_factory() as session:
            service = RunService(session, self.session_factory, quote_provider=self.quote_provider)
            run = service.run_repository.get(run_id)
            if run is None or run.status != _RUN_STATUS_RUNNING:
                return
            run.status = _RUN_STATUS_FAILED
            run.error = message
            run.finished_at = utcnow()
            session.commit()

    @staticmethod
    def _start_trace_session(*, run: Run, plan: ExecutionPlan) -> Any:
        configure_logfire()
        if plan.target.kind == "workflow":
            return create_logfire_span(
                "Workflow run {workflow_key} v{workflow_version} #{run_id}",
                workflow_id=plan.target.id,
                workflow_key=plan.target.key,
                workflow_version=plan.target.version,
                run_id=run.id,
                run_status=run.status,
            )
        return create_logfire_span(
            "Agent run {agent_key} v{agent_version} #{run_id}",
            agent_id=plan.target.id,
            agent_key=plan.target.key,
            agent_version=plan.target.version,
            run_id=run.id,
            run_status=run.status,
        )

    @staticmethod
    def _coerce_execution_error(exc: Exception) -> RunExecutionError:
        if isinstance(exc, RunExecutionError):
            return exc
        if isinstance(exc, ExecutionPlanBuilderError):
            return RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details),
            )
        return RunExecutionError(code="agent_execution_failed", message=str(exc))

    @staticmethod
    def _error_payload(error: RunExecutionError) -> dict[str, Any]:
        return {"code": error.code, "message": error.message, "details": list(error.details)}

    @staticmethod
    def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, str]]:
        details: list[dict[str, str]] = []
        for error in exc.errors():
            location = error.get("loc", ())
            field = ".".join(str(part) for part in location) if location else "input"
            details.append(
                {
                    "field": field or "input",
                    "issue": str(error.get("msg", "Invalid value")),
                }
            )
        return details

    def _get_run_or_raise(self, run_id: int) -> Run:
        run = self.run_repository.get_detail(run_id)
        if run is None:
            raise not_found_error("Run")
        return run

    @staticmethod
    def _build_step_entry(
        *,
        plan_agent: ExecutionPlanAgent,
        resolved_input: dict[str, Any],
        status: str = _RUN_STATUS_RUNNING,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "slot": plan_agent.slot,
            "agentId": plan_agent.agent_id,
            "agentKey": plan_agent.agent_key,
            "agentVersion": plan_agent.agent_version,
            "outputSchemaId": plan_agent.output_schema_id,
            "outputSchemaVersion": plan_agent.output_schema_version,
            "resolvedInput": resolved_input,
            "output": None,
            "error": error,
            "status": status,
            "tokens": 0,
            "costUsd": decimal_to_string(Decimal("0")),
            "durationMs": None,
            "traceSpanId": None,
        }

    @staticmethod
    def _to_created_read(run: Run) -> RunCreatedRead:
        return RunCreatedRead.model_validate(
            {
                "id": run.id,
                "status": run.status,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "traceId": run.trace_id,
                "createdAt": run.created_at,
            }
        )

    @staticmethod
    def _to_list_item(run: Run) -> RunListItemRead:
        return RunListItemRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "status": run.status,
                "totalTokens": run.total_tokens,
                "totalCostUsd": run.total_cost_usd,
                "traceId": run.trace_id,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
            }
        )

    @staticmethod
    def _to_read_model(run: Run) -> RunRead:
        return RunRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "input": run.input,
                "sourceRunId": run.source_run_id,
                "lineageRootRunId": run.lineage_root_run_id,
                "forkedFromStepIndex": run.forked_from_step_index,
                "resumeStepIndex": run.resume_step_index,
                "finalOutput": run.final_output,
                "status": run.status,
                "totalTokens": run.total_tokens,
                "totalCostUsd": run.total_cost_usd,
                "inheritedTokens": run.inherited_tokens,
                "inheritedCostUsd": run.inherited_cost_usd,
                "executedTokens": run.executed_tokens,
                "executedCostUsd": run.executed_cost_usd,
                "traceId": run.trace_id,
                "error": run.error,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
                "createdAt": run.created_at,
                "updatedAt": run.updated_at,
                "steps": [
                    RunService._to_step_read(step)
                    for step in sorted(
                        cast(list[RunStep], run.steps),
                        key=lambda item: (item.step_index, item.id),
                    )
                ],
            }
        )

    @staticmethod
    def _to_step_read(step: RunStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "runId": step.run_id,
            "index": step.step_index,
            "status": step.status,
            "origin": step.origin,
            "sourceRunStepId": step.source_run_step_id,
            "sourceRunId": step.source_run_id,
            "sourceStepIndex": step.source_step_index,
            "error": step.error,
            "startedAt": step.started_at,
            "finishedAt": step.finished_at,
            "persistedAt": step.persisted_at,
            "createdAt": step.created_at,
            "updatedAt": step.updated_at,
            "invocations": [
                RunService._to_invocation_read(invocation)
                for invocation in sorted(
                    cast(list[RunAgentInvocation], step.invocations),
                    key=lambda item: (item.position, item.id),
                )
            ],
        }

    @staticmethod
    def _to_invocation_read(invocation: RunAgentInvocation) -> dict[str, Any]:
        return {
            "id": invocation.id,
            "runStepId": invocation.run_step_id,
            "runId": invocation.run_id,
            "stepIndex": invocation.step_index,
            "slot": invocation.slot,
            "position": invocation.position,
            "agentId": invocation.agent_id,
            "agentKey": invocation.agent_key,
            "agentVersion": invocation.agent_version,
            "outputSchemaId": invocation.output_schema_id,
            "outputSchemaVersion": invocation.output_schema_version,
            "inputMode": invocation.input_mode,
            "wiring": invocation.wiring,
            "optional": invocation.optional,
            "status": invocation.status,
            "resolvedInput": invocation.resolved_input,
            "resolvedInputOrigin": invocation.resolved_input_origin,
            "output": invocation.output,
            "outputOrigin": invocation.output_origin,
            "errorCode": invocation.error_code,
            "errorMessage": invocation.error_message,
            "errorDetails": invocation.error_details,
            "tokens": invocation.tokens,
            "costUsd": invocation.cost_usd,
            "durationMs": invocation.duration_ms,
            "traceSpanId": invocation.trace_span_id,
            "sourceInvocationId": invocation.source_invocation_id,
            "startedAt": invocation.started_at,
            "finishedAt": invocation.finished_at,
            "persistedAt": invocation.persisted_at,
            "createdAt": invocation.created_at,
            "updatedAt": invocation.updated_at,
        }


__all__ = ["RunAgentInvocationResult", "RunExecutionError", "RunService"]
