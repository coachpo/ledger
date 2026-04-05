from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.balance import Balance
from app.repositories.base import BaseRepository
from app.schemas.common import OperationType


class BalanceRepository(BaseRepository[Balance]):
    model = Balance

    def list_for_portfolio(self, portfolio_id: int) -> list[Balance]:
        statement = (
            select(self.model)
            .options(selectinload(self.model.trading_operations))
            .where(self.model.portfolio_id == portfolio_id)
            .order_by(self.model.created_at.asc())
        )
        return self._list(statement)

    def get_for_portfolio(self, portfolio_id: int, balance_id: int) -> Balance | None:
        statement = (
            select(self.model)
            .options(selectinload(self.model.trading_operations))
            .where(
                self.model.portfolio_id == portfolio_id,
                self.model.id == balance_id,
            )
        )
        return self._get_by_statement(statement)

    def get_by_label(self, portfolio_id: int, label: str) -> Balance | None:
        statement = select(self.model).where(
            self.model.portfolio_id == portfolio_id,
            self.model.label == label,
        )
        return self._get_by_statement(statement)

    def list_deposit_balances_for_portfolio(self, portfolio_id: int) -> list[Balance]:
        statement = (
            select(self.model)
            .options(selectinload(self.model.trading_operations))
            .where(
                self.model.portfolio_id == portfolio_id,
                self.model.operation_type == OperationType.DEPOSIT.value,
            )
            .order_by(self.model.amount.desc(), self.model.created_at.asc())
        )
        return self._list(statement)
