from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import decimal_to_string, parse_decimal_string, utcnow
from app.core.telemetry import (
    configure_logfire,
    create_logfire_span,
    format_current_span_id,
    format_current_trace_id,
)
from app.db.engine import get_session_factory
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.run import RunCreatedRead, RunListItemRead, RunListRead, RunRead, RunStatus
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    SchemaField,
    SchemaNode,
    SchemaObject,
    SchemaRef,
)
from app.services.stock_analysis_reference import (
    StockAnalysisReferenceError,
    StockAnalysisReferenceService,
)

logger = logging.getLogger(__name__)

_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"


class RunExecutionError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        trace_span_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])
        self.trace_span_id = trace_span_id


@dataclass
class RunAgentInvocationResult:
    output: Any
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    duration_ms: int | None = None
    trace_span_id: str | None = None


@dataclass
class _PreparedAgentInvocation:
    agent: Agent
    output_model: type[BaseModel]
    resolved_input: dict[str, Any]
    entry: dict[str, Any]
    optional: bool
    step_index: int
    slot: str


@dataclass(frozen=True)
class _ResolvedModelConnectionConfig:
    id: int
    name: str
    base_url: str
    organization: str | None
    project: str | None
    model_id: str
    reasoning_effort: str
    timeout_seconds: int
    api_key: str | None


class RunService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.workflow_repository = WorkflowRepository(session)
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.run_repository = RunRepository(session)
        self.schema_compiler = OutputSchemaCompiler(self.output_schema_repository)
        self._stored_schema_node_cache: dict[tuple[str, int], SchemaNode] = {}

    def list_runs(
        self,
        *,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
        status_filter: RunStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> RunListRead:
        runs = self.run_repository.list_all(
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
        workflow = self._resolve_workflow(workflow_id, version=version)
        validated_input = self._validate_workflow_input(workflow.input_schema, input_payload)
        run = Run(
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            workflow_version=workflow.version,
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
        workflow = self._get_workflow_for_run(run)
        try:
            trace_session = self._start_trace_session(run=run, workflow=workflow)
        except Exception:
            await self._execute_run_with_trace(run=run, workflow=workflow, trace_id=None)
            return

        with trace_session as run_span:
            trace_id = format_current_trace_id(run_span)
            await self._execute_run_with_trace(run=run, workflow=workflow, trace_id=trace_id)

    async def _execute_run_with_trace(
        self,
        *,
        run: Run,
        workflow: Workflow,
        trace_id: str | None,
    ) -> None:
        slot_outputs: dict[tuple[int, str], Any] = {}
        total_tokens = 0
        total_cost = Decimal("0")

        for raw_step in workflow.steps:
            (
                step_entries,
                step_slot_outputs,
                step_tokens,
                step_cost,
                fatal_error,
            ) = await self._execute_step(
                workflow=workflow,
                raw_step=raw_step,
                initial_input=run.input,
                slot_outputs=slot_outputs,
                current_total_cost=total_cost,
                trace_id=trace_id,
            )
            step_index = int(raw_step["index"])
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

        (
            final_output,
            final_entries,
            final_tokens,
            final_cost,
            final_error,
        ) = await self._resolve_final_output(
            workflow=workflow,
            initial_input=run.input,
            slot_outputs=slot_outputs,
            current_total_cost=total_cost,
            trace_id=trace_id,
        )
        if final_entries is not None:
            final_step_index = len(workflow.steps) + 1
            persisted_outputs = dict(run.per_step_outputs)
            persisted_outputs[str(final_step_index)] = final_entries
            run.per_step_outputs = persisted_outputs
        total_tokens += final_tokens
        total_cost += final_cost
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

    async def _resolve_final_output(
        self,
        *,
        workflow: Workflow,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        current_total_cost: Decimal,
        trace_id: str | None,
    ) -> tuple[Any | None, list[dict[str, Any]] | None, int, Decimal, str | None]:
        output_spec = workflow.output_spec
        if output_spec.get("kind") == "slot":
            try:
                source_value, optional_null = self._resolve_source_value(
                    {
                        "from": "step",
                        "stepIndex": int(output_spec["stepIndex"]),
                        "slot": str(output_spec["slot"]),
                        "path": output_spec.get("path"),
                    },
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                )
            except RunExecutionError as exc:
                return None, None, 0, Decimal("0"), exc.message
            if optional_null:
                return None, None, 0, Decimal("0"), "Final output cannot resolve from a null slot"
            return source_value, None, 0, Decimal("0"), None

        final_step = {
            "index": len(workflow.steps) + 1,
            "agents": [
                {
                    "slot": "final_output",
                    "agentId": int(output_spec["agentId"]),
                    "agentKey": str(output_spec["agentKey"]),
                    "agentVersion": int(output_spec["agentVersion"]),
                    "outputSchemaId": int(output_spec["outputSchemaId"]),
                    "outputSchemaVersion": int(output_spec["outputSchemaVersion"]),
                    "wiring": dict(output_spec.get("wiring") or {}),
                    "optional": False,
                }
            ],
        }
        entries, step_slot_outputs, step_tokens, step_cost, fatal_error = await self._execute_step(
            workflow=workflow,
            raw_step=final_step,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            current_total_cost=current_total_cost,
            trace_id=trace_id,
        )
        return (
            step_slot_outputs.get("final_output"),
            entries,
            step_tokens,
            step_cost,
            fatal_error,
        )

    async def _execute_step(
        self,
        *,
        workflow: Workflow,
        raw_step: dict[str, Any],
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        current_total_cost: Decimal,
        trace_id: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], int, Decimal, str | None]:
        step_index = int(raw_step["index"])
        entries: list[dict[str, Any]] = []
        prepared_invocations: list[_PreparedAgentInvocation] = []
        step_slot_outputs: dict[str, Any] = {}
        fatal_error: str | None = None

        for raw_agent in raw_step.get("agents") or []:
            prepared, entry = self._prepare_agent_invocation(
                step_index=step_index,
                raw_agent=raw_agent,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            entries.append(entry)
            if prepared is None:
                step_slot_outputs[str(raw_agent["slot"])] = None
                if not bool(raw_agent.get("optional", False)) and fatal_error is None:
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
                workflow=workflow,
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
        raw_agent: dict[str, Any],
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[_PreparedAgentInvocation | None, dict[str, Any]]:
        try:
            agent = self._resolve_agent_row(raw_agent)
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
                raw_agent=raw_agent,
                input_node=input_node,
                input_model=input_model,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            entry = self._build_step_entry(raw_agent=raw_agent, resolved_input=resolved_input)
            return (
                _PreparedAgentInvocation(
                    agent=agent,
                    output_model=output_model,
                    resolved_input=resolved_input,
                    entry=entry,
                    optional=bool(raw_agent.get("optional", False)),
                    step_index=step_index,
                    slot=str(raw_agent["slot"]),
                ),
                entry,
            )
        except RunExecutionError as exc:
            entry = self._build_step_entry(
                raw_agent=raw_agent,
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
                raw_agent=raw_agent,
                resolved_input={},
                status=_RUN_STATUS_FAILED,
                error=self._error_payload(failure),
            )
            return None, entry

    def _resolve_agent_input(
        self,
        *,
        step_index: int,
        raw_agent: dict[str, Any],
        input_node: SchemaNode,
        input_model: type[BaseModel],
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> dict[str, Any]:
        target_fields = self._object_field_map(input_node)
        wiring = dict(raw_agent.get("wiring") or {})
        agent_field_prefix = f"steps[{step_index - 1}].agents.{raw_agent['slot']}.wiring"
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
                source,
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
        return await asyncio.to_thread(
            self._invoke_agent_sync,
            agent,
            resolved_input,
            output_model,
            trace_id,
            step_index,
            slot,
        )

    def _invoke_agent_sync(
        self,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocationResult:
        del trace_id
        with self.session_factory() as session:
            reference_service = StockAnalysisReferenceService(session)
            try:
                reference_result = reference_service.maybe_invoke(
                    agent=agent,
                    resolved_input=resolved_input,
                    step_index=step_index,
                    slot=slot,
                )
            except StockAnalysisReferenceError as exc:
                raise RunExecutionError(
                    code=exc.code,
                    message=exc.message,
                    details=list(exc.details or []),
                ) from exc
            if reference_result is not None:
                return RunAgentInvocationResult(
                    output=reference_result["output"],
                    tokens=int(reference_result.get("tokens", 0) or 0),
                    cost_usd=parse_decimal_string(reference_result.get("costUsd", "0")),
                    duration_ms=(
                        int(reference_result["durationMs"])
                        if reference_result.get("durationMs") is not None
                        else None
                    ),
                    trace_span_id=(
                        None
                        if reference_result.get("traceSpanId") is None
                        else str(reference_result["traceSpanId"])
                    ),
                )
            model_connection = self._resolve_runtime_model_connection(session, agent)
        return self._invoke_saved_model_connection_agent(
            agent=agent,
            model_connection=model_connection,
            resolved_input=resolved_input,
            output_model=output_model,
        )

    def _resolve_runtime_model_connection(
        self,
        session: Session,
        agent: Agent,
    ) -> _ResolvedModelConnectionConfig:
        if agent.model_connection_id is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=f"Agent {agent.key!r} is missing its saved model connection",
            )
        connection = ModelConnectionRepository(session).get(agent.model_connection_id)
        if connection is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=(
                    f"Agent {agent.key!r} references missing model connection "
                    f"{agent.model_connection_id}"
                ),
            )
        return _ResolvedModelConnectionConfig(
            id=connection.id,
            name=connection.name,
            base_url=connection.base_url,
            organization=connection.organization,
            project=connection.project,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            timeout_seconds=connection.timeout_seconds,
            api_key=self._extract_model_connection_api_key(connection),
        )

    @staticmethod
    def _extract_model_connection_api_key(connection: ModelConnection) -> str | None:
        payload = connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
        raw_api_key = payload.get("apiKey")
        if raw_api_key is None:
            return None
        normalized = str(raw_api_key).strip()
        return normalized or None

    def _invoke_saved_model_connection_agent(
        self,
        *,
        agent: Agent,
        model_connection: _ResolvedModelConnectionConfig,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
    ) -> RunAgentInvocationResult:
        if model_connection.api_key is None:
            raise RunExecutionError(
                code="agent_model_connection_api_key_missing",
                message=(
                    f"Agent {agent.key!r} cannot run because model connection "
                    f"{model_connection.name!r} is missing an API key"
                ),
            )

        instructions = self._build_openai_instructions(agent, output_model)
        input_text = self._build_openai_input(resolved_input)
        started_at = time.monotonic()
        client_kwargs: dict[str, Any] = {
            "api_key": model_connection.api_key,
            "base_url": model_connection.base_url,
            "timeout": float(model_connection.timeout_seconds),
        }
        if model_connection.organization:
            client_kwargs["organization"] = model_connection.organization
        if model_connection.project:
            client_kwargs["project"] = model_connection.project

        try:
            with OpenAI(**client_kwargs) as client:
                response = client.responses.create(
                    model=model_connection.model_id,
                    instructions=instructions,
                    input=input_text,
                    reasoning=cast(Any, {"effort": model_connection.reasoning_effort}),
                )
        except openai.APITimeoutError as exc:
            raise RunExecutionError(
                code="agent_provider_timeout",
                message="OpenAI request timed out.",
            ) from exc
        except openai.APIConnectionError as exc:
            raise RunExecutionError(
                code="agent_provider_connection_error",
                message="OpenAI request could not reach the API.",
            ) from exc
        except openai.APIStatusError as exc:
            raise RunExecutionError(
                code="agent_provider_status_error",
                message=self._format_api_status_error(exc, api_key=model_connection.api_key),
            ) from exc
        except openai.APIError as exc:
            raise RunExecutionError(
                code="agent_provider_error",
                message=self._normalize_provider_message(
                    str(exc),
                    api_key=model_connection.api_key,
                ),
            ) from exc
        except Exception as exc:
            raise RunExecutionError(
                code="agent_provider_error",
                message=self._normalize_provider_message(
                    f"Unexpected OpenAI execution failure: {exc}",
                    api_key=model_connection.api_key,
                ),
            ) from exc

        duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
        response_text = self._extract_response_text(response)
        return RunAgentInvocationResult(
            output=self._parse_response_output(response_text),
            tokens=self._extract_total_tokens(response),
            cost_usd=Decimal("0"),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _build_openai_instructions(agent: Agent, output_model: type[BaseModel]) -> str:
        schema_text = json.dumps(output_model.model_json_schema(), indent=2, sort_keys=True)
        return (
            f"{agent.system_prompt.strip()}\n\n"
            "Return only valid JSON with no markdown fences or explanatory text. "
            "The JSON must satisfy this schema exactly:\n"
            f"{schema_text}"
        )

    @staticmethod
    def _build_openai_input(resolved_input: dict[str, Any]) -> str:
        serialized_input = json.dumps(
            resolved_input,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"Use this JSON object as the complete agent input:\n{serialized_input}"

    @classmethod
    def _extract_response_text(cls, response: Any) -> str:
        if isinstance(response, dict):
            direct_text = response.get("output_text") or response.get("outputText")
            output_payload = response.get("output")
        else:
            direct_text = getattr(response, "output_text", None)
            output_payload = getattr(response, "output", None)
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()
        fragments = cls._collect_response_text_fragments(output_payload)
        normalized = "\n".join(
            fragment.strip() for fragment in fragments if fragment.strip()
        ).strip()
        if normalized:
            return normalized
        raise RunExecutionError(
            code="agent_provider_response_empty",
            message="OpenAI response did not contain text output.",
        )

    @classmethod
    def _collect_response_text_fragments(cls, value: Any) -> list[str]:
        fragments: list[str] = []
        if value is None:
            return fragments
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            for item in value:
                fragments.extend(cls._collect_response_text_fragments(item))
            return fragments
        if isinstance(value, dict):
            text_value = value.get("text")
            if isinstance(text_value, str) and text_value.strip():
                fragments.append(text_value)
            for key in ("content", "output"):
                nested = value.get(key)
                if nested is not None:
                    fragments.extend(cls._collect_response_text_fragments(nested))
            return fragments

        text_attr = getattr(value, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            fragments.append(text_attr)
        for attr in ("content", "output"):
            nested = getattr(value, attr, None)
            if nested is not None:
                fragments.extend(cls._collect_response_text_fragments(nested))
        return fragments

    def _parse_response_output(self, response_text: str) -> Any:
        candidate = self._strip_markdown_code_fence(response_text)
        candidates = [candidate]
        embedded = self._extract_embedded_json_candidate(candidate)
        if embedded is not None and embedded != candidate:
            candidates.append(embedded)
        for raw_candidate in candidates:
            try:
                return json.loads(raw_candidate)
            except json.JSONDecodeError:
                continue
        raise RunExecutionError(
            code="agent_output_parse_failed",
            message="OpenAI response did not return valid JSON for the agent output schema.",
        )

    @staticmethod
    def _strip_markdown_code_fence(text: str) -> str:
        candidate = text.strip()
        if not candidate.startswith("```"):
            return candidate
        lines = candidate.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
            return "\n".join(lines[1:-1]).strip()
        return candidate

    @staticmethod
    def _extract_embedded_json_candidate(text: str) -> str | None:
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start != -1 and object_end > object_start:
            return text[object_start : object_end + 1].strip()
        array_start = text.find("[")
        array_end = text.rfind("]")
        if array_start != -1 and array_end > array_start:
            return text[array_start : array_end + 1].strip()
        return None

    @staticmethod
    def _extract_total_tokens(response: Any) -> int:
        if isinstance(response, dict):
            usage = response.get("usage")
        else:
            usage = getattr(response, "usage", None)
        if isinstance(usage, dict):
            raw_total = usage.get("total_tokens", usage.get("totalTokens"))
        else:
            raw_total = getattr(usage, "total_tokens", None)
            if raw_total is None:
                raw_total = getattr(usage, "totalTokens", None)
        try:
            return int(raw_total or 0)
        except (TypeError, ValueError):
            return 0

    def _format_api_status_error(self, exc: openai.APIStatusError, *, api_key: str) -> str:
        message = self._extract_api_status_message(exc)
        request_id = getattr(exc, "request_id", None)
        if isinstance(request_id, str) and request_id.strip():
            message = f"{message} requestId={request_id.strip()}"
        return self._normalize_provider_message(message, api_key=api_key)

    @staticmethod
    def _extract_api_status_message(exc: openai.APIStatusError) -> str:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            raw_error = body.get("error")
            if isinstance(raw_error, dict):
                raw_message = raw_error.get("message")
                if isinstance(raw_message, str) and raw_message.strip():
                    return raw_message.strip()
            raw_message = body.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                return raw_message.strip()

        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return f"OpenAI request failed with status {status_code}."
        return "OpenAI request failed."

    @staticmethod
    def _normalize_provider_message(message: str, *, api_key: str | None) -> str:
        normalized = " ".join(str(message).split()).strip()
        if api_key:
            normalized = normalized.replace(api_key, "[REDACTED]")
        if len(normalized) > 500:
            return f"{normalized[:497]}..."
        return normalized or "Agent execution failed."

    def _coerce_invocation_result(self, raw_result: Any) -> RunAgentInvocationResult:
        if isinstance(raw_result, RunAgentInvocationResult):
            return raw_result
        if not isinstance(raw_result, dict):
            raise RunExecutionError(
                code="agent_result_invalid",
                message="Agent execution returned an unsupported result payload",
            )
        duration_raw = raw_result.get("duration_ms", raw_result.get("durationMs"))
        trace_span_raw = raw_result.get("trace_span_id", raw_result.get("traceSpanId"))
        return RunAgentInvocationResult(
            output=raw_result.get("output"),
            tokens=int(raw_result.get("tokens", 0) or 0),
            cost_usd=self._normalize_cost(
                raw_result.get("cost_usd", raw_result.get("costUsd", "0"))
            ),
            duration_ms=None if duration_raw is None else int(duration_raw),
            trace_span_id=None if trace_span_raw is None else str(trace_span_raw),
        )

    def _check_budget(
        self,
        *,
        agent: Agent,
        workflow: Workflow,
        agent_cost: Decimal,
        projected_total_cost: Decimal,
    ) -> RunExecutionError | None:
        if agent_cost > agent.budget_usd:
            budget_text = decimal_to_string(agent.budget_usd)
            return RunExecutionError(
                code="agent_budget_exceeded",
                message=f"Agent {agent.key!r} exceeded its budget of {budget_text} USD",
            )
        if projected_total_cost > workflow.aggregate_budget_usd:
            return RunExecutionError(
                code="run_budget_exceeded",
                message=(
                    f"Run exceeded the workflow aggregate budget of "
                    f"{decimal_to_string(workflow.aggregate_budget_usd)} USD"
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

    def _resolve_workflow(self, workflow_id: int, *, version: int | None) -> Workflow:
        anchor = self.workflow_repository.get(workflow_id)
        if anchor is None:
            raise not_found_error("Workflow")
        if version is None:
            return anchor
        workflow = self.workflow_repository.get_by_key_version(anchor.key, version)
        if workflow is None:
            raise not_found_error("Workflow")
        return workflow

    def _get_workflow_for_run(self, run: Run) -> Workflow:
        workflow = self.workflow_repository.get_by_key_version(
            run.workflow_key,
            run.workflow_version,
        )
        if workflow is None:
            raise RunExecutionError(
                code="run_workflow_missing",
                message=(
                    f"Workflow {run.workflow_key!r} version {run.workflow_version} "
                    "is no longer available"
                ),
            )
        return workflow

    def _resolve_agent_row(self, raw_agent: dict[str, Any]) -> Agent:
        agent = self.agent_repository.get_by_key_version(
            str(raw_agent["agentKey"]),
            int(raw_agent["agentVersion"]),
        )
        if agent is None:
            raise RunExecutionError(
                code="run_agent_missing",
                message=(
                    f"Agent {raw_agent['agentKey']!r} version "
                    f"{raw_agent['agentVersion']} was not found"
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

    def _validate_workflow_input(
        self,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        input_model = self._build_input_model(input_schema, candidate_key="workflow_input")
        try:
            validated = input_model.model_validate(input_payload)
        except ValidationError as exc:
            raise business_rule_error(
                "run_invalid_input",
                "Run input failed workflow input schema validation",
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
    def _start_trace_session(*, run: Run, workflow: Workflow) -> Any:
        configure_logfire()
        return create_logfire_span(
            "Workflow run {workflow_key} v{workflow_version} #{run_id}",
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            workflow_version=workflow.version,
            run_id=run.id,
            run_status=run.status,
        )

    @staticmethod
    def _normalize_cost(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return parse_decimal_string(value)

    @staticmethod
    def _coerce_execution_error(exc: Exception) -> RunExecutionError:
        if isinstance(exc, RunExecutionError):
            return exc
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
        raw_agent: dict[str, Any],
        resolved_input: dict[str, Any],
        status: str = _RUN_STATUS_RUNNING,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "slot": str(raw_agent["slot"]),
            "agentId": int(raw_agent["agentId"]),
            "agentKey": str(raw_agent["agentKey"]),
            "agentVersion": int(raw_agent["agentVersion"]),
            "outputSchemaId": int(raw_agent["outputSchemaId"]),
            "outputSchemaVersion": int(raw_agent["outputSchemaVersion"]),
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
                "workflowId": run.workflow_id,
                "workflowKey": run.workflow_key,
                "workflowVersion": run.workflow_version,
                "traceId": run.trace_id,
                "createdAt": run.created_at,
            }
        )

    @staticmethod
    def _to_list_item(run: Run) -> RunListItemRead:
        return RunListItemRead.model_validate(
            {
                "id": run.id,
                "workflowId": run.workflow_id,
                "workflowKey": run.workflow_key,
                "workflowVersion": run.workflow_version,
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
                "workflowId": run.workflow_id,
                "workflowKey": run.workflow_key,
                "workflowVersion": run.workflow_version,
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
