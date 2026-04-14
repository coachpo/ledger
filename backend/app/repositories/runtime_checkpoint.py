from __future__ import annotations

from sqlalchemy import select

from app.models.runtime_checkpoint import RuntimeCheckpoint
from app.repositories.base import BaseRepository


class RuntimeCheckpointRepository(BaseRepository[RuntimeCheckpoint]):
    model = RuntimeCheckpoint

    def list_for_run(self, run_id: int) -> list[RuntimeCheckpoint]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id)
            .order_by(
                self.model.checkpoint_index.asc(), self.model.created_at.asc(), self.model.id.asc()
            )
        )
        return self._list(statement)

    def get_for_run_index(self, run_id: int, checkpoint_index: int) -> RuntimeCheckpoint | None:
        statement = select(self.model).where(
            self.model.run_id == run_id,
            self.model.checkpoint_index == checkpoint_index,
        )
        return self._get_by_statement(statement)

    def get_latest_for_run(self, run_id: int) -> RuntimeCheckpoint | None:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id)
            .order_by(
                self.model.checkpoint_index.desc(),
                self.model.updated_at.desc(),
                self.model.id.desc(),
            )
        )
        return self.session.scalar(statement.limit(1))
