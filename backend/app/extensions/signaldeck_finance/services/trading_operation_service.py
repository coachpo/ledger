from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import PORTFOLIO_CURRENCY
from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import portfolio_cash_total, utcnow
from app.extensions.signaldeck_finance.service_gate import (
    TRADING_OPERATION_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.extensions.signaldeck_finance.services.portfolio_service import PortfolioService
from app.models.balance import Balance
from app.models.position import Position
from app.models.trading_operation import TradingOperation
from app.repositories.balance import BalanceRepository
from app.repositories.position import PositionRepository
from app.repositories.symbol_name_cache import SymbolNameCacheRepository
from app.repositories.trading_operation import TradingOperationRepository
from app.schemas.balance import BalanceCompactRead
from app.schemas.common import OperationType, TradingSide
from app.schemas.position import PositionCompactRead
from app.schemas.trading_operation import (
    BuyOperationCreate,
    DividendOperationCreate,
    SellOperationCreate,
    SplitOperationCreate,
    TradingOperationCreate,
    TradingOperationRead,
    TradingOperationResult,
)
from app.services.quote_provider import QuoteProvider, QuoteProviderError


class TradingOperationService:
    def __init__(self, session: Session, quote_provider: QuoteProvider) -> None:
        self.session = session
        self.balance_repository = BalanceRepository(session)
        self.position_repository = PositionRepository(session)
        self.portfolio_service = PortfolioService(session)
        self.repository = TradingOperationRepository(session)
        self.quote_provider = quote_provider
        self.symbol_name_cache_repository = SymbolNameCacheRepository(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(
            self.session,
            surface=TRADING_OPERATION_SERVICE_SURFACE,
        )

    def list_operations(self, portfolio_id: int) -> list[TradingOperationRead]:
        self._require_enabled()
        self.portfolio_service.get_portfolio_model(portfolio_id)
        operations = self.repository.list_for_portfolio(portfolio_id)
        return [TradingOperationRead.model_validate(operation) for operation in operations]

    def create_operation(
        self,
        portfolio_id: int,
        payload: TradingOperationCreate,
    ) -> TradingOperationResult:
        self._require_enabled()
        portfolio = self.portfolio_service.get_portfolio_model(portfolio_id)
        portfolio_cash_total = self._portfolio_cash_total(portfolio_id)
        position = self.position_repository.get_by_symbol(portfolio_id, payload.symbol)

        balance: Balance | None = None
        updated_position: Position | None

        try:
            if payload.side == TradingSide.BUY:
                assert isinstance(payload, BuyOperationCreate)
                balance = self._get_required_deposit_balance(portfolio_id, payload.balance_id)
                updated_position = self._apply_buy(
                    portfolio_id=portfolio.id,
                    currency=PORTFOLIO_CURRENCY,
                    position=position,
                    balance_amount=balance.amount,
                    portfolio_cash_total=portfolio_cash_total,
                    payload=payload,
                )
                balance.amount -= self._buy_cash_impact(payload)
                if position is None:
                    self.position_repository.add(updated_position)
            elif payload.side == TradingSide.SELL:
                assert isinstance(payload, SellOperationCreate)
                balance = self._get_required_deposit_balance(portfolio_id, payload.balance_id)
                updated_position = self._apply_sell(
                    position=position,
                    balance_amount=balance.amount,
                    payload=payload,
                )
                balance.amount += self._sell_cash_impact(payload)
                if updated_position is None and position is not None:
                    self.position_repository.delete(position)
            elif payload.side == TradingSide.DIVIDEND:
                assert isinstance(payload, DividendOperationCreate)
                balance = self._get_required_deposit_balance(portfolio_id, payload.balance_id)
                if position is None:
                    raise business_rule_error(
                        "no_position_for_dividend",
                        "Cannot apply dividend to non-existent position",
                    )
                updated_position = position
                if balance.amount + self._dividend_cash_impact(payload) < Decimal("0"):
                    raise business_rule_error(
                        "insufficient_balance",
                        "Selected balance would become negative",
                    )
                balance.amount += self._dividend_cash_impact(payload)
            elif payload.side == TradingSide.SPLIT:
                assert isinstance(payload, SplitOperationCreate)
                updated_position = self._apply_split(
                    position=position,
                    payload=payload,
                )
            else:
                raise ValueError(f"Unsupported operation side: {payload.side.value}")

            operation = self._build_operation_record(
                portfolio_id=portfolio.id,
                balance_id=balance.id if balance is not None else None,
                balance_label=balance.label if balance is not None else "Not Applicable",
                currency=PORTFOLIO_CURRENCY,
                payload=payload,
            )
            self.repository.add(operation)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(operation)
        if balance is not None:
            self.session.refresh(balance)
        if updated_position is not None:
            self.session.refresh(updated_position)

        return TradingOperationResult(
            operation=TradingOperationRead.model_validate(operation),
            updated_position=(
                PositionCompactRead.model_validate(updated_position)
                if updated_position is not None
                else None
            ),
            updated_balance=(
                BalanceCompactRead.model_validate(balance) if balance is not None else None
            ),
        )

    def _get_required_deposit_balance(self, portfolio_id: int, balance_id: int) -> Balance:
        balance = self.balance_repository.get_for_portfolio(portfolio_id, balance_id)
        if balance is None:
            raise not_found_error("Balance")
        if balance.operation_type != OperationType.DEPOSIT:
            raise business_rule_error(
                "invalid_operation_balance",
                "Trading operations require a deposit balance",
            )
        return balance

    def _apply_buy(
        self,
        *,
        portfolio_id: int,
        currency: str,
        position: Position | None,
        balance_amount: Decimal,
        portfolio_cash_total: Decimal,
        payload: BuyOperationCreate,
    ) -> Position:
        gross_cost = payload.quantity * payload.price
        cash_impact = self._buy_cash_impact(payload)
        if balance_amount < cash_impact:
            raise business_rule_error(
                "insufficient_balance",
                "Insufficient balance for buy operation",
            )
        if portfolio_cash_total < cash_impact:
            raise business_rule_error(
                "insufficient_balance",
                "Portfolio cash is insufficient after withdrawals",
            )
        if position is None:
            average_cost = cash_impact / payload.quantity
            resolved_name = self._resolve_symbol_name(payload.symbol)
            return Position(
                portfolio_id=portfolio_id,
                symbol=payload.symbol,
                name=resolved_name,
                quantity=payload.quantity,
                average_cost=average_cost,
                currency=currency,
                last_source="simulation",
            )

        new_quantity = position.quantity + payload.quantity
        new_book_cost = (
            (position.quantity * position.average_cost) + gross_cost + payload.commission
        )
        position.quantity = new_quantity
        position.average_cost = new_book_cost / new_quantity
        if position.name is None:
            position.name = self._resolve_symbol_name(payload.symbol)
        position.last_source = "simulation"
        return position

    def _apply_sell(
        self,
        *,
        position: Position | None,
        balance_amount: Decimal,
        payload: SellOperationCreate,
    ) -> Position | None:
        if position is None or payload.quantity > position.quantity:
            raise business_rule_error(
                "oversell_rejected",
                "Sell quantity exceeds the current position quantity",
            )
        cash_impact = self._sell_cash_impact(payload)
        if balance_amount + cash_impact < 0:
            raise business_rule_error(
                "insufficient_balance",
                "Selected balance would become negative",
            )
        remaining_quantity = position.quantity - payload.quantity
        if remaining_quantity == 0:
            return None
        position.quantity = remaining_quantity
        position.last_source = "simulation"
        return position

    def _build_operation_record(
        self,
        *,
        portfolio_id: int,
        balance_id: int | None,
        balance_label: str,
        currency: str,
        payload: TradingOperationCreate,
    ) -> TradingOperation:
        operation_data: dict[str, object] = {
            "portfolio_id": portfolio_id,
            "balance_id": balance_id,
            "balance_label": balance_label,
            "symbol": payload.symbol,
            "side": payload.side.value,
            "currency": currency,
            "executed_at": payload.executed_at,
            "commission": Decimal("0"),
        }

        if payload.side == TradingSide.BUY:
            assert isinstance(payload, BuyOperationCreate)
            operation_data["commission"] = payload.commission
            operation_data["quantity"] = payload.quantity
            operation_data["price"] = payload.price
        elif payload.side == TradingSide.SELL:
            assert isinstance(payload, SellOperationCreate)
            operation_data["commission"] = payload.commission
            operation_data["quantity"] = payload.quantity
            operation_data["price"] = payload.price
        elif payload.side == TradingSide.DIVIDEND:
            assert isinstance(payload, DividendOperationCreate)
            operation_data["commission"] = payload.commission
            operation_data["dividend_amount"] = payload.dividend_amount
        else:
            assert isinstance(payload, SplitOperationCreate)
            operation_data["split_ratio"] = payload.split_ratio

        return TradingOperation(**operation_data)

    def _buy_cash_impact(self, payload: BuyOperationCreate) -> Decimal:
        return (payload.quantity * payload.price) + payload.commission

    def _sell_cash_impact(self, payload: SellOperationCreate) -> Decimal:
        return (payload.quantity * payload.price) - payload.commission

    def _dividend_cash_impact(self, payload: DividendOperationCreate) -> Decimal:
        return payload.dividend_amount - payload.commission

    def _portfolio_cash_total(self, portfolio_id: int) -> Decimal:
        return portfolio_cash_total(self.balance_repository.list_for_portfolio(portfolio_id))

    def _apply_split(
        self,
        *,
        position: Position | None,
        payload: SplitOperationCreate,
    ) -> Position | None:
        if position is None:
            raise business_rule_error(
                "no_position_for_split",
                "Cannot apply split to non-existent position",
            )
        position.quantity = position.quantity * payload.split_ratio
        position.average_cost = position.average_cost / payload.split_ratio
        position.last_source = "simulation"
        return position

    def _resolve_symbol_name(self, symbol: str) -> str | None:
        cached = self.symbol_name_cache_repository.get_by_symbol(symbol)
        if cached is not None:
            return cached.name

        try:
            name = self.quote_provider.fetch_symbol_name(symbol)
        except QuoteProviderError:
            return None

        if name is None:
            return None

        self.symbol_name_cache_repository.insert_if_missing(
            symbol=symbol,
            name=name,
            fetched_at=utcnow(),
        )
        return name
