from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import select

from app.core.formatting import utcnow
from app.models.run_operation_invocation import RunOperationInvocation
from app.repositories.base import BaseRepository

_TERMINAL_OPERATION_STATUSES = ("succeeded", "failed", "skipped")
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "cookie",
)


def _normalized_sensitive_key(value: object) -> str:
    return str(value).replace("-", "_").replace(" ", "_").lower()


def _is_sensitive_metadata_key(value: object) -> bool:
    normalized = _normalized_sensitive_key(value)
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _redacted_marker() -> dict[str, bool]:
    return {"redacted": True}


def redact_operation_request_metadata(value: object) -> object:
    if isinstance(value, dict):
        source = cast(dict[object, object], value)
        if source.get("from") == "secret":
            redacted: dict[str, object] = {"from": "secret", "redacted": True}
            if source.get("key") is not None:
                redacted["key"] = str(source["key"])
            return redacted
        sanitized: dict[str, object] = {}
        for key, item in source.items():
            if _is_sensitive_metadata_key(key) and not (
                isinstance(item, dict) and item.get("from") == "secret"
            ):
                sanitized[str(key)] = _redacted_marker()
            else:
                sanitized[str(key)] = redact_operation_request_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [redact_operation_request_metadata(item) for item in value]
    return value


class RunOperationInvocationRepository(BaseRepository[RunOperationInvocation]):
    model = RunOperationInvocation

    def create_operation(
        self,
        *,
        run_step_id: int,
        run_id: int,
        step_index: int,
        slot: str,
        position: int,
        operation_key: str,
        operation_kind: str,
        output_schema_id: int,
        output_schema_version: int,
        method: str | None = None,
        timeout_seconds: int | None = None,
        request_metadata: dict[str, Any] | None = None,
        response_metadata: dict[str, Any] | None = None,
        graph_metadata: dict[str, Any] | None = None,
        optional: bool = False,
        status: str = "pending",
        output: Any | None = None,
        output_origin: str | None = None,
    ) -> RunOperationInvocation:
        operation = self.model(
            run_step_id=run_step_id,
            run_id=run_id,
            step_index=step_index,
            slot=slot,
            position=position,
            operation_key=operation_key,
            operation_kind=operation_kind,
            output_schema_id=output_schema_id,
            output_schema_version=output_schema_version,
            method=method,
            timeout_seconds=timeout_seconds,
            request_metadata=cast(
                dict[str, Any],
                redact_operation_request_metadata(request_metadata or {}),
            ),
            response_metadata=response_metadata or {},
            graph_metadata=graph_metadata,
            optional=optional,
            status=status,
            output=output,
            output_origin=output_origin,
        )
        return self.add(operation)

    def get_by_run_step_slot(
        self,
        run_id: int,
        step_index: int,
        slot: str,
    ) -> RunOperationInvocation | None:
        statement = select(self.model).where(
            self.model.run_id == run_id,
            self.model.step_index == step_index,
            self.model.slot == slot,
        )
        return self._get_by_statement(statement)

    def list_by_run(self, run_id: int) -> list[RunOperationInvocation]:
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

    def list_by_run_step(self, run_id: int, step_index: int) -> list[RunOperationInvocation]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id, self.model.step_index == step_index)
            .order_by(self.model.position.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_terminal_by_run(self, run_id: int) -> list[RunOperationInvocation]:
        statement = (
            select(self.model)
            .where(
                self.model.run_id == run_id,
                self.model.status.in_(_TERMINAL_OPERATION_STATUSES),
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
        operation: RunOperationInvocation,
        *,
        request_metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> RunOperationInvocation:
        started = started_at or utcnow()
        operation.status = "running"
        operation.started_at = operation.started_at or started
        operation.finished_at = None
        operation.persisted_at = None
        operation.output = None
        operation.output_origin = None
        operation.response_metadata = {}
        operation.error_code = None
        operation.error_message = None
        operation.error_details = []
        if request_metadata is not None:
            operation.request_metadata = cast(
                dict[str, Any],
                redact_operation_request_metadata(request_metadata),
            )
        return self.add(operation)

    def persist_success(
        self,
        operation: RunOperationInvocation,
        *,
        output: Any,
        output_origin: str = "executed",
        response_metadata: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        trace_span_id: str | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunOperationInvocation:
        finished = finished_at or utcnow()
        operation.status = "succeeded"
        operation.output = output
        operation.output_origin = output_origin
        operation.response_metadata = response_metadata or {}
        operation.error_code = None
        operation.error_message = None
        operation.error_details = []
        operation.duration_ms = duration_ms
        operation.trace_span_id = trace_span_id
        operation.finished_at = finished
        operation.persisted_at = persisted_at or finished
        return self.add(operation)

    def persist_failure(
        self,
        operation: RunOperationInvocation,
        *,
        error_code: str,
        error_message: str,
        error_details: list[dict[str, Any]] | None = None,
        response_metadata: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        trace_span_id: str | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunOperationInvocation:
        finished = finished_at or utcnow()
        operation.status = "failed"
        operation.output = None
        operation.output_origin = None
        operation.response_metadata = response_metadata or {}
        operation.error_code = error_code
        operation.error_message = error_message
        operation.error_details = list(error_details or [])
        operation.duration_ms = duration_ms
        operation.trace_span_id = trace_span_id
        operation.finished_at = finished
        operation.persisted_at = persisted_at or finished
        return self.add(operation)

    def persist_skipped(
        self,
        operation: RunOperationInvocation,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: list[dict[str, Any]] | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunOperationInvocation:
        finished = finished_at or utcnow()
        operation.status = "skipped"
        operation.output = None
        operation.output_origin = None
        operation.response_metadata = {}
        operation.error_code = error_code
        operation.error_message = error_message
        operation.error_details = list(error_details or [])
        operation.finished_at = finished
        operation.persisted_at = persisted_at or finished
        return self.add(operation)

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
            (operation.step_index, operation.slot): operation.output
            for operation in self._list(statement)
        }
