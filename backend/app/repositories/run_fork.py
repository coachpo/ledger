from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.run_fork import RunFork
from app.repositories.base import BaseRepository


class RunForkRepository(BaseRepository[RunFork]):
    model = RunFork

    def create_fork(
        self,
        *,
        run_id: int,
        source_run_id: int,
        lineage_root_run_id: int | None,
        source_invocation_id: int,
        source_step_index: int,
        resume_step_index: int,
        invocation_input: dict[str, Any],
    ) -> RunFork:
        fork = self.model(
            run_id=run_id,
            source_run_id=source_run_id,
            lineage_root_run_id=lineage_root_run_id,
            source_invocation_id=source_invocation_id,
            source_step_index=source_step_index,
            resume_step_index=resume_step_index,
            invocation_input=invocation_input,
        )
        return self.add(fork)

    def get_by_run_id(self, run_id: int) -> RunFork | None:
        return self.session.get(self.model, run_id)

    def list_by_source_run(self, source_run_id: int) -> list[RunFork]:
        statement = (
            select(self.model)
            .where(self.model.source_run_id == source_run_id)
            .order_by(self.model.run_id.asc())
        )
        return self._list(statement)

    def list_by_source_invocation(self, source_invocation_id: int) -> list[RunFork]:
        statement = (
            select(self.model)
            .where(self.model.source_invocation_id == source_invocation_id)
            .order_by(self.model.run_id.asc())
        )
        return self._list(statement)
