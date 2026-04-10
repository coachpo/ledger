from __future__ import annotations

from importlib import import_module
from typing import Any

from sqlalchemy import select

from app.repositories.base import BaseRepository

BacktestOrchestrationSnapshot = import_module(
    "app.models.backtest_orchestration_snapshot"
).BacktestOrchestrationSnapshot


class BacktestOrchestrationSnapshotRepository(BaseRepository):
    model = BacktestOrchestrationSnapshot

    def list_for_backtest(self, backtest_id: int) -> list[Any]:
        statement = (
            select(self.model)
            .where(self.model.backtest_id == backtest_id)
            .order_by(self.model.cycle_date.asc(), self.model.created_at.asc(), self.model.id.asc())
        )
        return self._list(statement)
