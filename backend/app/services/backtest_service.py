from __future__ import annotations

import threading
from collections.abc import Mapping

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.repositories.backtest import BacktestRepository
from app.repositories.balance import BalanceRepository
from app.repositories.report import ReportRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_run_artifact import RuntimeRunArtifactRepository
from app.repositories.trading_operation import TradingOperationRepository
from app.schemas.backtest import (
    BacktestCreate,
    BacktestExecutionOwner,
    BacktestPriceMode,
    BacktestRead,
    BacktestStatus,
)
from app.schemas.text_template import TextTemplateCreate
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.backtest_classification_service import BacktestClassificationService
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
_RUNTIME_CANCELLABLE_STATUSES = {"QUEUED", "RUNNING", "WAITING_APPROVAL"}


class BacktestService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory
        self.repository = BacktestRepository(session)
        self.balance_repository = BalanceRepository(session)
        self.report_repository = ReportRepository(session)
        self.runtime_run_repository = RuntimeRunRepository(session)
        self.runtime_artifact_repository = RuntimeRunArtifactRepository(session)
        self.template_service = TextTemplateService(session)
        self.portfolio_service = PortfolioService(session)
        self.trading_operation_repository = TradingOperationRepository(session)
        self.classification_service = BacktestClassificationService(session)

    def list_backtests(self) -> list[BacktestRead]:
        backtests = self.repository.list_all()
        return self._build_backtest_reads(backtests)

    def get_backtest(self, backtest_id: int) -> BacktestRead:
        backtest = self.get_backtest_model(backtest_id)
        runtime_runs, runtime_artifacts = self._load_runtime_projection_records([backtest])
        return self._build_backtest_read(
            backtest,
            runtime_runs=runtime_runs,
            runtime_artifacts=runtime_artifacts,
        )

    def get_backtest_model(self, backtest_id: int) -> Backtest:
        backtest = self.repository.get(backtest_id)
        if backtest is None:
            raise not_found_error("Backtest")
        return backtest

    def create_backtest(self, payload: BacktestCreate) -> BacktestRead:
        self.portfolio_service.get_portfolio_model(payload.portfolio_id)
        deposit_balance = self._resolve_deposit_balance(payload.portfolio_id)
        template_id = self._resolve_template_id(payload)
        routing = self.classification_service.resolve_create_time_routing(
            launch_mode=payload.launch_mode,
            requested_pattern_key=payload.orchestration_pattern_key,
        )
        webhook_url, webhook_timeout = self._resolve_webhook_settings(payload)

        backtest = Backtest(
            portfolio_id=payload.portfolio_id,
            deposit_balance_id=deposit_balance.id,
            name=payload.name,
            orchestration_pattern_key=routing.orchestration_pattern_key,
            launch_mode=routing.launch_mode.value,
            workflow_spec_key=routing.workflow_spec_key,
            workflow_spec_version=routing.workflow_spec_version,
            execution_owner=routing.execution_owner.value,
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
        if backtest.execution_owner == BacktestExecutionOwner.RUNTIME_V2.value:
            return self._cancel_runtime_backtest(backtest)
        return self._cancel_legacy_backtest(backtest)

    def _cancel_legacy_backtest(self, backtest: Backtest) -> BacktestRead:
        if backtest.status not in {BacktestStatus.PENDING.value, BacktestStatus.RUNNING.value}:
            raise business_rule_error(
                "invalid_backtest_state",
                "Only pending or running backtests can be cancelled",
            )
        backtest.status = BacktestStatus.CANCELLED.value
        backtest.error_message = None
        self.session.commit()
        self.session.refresh(backtest)
        runtime_runs, runtime_artifacts = self._load_runtime_projection_records([backtest])
        return self._build_backtest_read(
            backtest,
            runtime_runs=runtime_runs,
            runtime_artifacts=runtime_artifacts,
        )

    def _cancel_runtime_backtest(self, backtest: Backtest) -> BacktestRead:
        runtime_runs, runtime_artifacts = self._load_runtime_projection_records([backtest])
        projection = self._project_runtime_backtest_read(
            backtest,
            runtime_runs=runtime_runs,
            runtime_artifacts=runtime_artifacts,
        )
        projected_status = projection["status"] if projection is not None else backtest.status

        runtime_run: RuntimeRun | None = None
        if backtest.current_run_id is not None:
            runtime_run = runtime_runs.get(backtest.current_run_id)

        if runtime_run is not None and runtime_run.status in _RUNTIME_CANCELLABLE_STATUSES:
            AgentRuntimeService(self.session).cancel_run(runtime_run.id, commit=False)
            backtest.status = BacktestStatus.CANCELLED.value
            backtest.current_cycle_status = BacktestStatus.CANCELLED.value
            backtest.current_run_id = None
            backtest.last_completed_run_id = runtime_run.id
            backtest.error_message = None
            self.session.commit()
            self.session.refresh(backtest)
            runtime_runs, runtime_artifacts = self._load_runtime_projection_records([backtest])
            return self._build_backtest_read(
                backtest,
                runtime_runs=runtime_runs,
                runtime_artifacts=runtime_artifacts,
            )

        if projected_status not in {BacktestStatus.PENDING.value, BacktestStatus.RUNNING.value}:
            raise business_rule_error(
                "invalid_backtest_state",
                "Only pending or running backtests can be cancelled",
            )

        backtest.status = BacktestStatus.CANCELLED.value
        backtest.current_cycle_status = BacktestStatus.CANCELLED.value
        backtest.current_run_id = None
        backtest.error_message = None
        self.session.commit()
        self.session.refresh(backtest)
        runtime_runs, runtime_artifacts = self._load_runtime_projection_records([backtest])
        return self._build_backtest_read(
            backtest,
            runtime_runs=runtime_runs,
            runtime_artifacts=runtime_artifacts,
        )

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
        return self.classification_service._normalize_orchestration_pattern_key(pattern_key)

    def _resolve_webhook_settings(self, payload: BacktestCreate) -> tuple[str, int]:
        if payload.webhook_url:
            return (
                payload.webhook_url,
                payload.webhook_timeout or _INTERNAL_BACKTEST_WEBHOOK_TIMEOUT,
            )

        return _INTERNAL_BACKTEST_WEBHOOK_URL, _INTERNAL_BACKTEST_WEBHOOK_TIMEOUT

    def _build_backtest_reads(self, backtests: list[Backtest]) -> list[BacktestRead]:
        runtime_runs, runtime_artifacts = self._load_runtime_projection_records(backtests)
        return [
            self._build_backtest_read(
                backtest,
                runtime_runs=runtime_runs,
                runtime_artifacts=runtime_artifacts,
            )
            for backtest in backtests
        ]

    def _build_backtest_read(
        self,
        backtest: Backtest,
        *,
        runtime_runs: Mapping[int, RuntimeRun],
        runtime_artifacts: Mapping[int, RuntimeRunArtifact],
    ) -> BacktestRead:
        read_model = BacktestRead.model_validate(backtest)
        projection = self._project_runtime_backtest_read(
            backtest,
            runtime_runs=runtime_runs,
            runtime_artifacts=runtime_artifacts,
        )
        if projection is None:
            return read_model

        payload = read_model.model_dump(mode="python")
        payload["status"] = projection["status"]
        payload["current_cycle_status"] = projection["current_cycle_status"]
        payload["error_message"] = projection["error_message"]
        return BacktestRead.model_validate(payload)

    def _load_runtime_projection_records(
        self, backtests: list[Backtest]
    ) -> tuple[dict[int, RuntimeRun], dict[int, RuntimeRunArtifact]]:
        if not backtests:
            return {}, {}

        run_ids: set[int] = set()
        for backtest in backtests:
            if backtest.execution_owner != BacktestExecutionOwner.RUNTIME_V2.value:
                continue
            if backtest.current_run_id is not None:
                run_ids.add(backtest.current_run_id)
            if backtest.last_completed_run_id is not None:
                run_ids.add(backtest.last_completed_run_id)

        if not run_ids:
            return {}, {}

        runtime_runs = {run.id: run for run in self.runtime_run_repository.list_by_ids(run_ids)}
        runtime_artifacts = {
            artifact.run_id: artifact
            for artifact in self.runtime_artifact_repository.list_by_run_ids(run_ids)
        }
        return runtime_runs, runtime_artifacts

    def _project_runtime_backtest_read(
        self,
        backtest: Backtest,
        *,
        runtime_runs: Mapping[int, RuntimeRun],
        runtime_artifacts: Mapping[int, RuntimeRunArtifact],
    ) -> dict[str, str | None] | None:
        if backtest.execution_owner != BacktestExecutionOwner.RUNTIME_V2.value:
            return None

        selected_run_id = backtest.current_run_id or backtest.last_completed_run_id
        runtime_run = runtime_runs.get(selected_run_id) if selected_run_id is not None else None
        runtime_artifact = (
            runtime_artifacts.get(runtime_run.id) if runtime_run is not None else None
        )

        if backtest.current_run_id is None:
            if backtest.status == BacktestStatus.CANCELLED.value:
                return {
                    "status": BacktestStatus.CANCELLED.value,
                    "current_cycle_status": BacktestStatus.CANCELLED.value,
                    "error_message": None,
                }
            if backtest.status == BacktestStatus.FAILED.value:
                return {
                    "status": BacktestStatus.FAILED.value,
                    "current_cycle_status": BacktestStatus.FAILED.value,
                    "error_message": (
                        runtime_artifact.terminal_error_message
                        if runtime_run is not None
                        and runtime_run.status == "FAILED"
                        and runtime_artifact is not None
                        and runtime_artifact.terminal_error_message
                        else backtest.error_message
                    ),
                }
            if backtest.status == BacktestStatus.COMPLETED.value:
                return {
                    "status": BacktestStatus.COMPLETED.value,
                    "current_cycle_status": BacktestStatus.COMPLETED.value,
                    "error_message": backtest.error_message,
                }

        if runtime_run is None:
            return None

        if runtime_run.status in {"QUEUED", "RUNNING"}:
            return {
                "status": BacktestStatus.RUNNING.value,
                "current_cycle_status": BacktestStatus.RUNNING.value,
                "error_message": backtest.error_message,
            }
        if runtime_run.status == "WAITING_APPROVAL":
            return {
                "status": BacktestStatus.RUNNING.value,
                "current_cycle_status": "WAITING_APPROVAL",
                "error_message": backtest.error_message,
            }
        if runtime_run.status == "SUCCEEDED":
            additional_completed_cycle = 1 if backtest.current_run_id == runtime_run.id else 0
            final_cycle_completed = backtest.status == BacktestStatus.COMPLETED.value or (
                backtest.total_cycles > 0
                and backtest.completed_cycles + additional_completed_cycle >= backtest.total_cycles
            )
            return {
                "status": (
                    BacktestStatus.COMPLETED.value
                    if final_cycle_completed
                    else BacktestStatus.RUNNING.value
                ),
                "current_cycle_status": BacktestStatus.COMPLETED.value,
                "error_message": backtest.error_message,
            }
        if runtime_run.status == "FAILED":
            return {
                "status": BacktestStatus.FAILED.value,
                "current_cycle_status": BacktestStatus.FAILED.value,
                "error_message": (
                    runtime_artifact.terminal_error_message
                    if runtime_artifact is not None and runtime_artifact.terminal_error_message
                    else backtest.error_message
                ),
            }
        if runtime_run.status == "CANCELLED":
            return {
                "status": BacktestStatus.CANCELLED.value,
                "current_cycle_status": BacktestStatus.CANCELLED.value,
                "error_message": None,
            }
        return None
