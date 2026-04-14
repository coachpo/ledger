from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.models.backtest import Backtest
from app.schemas.backtest import TradeDecision
from app.services.backtest_engine import BacktestEngine

RunStateLoader = Callable[[int], dict[str, Any]]
RunStateUpdater = Callable[..., None]
CycleDispatcher = Callable[[int, date], None]
CycleStatusClearer = Callable[[int], None]


@dataclass(frozen=True)
class BacktestCycleCompletionResult:
    backtest_id: int
    next_cycle_date: date | None
    finished: bool


class BacktestCompletionService:
    def complete_cycle(
        self,
        *,
        backtest_id: int,
        cycle_date: date,
        engine: BacktestEngine,
        market_data: dict[str, dict[str, Decimal]],
        load_run_state: RunStateLoader,
        update_run_state: RunStateUpdater,
        clear_cycle_status: CycleStatusClearer,
        dispatch_next_cycle: CycleDispatcher,
        decisions: list[TradeDecision] | None = None,
        report_markdown: str | None = None,
        report_slug: str | None = None,
        run_id: int | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> BacktestCycleCompletionResult:
        if run_id is not None:
            if session_factory is None:
                raise RuntimeError("Runtime-backed completion requires a session factory")
            self.ensure_runtime_completion_allowed(
                session_factory=session_factory,
                backtest_id=backtest_id,
                run_id=run_id,
            )

        run_state = load_run_state(backtest_id)
        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule",
            )

        persisted_report_slug = report_slug
        if report_markdown is not None and persisted_report_slug is None:
            persisted_report_slug = engine.store_cycle_report(cycle_date, report_markdown)
        trade_log = list(run_state["trade_log"])
        if decisions is not None:
            cycle_trades = engine.apply_cycle_trades(
                cycle_date=cycle_date,
                decisions=decisions,
                market_data=market_data,
                report_slug=persisted_report_slug,
            )
            trade_log.extend(cycle_trades)

        date_str, equity_value = engine.record_cycle_equity(cycle_date, market_data)
        benchmark_history = run_state["benchmark_history"]
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
            clear_cycle_status(backtest_id)
            if run_id is not None and session_factory is not None:
                self.mark_runtime_completion_consumed(
                    session_factory=session_factory,
                    backtest_id=backtest_id,
                    run_id=run_id,
                )
            return BacktestCycleCompletionResult(
                backtest_id=backtest_id,
                next_cycle_date=None,
                finished=True,
            )

        next_cycle_date = schedule[current_index + 1]
        update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        if run_id is not None and session_factory is not None:
            self.mark_runtime_completion_consumed(
                session_factory=session_factory,
                backtest_id=backtest_id,
                run_id=run_id,
            )
        dispatch_next_cycle(backtest_id, next_cycle_date)
        return BacktestCycleCompletionResult(
            backtest_id=backtest_id,
            next_cycle_date=next_cycle_date,
            finished=False,
        )

    @staticmethod
    def get_backtest_or_raise(session_factory: sessionmaker[Session], backtest_id: int) -> Backtest:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)
        return backtest

    @staticmethod
    def clear_cycle_status(session_factory: sessionmaker[Session], backtest_id: int) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.current_cycle_status = None
            session.commit()

    @staticmethod
    def load_run_state(session_factory: sessionmaker[Session], backtest_id: int) -> dict[str, Any]:
        with session_factory() as session:
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
                date.fromisoformat(str(raw_cycle_date))
                for raw_cycle_date in raw_run_state.get("schedule", [])
            ],
            "benchmark_history": benchmark_history,
            "trade_log": trade_log,
            "equity_points": equity_points,
        }

    @staticmethod
    def update_run_state(
        session_factory: sessionmaker[Session],
        backtest_id: int,
        *,
        equity_points: list[tuple[str, Decimal]],
        trade_log: list[dict[str, Any]],
    ) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return

            existing_results = dict(backtest.results) if isinstance(backtest.results, dict) else {}
            existing_run_state = existing_results.get("_run_state", {})
            run_state = dict(existing_run_state) if isinstance(existing_run_state, dict) else {}
            if not isinstance(run_state, dict):
                run_state = {}

            run_state["equity_points"] = [
                (point_date, str(value)) for point_date, value in equity_points
            ]
            run_state["trade_log"] = trade_log
            backtest.results = {**existing_results, "_run_state": run_state}
            session.commit()

    @staticmethod
    def set_current_run_id(
        session_factory: sessionmaker[Session],
        backtest_id: int,
        run_id: int,
    ) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            backtest.current_run_id = run_id
            session.commit()

    @staticmethod
    def clear_current_run_if_matches(
        session_factory: sessionmaker[Session],
        backtest_id: int,
        run_id: int,
    ) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            if backtest.current_run_id != run_id:
                return
            backtest.current_run_id = None
            session.commit()

    @staticmethod
    def ensure_runtime_completion_allowed(
        *,
        session_factory: sessionmaker[Session],
        backtest_id: int,
        run_id: int,
    ) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            if backtest.last_completed_run_id == run_id:
                raise business_rule_error(
                    "backtest_runtime_run_already_consumed",
                    f"Runtime run {run_id} was already consumed for backtest {backtest_id}",
                )
            if backtest.current_run_id != run_id:
                raise business_rule_error(
                    "backtest_runtime_run_stale",
                    (
                        f"Runtime run {run_id} is stale for backtest {backtest_id}; "
                        f"currentRunId={backtest.current_run_id}"
                    ),
                )

    @staticmethod
    def mark_runtime_completion_consumed(
        *,
        session_factory: sessionmaker[Session],
        backtest_id: int,
        run_id: int,
    ) -> None:
        with session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            if backtest.last_completed_run_id == run_id:
                raise business_rule_error(
                    "backtest_runtime_run_already_consumed",
                    f"Runtime run {run_id} was already consumed for backtest {backtest_id}",
                )
            if backtest.current_run_id != run_id:
                raise business_rule_error(
                    "backtest_runtime_run_stale",
                    (
                        f"Runtime run {run_id} is stale for backtest {backtest_id}; "
                        f"currentRunId={backtest.current_run_id}"
                    ),
                )
            backtest.current_run_id = None
            backtest.last_completed_run_id = run_id
            session.commit()
