from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.trading_operation import TradingOperation


class TradingOperationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_portfolio(self, portfolio_id: int) -> list[TradingOperation]:
        statement = (
            select(TradingOperation)
            .where(TradingOperation.portfolio_id == portfolio_id)
            .order_by(desc(TradingOperation.executed_at), desc(TradingOperation.created_at))
        )
        return list(self.session.scalars(statement))

    def add(self, operation: TradingOperation) -> TradingOperation:
        self.session.add(operation)
        return operation
