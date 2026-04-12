from __future__ import annotations

import threading

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.langgraph.seeds import (
    DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY,
    get_backtest_pattern_spec,
)
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.repositories.backtest import BacktestRepository
from app.repositories.balance import BalanceRepository
from app.repositories.report import ReportRepository
from app.repositories.trading_operation import TradingOperationRepository
from app.schemas.backtest import BacktestCreate, BacktestPriceMode, BacktestRead, BacktestStatus
from app.schemas.text_template import TextTemplateCreate
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.portfolio_service import PortfolioService
from app.services.text_template_service import TextTemplateService

_DEFAULT_BACKTEST_TEMPLATE = """# Portfolio Analysis ({{inputs.cycle_date}})

## Instructions
You are analyzing all positions in portfolio {{inputs.portfolio_name}}.
Analysis frequency: {{inputs.frequency}}.

CRITICAL: Today is {{inputs.cycle_date}}. Do NOT use any information
from after this date. If uncertain about timing, exclude it.

## Your Analysis
1. Assess the current business and market context for each position
2. Review the prior analysis reports provided below
3. Identify what changed since last review
4. Decide: BUY, SELL, or HOLD for each position
5. You may also suggest buying new symbols not currently held

## Response Format
Respond in this exact JSON:
{
  "overall_assessment": "brief portfolio summary",
  "decisions": [
    {
      "symbol": "TICKER",
      "action": "BUY|SELL|HOLD",
      "quantity": 5,
      "target_price": 185.50,
      "reasoning": "2-3 sentences"
    }
  ],
  "reflection": "what changed, what you got right/wrong"
}

This is an experimental simulation. No investment advice.
"""

_INTERNAL_BACKTEST_WEBHOOK_URL = "internal://ledger"
_INTERNAL_BACKTEST_WEBHOOK_TIMEOUT = 600


class BacktestService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory
        self.repository = BacktestRepository(session)
        self.balance_repository = BalanceRepository(session)
        self.report_repository = ReportRepository(session)
        self.template_service = TextTemplateService(session)
        self.portfolio_service = PortfolioService(session)
        self.trading_operation_repository = TradingOperationRepository(session)

    def list_backtests(self) -> list[BacktestRead]:
        backtests = self.repository.list_all()
        return [BacktestRead.model_validate(backtest) for backtest in backtests]

    def get_backtest(self, backtest_id: int) -> BacktestRead:
        return BacktestRead.model_validate(self.get_backtest_model(backtest_id))

    def get_backtest_model(self, backtest_id: int) -> Backtest:
        backtest = self.repository.get(backtest_id)
        if backtest is None:
            raise not_found_error("Backtest")
        return backtest

    def create_backtest(self, payload: BacktestCreate) -> BacktestRead:
        self.portfolio_service.get_portfolio_model(payload.portfolio_id)
        deposit_balance = self._resolve_deposit_balance(payload.portfolio_id)
        template_id = self._resolve_template_id(payload)
        orchestration_pattern_key = self._resolve_orchestration_pattern_key(
            payload.orchestration_pattern_key
        )
        webhook_url, webhook_timeout = self._resolve_webhook_settings(payload)

        backtest = Backtest(
            portfolio_id=payload.portfolio_id,
            deposit_balance_id=deposit_balance.id,
            name=payload.name,
            orchestration_pattern_key=orchestration_pattern_key,
            status=BacktestStatus.PENDING.value,
            frequency=payload.frequency.value,
            start_date=payload.start_date,
            end_date=payload.end_date,
            total_cycles=0,
            completed_cycles=0,
            template_id=template_id,
            webhook_url=webhook_url,
            webhook_timeout=webhook_timeout,
            price_mode=BacktestPriceMode.CLOSING_PRICE.value,
            commission_mode=payload.commission_mode.value,
            commission_value=payload.commission_value,
            benchmark_symbols=payload.benchmark_symbols,
        )

        try:
            self.repository.add(backtest)
            self.session.commit()
            self.session.refresh(backtest)
        except Exception:
            self.session.rollback()
            raise

        self.run_backtest(backtest.id)
        return BacktestRead.model_validate(backtest)

    def cancel_backtest(self, backtest_id: int) -> BacktestRead:
        backtest = self.get_backtest_model(backtest_id)
        if backtest.status not in {BacktestStatus.PENDING.value, BacktestStatus.RUNNING.value}:
            raise business_rule_error(
                "invalid_backtest_state",
                "Only pending or running backtests can be cancelled",
            )
        backtest.status = BacktestStatus.CANCELLED.value
        self.session.commit()
        self.session.refresh(backtest)
        return BacktestRead.model_validate(backtest)

    def delete_backtest(self, backtest_id: int) -> None:
        backtest = self.get_backtest_model(backtest_id)
        if backtest.status not in {
            BacktestStatus.COMPLETED.value,
            BacktestStatus.FAILED.value,
            BacktestStatus.CANCELLED.value,
        }:
            raise business_rule_error(
                "invalid_backtest_state",
                "Only terminal backtests can be deleted",
            )
        self.report_repository.delete_for_backtest_tag(f"backtest_{backtest.id}")
        self.trading_operation_repository.delete_for_backtest(backtest.id)
        self.repository.delete(backtest)
        self.session.commit()

    def run_backtest(self, backtest_id: int) -> None:
        def _run() -> None:
            cycle_service = BacktestCycleService(self.session, self.session_factory)
            cycle_service.start_backtest(backtest_id)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _resolve_deposit_balance(self, portfolio_id: int) -> Balance:
        balances = self.balance_repository.list_deposit_balances_for_portfolio(portfolio_id)
        if not balances:
            raise business_rule_error(
                "missing_deposit_balance",
                "Backtests require at least one deposit balance",
            )
        return max(balances, key=lambda balance: balance.amount)

    def _resolve_template_id(self, payload: BacktestCreate) -> int:
        if payload.template_id is not None:
            self.template_service.get_template_model(payload.template_id)
            return payload.template_id
        if not payload.create_template:
            raise business_rule_error(
                "missing_template",
                "Select a template or enable default template creation",
            )
        created = self.template_service.create_template(
            TextTemplateCreate(
                name=payload.template_name or f"{payload.name} Backtest Template",
                content=_DEFAULT_BACKTEST_TEMPLATE,
            )
        )
        return created.id

    def _resolve_orchestration_pattern_key(self, pattern_key: str | None) -> str:
        if pattern_key is None:
            return DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY

        normalized = pattern_key.strip()
        if not normalized:
            return DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY

        pattern_spec = get_backtest_pattern_spec(normalized)
        if pattern_spec is None:
            raise business_rule_error(
                "invalid_orchestration_pattern",
                f"Unknown orchestration pattern: {normalized}",
            )

        return pattern_spec.key

    def _resolve_webhook_settings(self, payload: BacktestCreate) -> tuple[str, int]:
        if payload.webhook_url:
            return (
                payload.webhook_url,
                payload.webhook_timeout or _INTERNAL_BACKTEST_WEBHOOK_TIMEOUT,
            )

        return _INTERNAL_BACKTEST_WEBHOOK_URL, _INTERNAL_BACKTEST_WEBHOOK_TIMEOUT
