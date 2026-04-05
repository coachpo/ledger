from __future__ import annotations

from sqlalchemy import func, select

from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.repositories.base import BaseRepository


class PortfolioRepository(BaseRepository[Portfolio]):
    model = Portfolio

    def list_all(self) -> list[Portfolio]:
        statement = select(self.model).order_by(self.model.created_at.desc())
        return self._list(statement)

    def get_by_slug(self, slug: str) -> Portfolio | None:
        statement = select(self.model).where(self.model.slug == slug)
        return self._get_by_statement(statement)

    def count_balances(self, portfolio_id: int) -> int:
        statement = select(func.count(Balance.id)).where(Balance.portfolio_id == portfolio_id)
        return int(self.session.scalar(statement) or 0)

    def count_positions(self, portfolio_id: int) -> int:
        statement = select(func.count(Position.id)).where(Position.portfolio_id == portfolio_id)
        return int(self.session.scalar(statement) or 0)
