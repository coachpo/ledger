from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

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
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.schemas.run import (
    RunCreatedRead,
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

logger = logging.getLogger(__name__)

_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"


@dataclass
class _PreparedAgentInvocation:
    agent: Agent
    output_model: type[BaseModel]
    resolved_input: dict[str, Any]
    entry: dict[str, Any]
    optional: bool
    step_index: int
    slot: str


class RunService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.run_repository = RunRepository(session)
        self.execution_plan_builder = ExecutionPlanBuilder(session)
        self.agent_execution_service = AgentExecutionService(self.session_factory)
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
            per_step_outputs={},
            final_output=None,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
            trace_id=None,
            error=None,
            finished_at=None,
        )
        try:
            self.run_repository.add(run)
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
        slot_outputs: dict[tuple[int, str], Any] = {}
        total_tokens = 0
        total_cost = Decimal("0")

        for step in plan.steps:
            (
                step_entries,
                step_slot_outputs,
                step_tokens,
                step_cost,
                fatal_error,
            ) = await self._execute_step(
                plan=plan,
                step=step,
                initial_input=run.input,
                slot_outputs=slot_outputs,
                current_total_cost=total_cost,
                trace_id=trace_id,
            )
            step_index = step.index
            persisted_outputs = dict(run.per_step_outputs)
            persisted_outputs[str(step_index)] = step_entries
            run.per_step_outputs = persisted_outputs
            total_tokens += step_tokens
            total_cost += step_cost
            run.total_tokens = total_tokens
            run.total_cost_usd = total_cost
            self.session.commit()
            for slot, value in step_slot_outputs.items():
                slot_outputs[(step_index, slot)] = value
            if fatal_error is not None:
                run.status = _RUN_STATUS_FAILED
                run.error = fatal_error
                run.finished_at = utcnow()
                self.session.commit()
                return

        final_output, final_error = self._resolve_final_output(
            plan=plan,
            slot_outputs=slot_outputs,
        )
        run.total_tokens = total_tokens
        run.total_cost_usd = total_cost
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
        plan: ExecutionPlan,
        step: ExecutionPlanStep,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        current_total_cost: Decimal,
        trace_id: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], int, Decimal, str | None]:
        step_index = step.index
        entries: list[dict[str, Any]] = []
        prepared_invocations: list[_PreparedAgentInvocation] = []
        step_slot_outputs: dict[str, Any] = {}
        fatal_error: str | None = None

        for plan_agent in step.agents:
            prepared, entry = self._prepare_agent_invocation(
                step_index=step_index,
                plan_agent=plan_agent,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            entries.append(entry)
            if prepared is None:
                step_slot_outputs[plan_agent.slot] = None
                if not plan_agent.optional and fatal_error is None:
                    fatal_error = str(entry["error"]["message"])
                continue
            prepared_invocations.append(prepared)

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
            entry = prepared.entry
            if isinstance(result, Exception):
                failure = self._coerce_execution_error(result)
                self._apply_failed_entry(
                    entry,
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
                self._apply_failed_entry(
                    entry,
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

            entry["output"] = result.output
            entry["error"] = None
            entry["status"] = _RUN_STATUS_SUCCEEDED
            entry["tokens"] = result.tokens
            entry["costUsd"] = decimal_to_string(result.cost_usd)
            entry["durationMs"] = result.duration_ms
            entry["traceSpanId"] = result.trace_span_id
            step_slot_outputs[prepared.slot] = result.output

        return entries, step_slot_outputs, step_tokens, step_cost, fatal_error

    def _prepare_agent_invocation(
        self,
        *,
        step_index: int,
        plan_agent: ExecutionPlanAgent,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[_PreparedAgentInvocation | None, dict[str, Any]]:
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
            entry = self._build_step_entry(plan_agent=plan_agent, resolved_input=resolved_input)
            return (
                _PreparedAgentInvocation(
                    agent=agent,
                    output_model=output_model,
                    resolved_input=resolved_input,
                    entry=entry,
                    optional=plan_agent.optional,
                    step_index=step_index,
                    slot=plan_agent.slot,
                ),
                entry,
            )
        except RunExecutionError as exc:
            entry = self._build_step_entry(
                plan_agent=plan_agent,
                resolved_input={},
                status=_RUN_STATUS_FAILED,
                error=self._error_payload(exc),
            )
            return None, entry
        except OutputSchemaCompilerError as exc:
            failure = RunExecutionError(
                code="agent_schema_build_failed",
                message=str(exc),
            )
            entry = self._build_step_entry(
                plan_agent=plan_agent,
                resolved_input={},
                status=_RUN_STATUS_FAILED,
                error=self._error_payload(failure),
            )
            return None, entry

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
            raw_result = await self._invoke_agent(
                agent=prepared.agent,
                resolved_input=prepared.resolved_input,
                output_model=prepared.output_model,
                trace_id=trace_id,
                step_index=prepared.step_index,
                slot=prepared.slot,
            )
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
        return await self.agent_execution_service.invoke(
            agent=agent,
            resolved_input=resolved_input,
            output_model=output_model,
            trace_id=trace_id,
            step_index=step_index,
            slot=slot,
            openai_client_factory=OpenAI,
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
                RunService(session, self.session_factory).execute_run(run_id)

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"ledger-agent-platform-run-{run_id}",
        )
        thread.start()

    def _mark_run_failed_in_fresh_session(self, run_id: int, *, code: str, message: str) -> None:
        with self.session_factory() as session:
            service = RunService(session, self.session_factory)
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
                "perStepOutputs": run.per_step_outputs,
                "finalOutput": run.final_output,
                "status": run.status,
                "totalTokens": run.total_tokens,
                "totalCostUsd": run.total_cost_usd,
                "traceId": run.trace_id,
                "error": run.error,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
                "createdAt": run.created_at,
                "updatedAt": run.updated_at,
            }
        )


__all__ = ["RunAgentInvocationResult", "RunExecutionError", "RunService"]
