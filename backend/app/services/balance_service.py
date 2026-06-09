from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import PORTFOLIO_CURRENCY
from app.core.errors import business_rule_error, not_found_error
from app.extensions.signaldeck_finance.service_gate import (
    BALANCE_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.models.balance import Balance
from app.repositories.balance import BalanceRepository
from app.schemas.balance import BalanceCreate, BalanceRead, BalanceUpdate
from app.services.portfolio_service import PortfolioService


class BalanceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = BalanceRepository(session)
        self.portfolio_service = PortfolioService(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=BALANCE_SERVICE_SURFACE)

    def list_balances(self, portfolio_id: int) -> list[BalanceRead]:
        self._require_enabled()
        self.portfolio_service.get_portfolio_model(portfolio_id)
        balances = self.repository.list_for_portfolio(portfolio_id)
        return [BalanceRead.model_validate(balance) for balance in balances]

    def create_balance(self, portfolio_id: int, payload: BalanceCreate) -> BalanceRead:
        self._require_enabled()
        portfolio = self.portfolio_service.get_portfolio_model(portfolio_id)
        if self.repository.get_by_label(portfolio_id, payload.label) is not None:
            raise business_rule_error(
                "duplicate_balance_label",
                "A balance with this label already exists in the portfolio",
            )
        balance = Balance(
            portfolio_id=portfolio.id,
            label=payload.label,
            amount=payload.amount,
            operation_type=payload.operation_type,
            currency=PORTFOLIO_CURRENCY,
        )
        self.repository.add(balance)
        self.session.commit()
        self.session.refresh(balance)
        return BalanceRead.model_validate(balance)

    def update_balance(
        self, portfolio_id: int, balance_id: int, payload: BalanceUpdate
    ) -> BalanceRead:
        self._require_enabled()
        balance = self.repository.get_for_portfolio(portfolio_id, balance_id)
        if balance is None:
            raise not_found_error("Balance")
        if payload.label is not None and payload.label != balance.label:
            duplicate = self.repository.get_by_label(portfolio_id, payload.label)
            if duplicate is not None and duplicate.id != balance.id:
                raise business_rule_error(
                    "duplicate_balance_label",
                    "A balance with this label already exists in the portfolio",
                )
            balance.label = payload.label
        if payload.amount is not None:
            balance.amount = payload.amount
        if payload.operation_type is not None:
            if payload.operation_type != balance.operation_type and balance.has_trading_operations:
                raise business_rule_error(
                    "balance_operation_type_locked",
                    "Cannot change operation type for a balance with trading history",
                )
            balance.operation_type = payload.operation_type
        self.session.commit()
        self.session.refresh(balance)
        return BalanceRead.model_validate(balance)

    def delete_balance(self, portfolio_id: int, balance_id: int) -> None:
        self._require_enabled()
        balance = self.repository.get_for_portfolio(portfolio_id, balance_id)
        if balance is None:
            raise not_found_error("Balance")
        self.repository.delete(balance)
        self.session.commit()
