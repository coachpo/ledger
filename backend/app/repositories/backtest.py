from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.backtest import Backtest
from app.repositories.base import BaseRepository


class BacktestRepository(BaseRepository[Backtest]):
    model = Backtest

    def list_all(self) -> list[Backtest]:
        statement = (
            select(self.model)
            .options(selectinload(self.model.portfolio))
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)

    def list_interrupted(self) -> list[Backtest]:
        statement = select(self.model).where(self.model.status.in_(("PENDING", "RUNNING")))
        return self._list(statement)
