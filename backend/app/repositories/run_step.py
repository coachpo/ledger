from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from app.core.formatting import utcnow
from app.models.run_step import RunStep
from app.repositories.base import BaseRepository

_TERMINAL_STEP_STATUSES = ("succeeded", "failed", "skipped")


class RunStepRepository(BaseRepository[RunStep]):
    model = RunStep

    def create_planned_steps(
        self,
        *,
        run_id: int,
        step_indexes: Iterable[int],
        graph_metadata_by_index: dict[int, dict[str, Any]] | None = None,
    ) -> list[RunStep]:
        metadata_by_index = graph_metadata_by_index or {}
        steps = [
            self.model(
                run_id=run_id,
                step_index=step_index,
                status="pending",
                origin="planned",
                graph_metadata=metadata_by_index.get(step_index),
            )
            for step_index in step_indexes
        ]
        self.session.add_all(steps)
        return steps

    def get_by_run_step_index(self, run_id: int, step_index: int) -> RunStep | None:
        statement = select(self.model).where(
            self.model.run_id == run_id,
            self.model.step_index == step_index,
        )
        return self._get_by_statement(statement)

    def list_by_run(self, run_id: int) -> list[RunStep]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id)
            .order_by(self.model.step_index.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_terminal_by_run(self, run_id: int) -> list[RunStep]:
        statement = (
            select(self.model)
            .where(
                self.model.run_id == run_id,
                self.model.status.in_(_TERMINAL_STEP_STATUSES),
            )
            .order_by(self.model.step_index.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_source_linked(
        self,
        *,
        source_run_id: int | None = None,
        source_run_step_id: int | None = None,
    ) -> list[RunStep]:
        statement = select(self.model)
        if source_run_id is None and source_run_step_id is None:
            statement = statement.where(
                or_(
                    self.model.source_run_id.is_not(None),
                    self.model.source_run_step_id.is_not(None),
                )
            )
        if source_run_id is not None:
            statement = statement.where(self.model.source_run_id == source_run_id)
        if source_run_step_id is not None:
            statement = statement.where(self.model.source_run_step_id == source_run_step_id)
        statement = statement.order_by(
            self.model.run_id.asc(),
            self.model.step_index.asc(),
            self.model.id.asc(),
        )
        return self._list(statement)

    def mark_running(
        self,
        step: RunStep,
        *,
        started_at: datetime | None = None,
    ) -> RunStep:
        started = started_at or utcnow()
        step.status = "running"
        step.started_at = step.started_at or started
        step.finished_at = None
        step.persisted_at = None
        step.error = None
        return self.add(step)

    def persist_success(
        self,
        step: RunStep,
        *,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunStep:
        finished = finished_at or utcnow()
        step.status = "succeeded"
        step.error = None
        step.finished_at = finished
        step.persisted_at = persisted_at or finished
        return self.add(step)

    def persist_failure(
        self,
        step: RunStep,
        *,
        error: str,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunStep:
        finished = finished_at or utcnow()
        step.status = "failed"
        step.error = error
        step.finished_at = finished
        step.persisted_at = persisted_at or finished
        return self.add(step)

    def persist_skipped(
        self,
        step: RunStep,
        *,
        error: str | None = None,
        finished_at: datetime | None = None,
        persisted_at: datetime | None = None,
    ) -> RunStep:
        finished = finished_at or utcnow()
        step.status = "skipped"
        step.error = error
        step.finished_at = finished
        step.persisted_at = persisted_at or finished
        return self.add(step)
