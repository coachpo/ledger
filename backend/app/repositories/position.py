from __future__ import annotations

from sqlalchemy import select

from app.models.position import Position
from app.repositories.base import BaseRepository


class PositionRepository(BaseRepository[Position]):
    model = Position

    def list_for_portfolio(self, portfolio_id: int) -> list[Position]:
        statement = (
            select(self.model)
            .where(self.model.portfolio_id == portfolio_id)
            .order_by(self.model.symbol.asc())
        )
        return self._list(statement)

    def get_for_portfolio(self, portfolio_id: int, position_id: int) -> Position | None:
        statement = select(self.model).where(
            self.model.portfolio_id == portfolio_id,
            self.model.id == position_id,
        )
        return self._get_by_statement(statement)

    def get_by_symbol(self, portfolio_id: int, symbol: str) -> Position | None:
        statement = select(self.model).where(
            self.model.portfolio_id == portfolio_id,
            self.model.symbol == symbol,
        )
        return self._get_by_statement(statement)
