from __future__ import annotations

import logging
import threading
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import business_rule_error, not_found_error
from app.models.backtest import Backtest
from app.schemas.backtest import BacktestStatus, TradeDecision
from app.schemas.backtest_callback import (
    CycleCompleteResponse,
    CycleReportUpload,
    CycleTradeResult,
    CycleTradesRequest,
    CycleTradesResponse,
)
from app.schemas.report import ReportMetadata
from app.services.backtest_engine import BacktestEngine
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)

_TERMINAL_BACKTEST_STATUSES = {
    BacktestStatus.COMPLETED,
    BacktestStatus.FAILED,
    BacktestStatus.CANCELLED,
}


class BacktestCycleService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory

    def start_backtest(self, backtest_id: int) -> None:
        engine = self._build_engine(backtest_id)

        try:
            schedule, benchmark_history = engine.initialize()
            if not schedule:
                return

            self._store_run_state(backtest_id, schedule, benchmark_history)
            self._dispatch_cycle(backtest_id, schedule[0])
        except Exception as exc:
            logger.exception("Failed to start backtest %d", backtest_id)
            engine._mark_failed(str(exc))

    def handle_report_callback(
        self, backtest_id: int, cycle_date: date, payload: CycleReportUpload
    ) -> str:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        with self.session_factory() as session:
            report_service = ReportService(session)
            report = report_service.create_external_report(
                name=payload.name,
                slug=payload.name,
                content=payload.content,
                metadata=ReportMetadata.model_validate(
                    {
                        "tags": payload.tags + [f"backtest_{backtest_id}"],
                        "analysis": {
                            "backtestId": backtest_id,
                            "cycleDate": cycle_date.isoformat(),
                            "reviewType": "backtest_analysis",
                        },
                    }
                ),
            )
        return report.slug

    def handle_trades_callback(
        self, backtest_id: int, cycle_date: date, payload: CycleTradesRequest
    ) -> CycleTradesResponse:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        engine = self._build_engine(backtest_id)
        market_data = engine._load_cycle_market_data(engine._portfolio_symbols(), cycle_date)
        trade_results = engine.apply_cycle_trades(
            cycle_date=cycle_date,
            decisions=payload.decisions,
            market_data=market_data,
            report_slug=payload.report_slug,
        )

        run_state = self._load_run_state(backtest_id)
        trade_log = list(run_state["trade_log"])
        trade_log.extend(trade_results)
        self._update_run_state(
            backtest_id,
            equity_points=run_state["equity_points"],
            trade_log=trade_log,
        )

        executed = [
            CycleTradeResult(
                symbol=str(trade["symbol"]),
                action=str(trade["side"]),
                executed=trade.get("executed"),
                executed_price=trade.get("executedPrice"),
                failure_reason=trade.get("failureReason"),
            )
            for trade in trade_results
        ]
        return CycleTradesResponse(executed=executed)

    def handle_cycle_complete(self, backtest_id: int, cycle_date: date) -> CycleCompleteResponse:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        engine = self._build_engine(backtest_id)
        market_data = engine._load_cycle_market_data(engine._portfolio_symbols(), cycle_date)
        date_str, equity_value = engine.record_cycle_equity(cycle_date, market_data)

        run_state = self._load_run_state(backtest_id)
        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule",
            )

        benchmark_history = run_state["benchmark_history"]
        trade_log = run_state["trade_log"]
        equity_points = list(run_state["equity_points"])
        if equity_points and equity_points[-1][0] == date_str:
            equity_points[-1] = (date_str, equity_value)
        else:
            equity_points.append((date_str, equity_value))

        current_index = schedule.index(cycle_date)
        is_last_cycle = current_index >= len(schedule) - 1
        if is_last_cycle:
            engine.finalize(
                equity_points=equity_points,
                benchmark_history=benchmark_history,
                trade_log=trade_log,
                schedule=schedule,
            )
            self._clear_cycle_status(backtest_id)
            refreshed = self._get_backtest_or_raise(backtest_id)
            return CycleCompleteResponse(
                backtest_id=backtest_id,
                status=refreshed.status,
                completed_cycles=refreshed.completed_cycles,
                total_cycles=refreshed.total_cycles,
                next_cycle_date=None,
                finished=True,
            )

        next_cycle_date = schedule[current_index + 1]
        self._update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        self._dispatch_cycle(backtest_id, next_cycle_date)

        refreshed = self._get_backtest_or_raise(backtest_id)
        return CycleCompleteResponse(
            backtest_id=backtest_id,
            status=refreshed.status,
            completed_cycles=refreshed.completed_cycles,
            total_cycles=refreshed.total_cycles,
            next_cycle_date=next_cycle_date.isoformat(),
            finished=False,
        )

    def _dispatch_cycle(self, backtest_id: int, cycle_date: date) -> None:
        engine = self._build_engine(backtest_id)

        try:
            cycle_ctx = engine.execute_cycle(cycle_date)
        except Exception as exc:
            logger.exception("Failed to prepare cycle %s for backtest %d", cycle_date, backtest_id)
            engine._mark_failed(str(exc))
            self._clear_cycle_status(backtest_id)
            return

        if cycle_ctx.get("cancelled"):
            self._clear_cycle_status(backtest_id)
            return

        settings = get_settings()
        if settings.backtest_test_mode:
            self._deterministic_cycle(backtest_id, cycle_date, engine, cycle_ctx)
            return

        backtest = self._get_backtest_or_raise(backtest_id)
        if not getattr(settings, "public_base_url", None):
            engine._mark_failed(
                "PUBLIC_BASE_URL is required for webhook backtests so external workers can "
                "reach report and callback URLs"
            )
            self._clear_cycle_status(backtest_id)
            return

        self._set_cycle_status(
            backtest_id,
            BacktestStatus.AWAITING_CALLBACK,
            cycle_date=cycle_date,
        )

        payload = {
            "backtestId": backtest_id,
            "cycleDate": cycle_date.isoformat(),
            "totalCycles": backtest.total_cycles,
            "completedCycles": backtest.completed_cycles,
            "frequency": backtest.frequency,
            "reportSlug": cycle_ctx["prompt_report_slug"],
            "reportDownloadUrl": self._resolve_public_url(
                settings,
                f"/api/v1/reports/{cycle_ctx['prompt_report_slug']}/download",
            ),
            "callbackBaseUrl": self._resolve_public_url(
                settings,
                f"/api/v1/backtests/{backtest_id}/cycles/{cycle_date.isoformat()}",
            ),
            "benchmarkSymbols": backtest.benchmark_symbols,
        }

        try:
            response = httpx.post(backtest.webhook_url, json=payload, timeout=30.0)
            response.raise_for_status()
        except Exception as exc:
            logger.error("Webhook dispatch failed for backtest %d: %s", backtest_id, exc)
            engine._mark_failed(f"Webhook dispatch failed: {exc}")
            self._clear_cycle_status(backtest_id)
            return

        timer = threading.Timer(
            backtest.webhook_timeout,
            self._handle_timeout,
            args=[backtest_id, cycle_date],
        )
        timer.daemon = True
        timer.start()

    def _handle_timeout(self, backtest_id: int, cycle_date: date) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            if backtest.current_cycle_status not in {
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            }:
                return
            if backtest.current_cycle_date != cycle_date:
                return
            backtest.status = BacktestStatus.FAILED
            backtest.error_message = f"Webhook callback timed out after {backtest.webhook_timeout}s"
            backtest.current_cycle_status = None
            session.commit()

    def _deterministic_cycle(
        self,
        backtest_id: int,
        cycle_date: date,
        engine: BacktestEngine,
        cycle_ctx: dict[str, Any],
    ) -> None:
        symbols = engine._portfolio_symbols()
        if not symbols:
            decisions = [
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=2,
                    target_price=None,
                    reasoning="Deterministic starter position",
                )
            ]
        else:
            decisions = [
                TradeDecision(
                    symbol=symbol,
                    action="HOLD",
                    quantity=None,
                    target_price=None,
                    reasoning="Deterministic hold",
                )
                for symbol in symbols
            ]

        run_state = self._load_run_state(backtest_id)
        trade_log = list(run_state["trade_log"])
        cycle_trades = engine.apply_cycle_trades(
            cycle_date=cycle_date,
            decisions=decisions,
            market_data=cycle_ctx["market_data"],
            report_slug=cycle_ctx.get("prompt_report_slug"),
        )
        trade_log.extend(cycle_trades)

        date_str, equity_value = engine.record_cycle_equity(cycle_date, cycle_ctx["market_data"])
        equity_points = list(run_state["equity_points"])
        if equity_points and equity_points[-1][0] == date_str:
            equity_points[-1] = (date_str, equity_value)
        else:
            equity_points.append((date_str, equity_value))

        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            engine._mark_failed(
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule"
            )
            self._clear_cycle_status(backtest_id)
            return

        benchmark_history = run_state["benchmark_history"]
        current_index = schedule.index(cycle_date)
        if current_index >= len(schedule) - 1:
            engine.finalize(
                equity_points=equity_points,
                benchmark_history=benchmark_history,
                trade_log=trade_log,
                schedule=schedule,
            )
            self._clear_cycle_status(backtest_id)
            return

        self._update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        self._dispatch_cycle(backtest_id, schedule[current_index + 1])

    def _build_engine(self, backtest_id: int) -> BacktestEngine:
        from app.services.quote_provider import (
            DeterministicQuoteProvider,
            YahooFinanceQuoteProvider,
        )

        settings = get_settings()
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)

        quote_provider: Any
        if settings.backtest_test_mode:
            quote_provider = DeterministicQuoteProvider()
        else:
            quote_provider = YahooFinanceQuoteProvider(
                timeout=settings.quote_provider_timeout_seconds
            )

        return BacktestEngine(
            backtest=backtest,
            session_factory=self.session_factory,
            settings=settings,
            quote_provider=quote_provider,
        )

    def _get_backtest_or_raise(self, backtest_id: int) -> Backtest:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)
        return backtest

    def _validate_cycle_status(
        self, backtest: Backtest, cycle_date: date, *, allow: list[str]
    ) -> None:
        if backtest.status in _TERMINAL_BACKTEST_STATUSES:
            raise business_rule_error(
                "invalid_backtest_state",
                f"Backtest is {backtest.status}, cannot process callbacks",
            )

        if backtest.current_cycle_date is not None and backtest.current_cycle_date != cycle_date:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                (
                    f"Backtest is waiting for cycle {backtest.current_cycle_date.isoformat()}, "
                    f"not {cycle_date.isoformat()}"
                ),
            )

        if backtest.current_cycle_status not in allow:
            raise business_rule_error(
                "invalid_backtest_cycle_status",
                (
                    f"Backtest cycle status is {backtest.current_cycle_status}, "
                    f"expected one of {allow}"
                ),
            )

    def _set_cycle_status(
        self, backtest_id: int, status: str, *, cycle_date: date | None = None
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.current_cycle_status = status
            if cycle_date is not None:
                backtest.current_cycle_date = cycle_date
            session.commit()

    def _clear_cycle_status(self, backtest_id: int) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.current_cycle_status = None
            session.commit()

    @staticmethod
    def _resolve_public_url(settings: Any, path: str) -> str:
        public_base_url = getattr(settings, "public_base_url", None)
        if not public_base_url:
            return path
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{public_base_url}{normalized_path}"

    def _store_run_state(
        self,
        backtest_id: int,
        schedule: list[date],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.results = {
                "_run_state": {
                    "schedule": [cycle_date.isoformat() for cycle_date in schedule],
                    "benchmark_history": {
                        symbol: [(point_date, str(value)) for point_date, value in points]
                        for symbol, points in benchmark_history.items()
                    },
                    "trade_log": [],
                    "equity_points": [],
                }
            }
            session.commit()

    def _load_run_state(self, backtest_id: int) -> dict[str, Any]:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            raw_results = backtest.results if backtest is not None else None

        if not isinstance(raw_results, dict):
            return {
                "schedule": [],
                "benchmark_history": {},
                "trade_log": [],
                "equity_points": [],
            }

        raw_run_state = raw_results.get("_run_state", {})
        if not isinstance(raw_run_state, dict):
            raw_run_state = {}

        raw_benchmark_history = raw_run_state.get("benchmark_history", {})
        benchmark_history: dict[str, list[tuple[str, Decimal]]] = {}
        if isinstance(raw_benchmark_history, dict):
            for symbol, points in raw_benchmark_history.items():
                if not isinstance(symbol, str) or not isinstance(points, list):
                    continue
                benchmark_history[symbol] = [
                    (str(point_date), Decimal(str(value))) for point_date, value in points
                ]

        raw_equity_points = raw_run_state.get("equity_points", [])
        equity_points = [
            (str(point_date), Decimal(str(value))) for point_date, value in raw_equity_points
        ]

        raw_trade_log = raw_run_state.get("trade_log", [])
        trade_log = [item for item in raw_trade_log if isinstance(item, dict)]

        return {
            "schedule": [
                date.fromisoformat(str(cycle_date))
                for cycle_date in raw_run_state.get("schedule", [])
            ],
            "benchmark_history": benchmark_history,
            "trade_log": trade_log,
            "equity_points": equity_points,
        }

    def _update_run_state(
        self,
        backtest_id: int,
        *,
        equity_points: list[tuple[str, Decimal]],
        trade_log: list[dict[str, Any]],
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return

            existing_results = backtest.results if isinstance(backtest.results, dict) else {}
            run_state = existing_results.get("_run_state", {})
            if not isinstance(run_state, dict):
                run_state = {}

            run_state["equity_points"] = [
                (point_date, str(value)) for point_date, value in equity_points
            ]
            run_state["trade_log"] = trade_log
            backtest.results = {**existing_results, "_run_state": run_state}
            session.commit()
