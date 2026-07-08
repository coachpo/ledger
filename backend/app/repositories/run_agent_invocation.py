from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.formatting import utcnow
from app.models.run_agent_invocation import RunAgentInvocation
from app.repositories.base import BaseRepository

_TERMINAL_INVOCATION_STATUSES = ("succeeded", "failed", "skipped")


class RunAgentInvocationRepository(BaseRepository[RunAgentInvocation]):
    model = RunAgentInvocation

    def create_invocation(
        self,
        *,
        run_step_id: int,
        run_id: int,
        step_index: int,
        slot: str,
        position: int,
        agent_id: int,
        agent_key: str,
        agent_version: int,
        output_schema_id: int,
        output_schema_version: int,
        input_mode: str = "wired",
        wiring: dict[str, Any] | None = None,
        graph_metadata: dict[str, Any] | None = None,
        optional: bool = False,
        resolved_input: dict[str, Any] | None = None,
        resolved_input_origin: str = "derived",
        status: str = "pending",
        output: Any | None = None,
        output_origin: str | None = None,
    ) -> RunAgentInvocation:
        invocation = self.model(
            run_step_id=run_step_id,
            run_id=run_id,
            step_index=step_index,
            slot=slot,
            position=position,
            agent_id=agent_id,
            agent_key=agent_key,
            agent_version=agent_version,
            output_schema_id=output_schema_id,
            output_schema_version=output_schema_version,
            input_mode=input_mode,
            wiring=wiring or {},
            graph_metadata=graph_metadata,
            optional=optional,
            resolved_input=resolved_input or {},
            resolved_input_origin=resolved_input_origin,
            status=status,
            output=output,
            output_origin=output_origin,
        )
        return self.add(invocation)

    def create_invocations(
        self,
        invocations: Iterable[RunAgentInvocation],
    ) -> list[RunAgentInvocation]:
        rows = list(invocations)
        self.session.add_all(rows)
        return rows

    def get_by_step_slot(self, run_step_id: int, slot: str) -> RunAgentInvocation | None:
        statement = select(self.model).where(
            self.model.run_step_id == run_step_id,
            self.model.slot == slot,
        )
        return self._get_by_statement(statement)

    def get_by_run_step_slot(
        self,
        run_id: int,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocation | None:
        statement = select(self.model).where(
            self.model.run_id == run_id,
            self.model.step_index == step_index,
            self.model.slot == slot,
        )
        return self._get_by_statement(statement)

    def list_by_run(self, run_id: int) -> list[RunAgentInvocation]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id)
            .order_by(
                self.model.step_index.asc(),
                self.model.position.asc(),
                self.model.id.asc(),
            )
        )
        return self._list(statement)

    def list_by_run_step(self, run_id: int, step_index: int) -> list[RunAgentInvocation]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id, self.model.step_index == step_index)
            .order_by(self.model.position.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_terminal_by_run(self, run_id: int) -> list[RunAgentInvocation]:
        statement = (
            select(self.model)
            .where(
                self.model.run_id == run_id,
                self.model.status.in_(_TERMINAL_INVOCATION_STATUSES),
            )
            .order_by(
                self.model.step_index.asc(),
                self.model.position.asc(),
                self.model.id.asc(),
            )
        )
        return self._list(statement)

    def mark_running(
        self,
        invocation: RunAgentInvocation,
        *,
        resolved_input: dict[str, Any] | None = None,
        resolved_input_origin: str | None = None,
        started_at: datetime | None = None,
    ) -> RunAgentInvocation:
        started = started_at or utcnow()
        invocation.status = "running"
        invocation.started_at = invocation.started_at or started
        invocation.finished_at = None
        invocation.persisted_at = None
        invocation.error_code = None
        invocation.error_message = None
        invocation.error_details = []
        if resolved_input is not None:
            invocation.resolved_input = resolved_input
        if resolved_input_origin is not None:
            invocation.resolved_input_origin = resolved_input_origin
        return self.add(invocation)

    def persist_success(
        self,
        invocation: RunAgentInvocation,
        *,
        output: Any,
        output_origin: str = "executed",
        tokens: int = 0,
        duration_ms: int | None = None,
        trace_span_id: str | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunAgentInvocation:
        finished = finished_at or utcnow()
        invocation.status = "succeeded"
        invocation.output = output
        invocation.output_origin = output_origin
        invocation.error_code = None
        invocation.error_message = None
        invocation.error_details = []
        invocation.tokens = tokens
        invocation.duration_ms = duration_ms
        invocation.trace_span_id = trace_span_id
        invocation.finished_at = finished
        invocation.persisted_at = persisted_at or finished
        return self.add(invocation)

    def persist_failure(
        self,
        invocation: RunAgentInvocation,
        *,
        error_code: str,
        error_message: str,
        error_details: list[dict[str, Any]] | None = None,
        tokens: int = 0,
        duration_ms: int | None = None,
        trace_span_id: str | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunAgentInvocation:
        finished = finished_at or utcnow()
        invocation.status = "failed"
        invocation.output = None
        invocation.output_origin = None
        invocation.error_code = error_code
        invocation.error_message = error_message
        invocation.error_details = list(error_details or [])
        invocation.tokens = tokens
        invocation.duration_ms = duration_ms
        invocation.trace_span_id = trace_span_id
        invocation.finished_at = finished
        invocation.persisted_at = persisted_at or finished
        return self.add(invocation)

    def persist_skipped(
        self,
        invocation: RunAgentInvocation,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: list[dict[str, Any]] | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunAgentInvocation:
        finished = finished_at or utcnow()
        invocation.status = "skipped"
        invocation.output = None
        invocation.output_origin = None
        invocation.error_code = error_code
        invocation.error_message = error_message
        invocation.error_details = list(error_details or [])
        invocation.finished_at = finished
        invocation.persisted_at = persisted_at or finished
        return self.add(invocation)

    def hydrate_successful_outputs(
        self,
        run_id: int,
        *,
        before_step_index: int | None = None,
    ) -> dict[tuple[int, str], Any]:
        statement = select(self.model).where(
            self.model.run_id == run_id,
            self.model.status == "succeeded",
        )
        if before_step_index is not None:
            statement = statement.where(self.model.step_index < before_step_index)
        statement = statement.order_by(
            self.model.step_index.asc(),
            self.model.position.asc(),
            self.model.id.asc(),
        )
        return {
            (invocation.step_index, invocation.slot): invocation.output
            for invocation in self._list(statement)
        }
