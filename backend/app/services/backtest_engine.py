from __future__ import annotations

import importlib
import math
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import format_decimal, format_nullable_decimal, portfolio_cash_total
from app.models.backtest import Backtest
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.text_template import TextTemplate
from app.repositories.balance import BalanceRepository
from app.repositories.position import PositionRepository
from app.repositories.report import ReportRepository
from app.schemas.backtest import BacktestStatus, TradeDecision
from app.schemas.report import ReportMetadata
from app.schemas.trading_operation import BuyOperationCreate, SellOperationCreate
from app.services.quote_provider import ProviderHistorySeries, ProviderQuote
from app.services.report_service import ReportService
from app.services.template_compiler_service import TemplateCompilerService
from app.services.trading_operation_service import TradingOperationService

_RISK_FREE_RATE = Decimal("0")
_TERMINAL_STATUSES = {
    BacktestStatus.COMPLETED.value,
    BacktestStatus.FAILED.value,
    BacktestStatus.CANCELLED.value,
}


class _NullQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        return symbol

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        return ProviderQuote(
            symbol=symbol,
            price=Decimal("0"),
            previous_close=None,
            currency="USD",
            provider="backtest_null",
            as_of=None,
            name=symbol,
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        _ = (range_value, interval)
        return ProviderHistorySeries(
            symbol=symbol,
            currency="USD",
            provider="backtest_null",
            points=[],
        )


def _pandas() -> Any:
    return importlib.import_module("pandas")


def _calendar() -> Any:
    return importlib.import_module("exchange_calendars").get_calendar("XNYS")


class BacktestEngine:
    def __init__(
        self,
        *,
        backtest: Backtest | Any,
        session_factory: sessionmaker[Session] | None,
        settings: Any,
        quote_provider: Any | None,
        rng: random.Random | None = None,
    ) -> None:
        self.backtest = backtest
        self.session_factory = session_factory
        self.settings = settings
        self.quote_provider = quote_provider or _NullQuoteProvider()
        self.rng = rng or random.Random()

    def initialize(self) -> tuple[list[date], dict[str, list[tuple[str, Decimal]]]]:
        if self.session_factory is None:
            raise RuntimeError("Backtest engine requires a session factory")

        backtest = self._refresh_backtest()
        schedule = self._build_schedule(
            backtest.start_date,
            backtest.end_date,
            backtest.frequency,
        )

        with self.session_factory() as session:
            current = self._get_backtest(session)
            if current.status == BacktestStatus.CANCELLED.value:
                session.expunge(current)
                self.backtest = current
                return [], {}
            current.status = BacktestStatus.RUNNING.value
            current.error_message = None
            current.total_cycles = len(schedule)
            session.commit()

        benchmark_history = self._load_benchmark_history(schedule)
        return schedule, benchmark_history

    def execute_cycle(self, cycle_date: date) -> dict[str, Any]:
        current = self._refresh_backtest()
        if current.status == BacktestStatus.CANCELLED.value:
            return {"cancelled": True}

        symbols = self._portfolio_symbols()
        market_data = self._load_cycle_market_data(symbols, cycle_date)
        prompt_bundle = self._build_prompts(cycle_date)
        if isinstance(prompt_bundle, tuple):
            system_prompt, full_user_prompt = prompt_bundle
            prompt_bundle = {
                "system_prompt": system_prompt,
                "authored_entry_prompt_body": "",
                "compiled_entry_prompt_body": full_user_prompt,
                "execution_context_body": full_user_prompt,
                "full_user_prompt": full_user_prompt,
            }
        else:
            prompt_bundle = {
                **prompt_bundle,
                "system_prompt": (
                    f"Today is {cycle_date.isoformat()}. Do not use information from after this "
                    "date. "
                    "This is an experimental simulation. No investment advice."
                ),
            }
        prompt_report_slug = self._store_prompt_report(
            cycle_date,
            prompt_bundle["system_prompt"],
            prompt_bundle["full_user_prompt"],
        )

        return {
            "cancelled": False,
            "cycle_date": cycle_date,
            "market_data": market_data,
            "authored_entry_prompt_body": prompt_bundle["authored_entry_prompt_body"],
            "compiled_entry_prompt_body": prompt_bundle["compiled_entry_prompt_body"],
            "execution_context_body": prompt_bundle["execution_context_body"],
            "full_user_prompt": prompt_bundle["full_user_prompt"],
            "prompt_report_slug": prompt_report_slug,
        }

    def apply_cycle_trades(
        self,
        *,
        cycle_date: date,
        decisions: list[TradeDecision],
        market_data: dict[str, dict[str, Decimal]],
        report_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._apply_decisions(
            cycle_date=cycle_date,
            decisions=decisions,
            market_data=market_data,
            report_slug=report_slug,
        )

    def record_cycle_equity(
        self, cycle_date: date, market_data: dict[str, dict[str, Decimal]]
    ) -> tuple[str, Decimal]:
        equity_value = self._portfolio_value(market_data, cycle_date)
        self._update_progress(cycle_date)
        return cycle_date.isoformat(), equity_value

    def finalize(
        self,
        *,
        equity_points: list[tuple[str, Decimal]],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
        trade_log: list[dict[str, Any]],
        schedule: list[date],
    ) -> dict[str, Any]:
        results = self._compute_results(
            equity_points=equity_points,
            benchmark_history=benchmark_history,
            trade_log=trade_log,
        )
        if self.session_factory is not None:
            with self.session_factory() as session:
                current = self._get_backtest(session)
                if current.status != BacktestStatus.CANCELLED.value:
                    current.results = results
                    current.status = BacktestStatus.COMPLETED.value
                    current.current_cycle_date = schedule[-1] if schedule else None
                session.commit()
        self._refresh_backtest()
        return results

    def _build_schedule(self, start_date: date, end_date: date, frequency: str) -> list[date]:
        sessions = _calendar().sessions_in_range(start_date, end_date)
        trading_days = [session.date() for session in sessions]
        if frequency == "DAILY":
            return trading_days
        if frequency == "WEEKLY":
            return self._last_sessions_per_period(trading_days, period="week")
        return self._last_sessions_per_period(trading_days, period="month")

    def _prior_report_limit(self, frequency: str) -> int | None:
        return {"DAILY": 1, "WEEKLY": 5, "MONTHLY": None}[frequency]

    def _last_sessions_per_period(self, trading_days: list[date], *, period: str) -> list[date]:
        grouped: list[date] = []
        last_key: tuple[int, int] | None = None
        for trading_day in trading_days:
            if period == "week":
                key = (trading_day.isocalendar().year, trading_day.isocalendar().week)
            else:
                key = (trading_day.year, trading_day.month)
            if last_key != key:
                grouped.append(trading_day)
                last_key = key
                continue
            grouped[-1] = trading_day
        return grouped

    def _load_symbol_history(self, symbol: str, start: date, end: date) -> Any:
        pandas = _pandas()
        cache_dir = Path(self.settings.market_data_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{symbol}.parquet"

        cached: Any = None
        if cache_path.exists():
            cached = self._normalize_history_frame(pandas.read_parquet(cache_path))
            if not cached.empty:
                cached.index = pandas.to_datetime(cached.index)
                cached = cached.sort_index()
                if cached.index.max().date() >= end:
                    return self._slice_history_frame(cached, start, end)

        fetch_start = start
        if cached is not None and not cached.empty:
            fetch_start = max(cached.index.max().date() + timedelta(days=1), start)

        fetched = self._normalize_history_frame(self._download_history(symbol, fetch_start, end))
        if not fetched.empty:
            fetched.index = pandas.to_datetime(fetched.index)
            fetched = fetched.sort_index()
        if cached is not None and not cached.empty:
            combined = pandas.concat([cached, fetched]).sort_index()
            combined = combined[~combined.index.duplicated(keep="last")]
        else:
            combined = fetched

        combined.to_parquet(cache_path)
        return self._slice_history_frame(combined, start, end)

    def _download_history(self, symbol: str, start: date, end: date) -> Any:
        download_history = getattr(self.quote_provider, "download_history", None)
        if callable(download_history):
            raw_rows = download_history(symbol, start, end)
            if not isinstance(raw_rows, list):
                raise RuntimeError("History provider must return a list of row dictionaries")
            return self._rows_to_dataframe(raw_rows)

        pandas = _pandas()
        yf = importlib.import_module("yfinance")
        try:
            downloaded = yf.download(
                symbol,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=False,
            )
        except Exception:
            return pandas.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if downloaded.empty:
            return pandas.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = self._normalize_history_frame(
            downloaded.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
        )
        frame.index = pandas.to_datetime(frame.index)
        return frame.sort_index()

    def _rows_to_dataframe(self, rows: list[dict[str, object]]) -> Any:
        pandas = _pandas()
        if not rows:
            return pandas.DataFrame(columns=["open", "high", "low", "close", "volume"])

        frame = pandas.DataFrame(rows)
        frame["date"] = pandas.to_datetime(frame["date"])
        frame = frame.set_index("date").sort_index()
        return self._normalize_history_frame(frame.rename(columns=str.lower))

    def _slice_history_frame(self, frame: Any, start: date, end: date) -> Any:
        pandas = _pandas()
        return frame.loc[pandas.Timestamp(start) : pandas.Timestamp(end)]

    def _normalize_history_frame(self, frame: Any) -> Any:
        if getattr(frame.columns, "nlevels", 1) > 1:
            frame.columns = frame.columns.get_level_values(0)
        frame.columns = [str(column).lower() for column in frame.columns]
        frame = frame.loc[:, ~frame.columns.duplicated(keep="last")]
        return frame[["open", "high", "low", "close", "volume"]]

    def _build_prompts(self, cycle_date: date) -> dict[str, str]:
        if self.session_factory is None:
            raise RuntimeError("Backtest engine requires a session factory")

        with self.session_factory() as session:
            backtest = self._get_backtest(session)
            template = session.get(TextTemplate, backtest.template_id)
            if template is None:
                raise RuntimeError("Backtest template not found")

            portfolio = session.get(Portfolio, backtest.portfolio_id)
            if portfolio is None:
                raise RuntimeError("Portfolio not found")

            compiler = TemplateCompilerService(session)
            compiled_template = compiler.compile(
                template.content,
                inputs={
                    "cycle_date": cycle_date.isoformat(),
                    "portfolio_name": portfolio.name,
                    "frequency": backtest.frequency,
                },
            )
            positions = PositionRepository(session).list_for_portfolio(backtest.portfolio_id)
            balances = BalanceRepository(session).list_for_portfolio(backtest.portfolio_id)
            prior_reports = self._load_prior_reports(session, cycle_date)

        authored_entry_prompt_body = template.content
        compiled_entry_prompt_body = compiled_template
        market_context = self._render_market_context(positions, cycle_date)
        benchmark_context = self._render_benchmark_context(cycle_date)
        execution_context_body = "\n\n".join(
            [
                self._render_portfolio_state(positions, balances),
                market_context,
                benchmark_context,
                self._render_prior_reports(prior_reports),
            ]
        )

        full_user_prompt = "\n\n".join([execution_context_body, compiled_entry_prompt_body])
        return {
            "authored_entry_prompt_body": authored_entry_prompt_body,
            "compiled_entry_prompt_body": compiled_entry_prompt_body,
            "execution_context_body": execution_context_body,
            "full_user_prompt": full_user_prompt,
        }

    def _apply_decisions(
        self,
        *,
        cycle_date: date,
        decisions: list[TradeDecision],
        market_data: dict[str, dict[str, Decimal]],
        report_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.session_factory is None:
            raise RuntimeError("Backtest engine requires a session factory")

        decision_summaries: list[dict[str, Any]] = []
        trade_log: list[dict[str, Any]] = []

        with self.session_factory() as session:
            backtest = self._get_backtest(session)
            trading_service = TradingOperationService(session, self.quote_provider)
            position_repository = PositionRepository(session)

            for decision in decisions:
                summary: dict[str, Any] = {
                    "symbol": decision.symbol,
                    "action": decision.action,
                    "reasoning": decision.reasoning,
                }
                row = market_data.get(decision.symbol)
                if decision.quantity is not None:
                    summary["quantity"] = decision.quantity
                if decision.target_price is not None:
                    summary["targetPrice"] = format_decimal(decision.target_price, places=2)

                if decision.action == "HOLD":
                    summary["executed"] = None
                    decision_summaries.append(summary)
                    continue

                if row is None:
                    row = self._load_market_row(decision.symbol, cycle_date)
                if row is None:
                    summary["executed"] = False
                    summary["failureReason"] = "No market data for symbol"
                    decision_summaries.append(summary)
                    trade_log.append(
                        {
                            "cycleDate": cycle_date.isoformat(),
                            "symbol": decision.symbol,
                            "side": decision.action,
                            "quantity": format_nullable_decimal(
                                Decimal(decision.quantity)
                                if decision.quantity is not None
                                else None
                            ),
                            "requestedPrice": format_nullable_decimal(decision.target_price),
                            "executedPrice": None,
                            "executed": False,
                            "failureReason": "No market data for symbol",
                            "reportSlug": report_slug,
                        }
                    )
                    continue

                execution_price, executed, failure_reason = self._resolve_execution(decision, row)
                summary["executed"] = executed
                if failure_reason is not None:
                    summary["failureReason"] = failure_reason

                current_position = position_repository.get_by_symbol(
                    backtest.portfolio_id, decision.symbol
                )

                trade_entry = {
                    "cycleDate": cycle_date.isoformat(),
                    "symbol": decision.symbol,
                    "side": decision.action,
                    "quantity": format_nullable_decimal(
                        Decimal(decision.quantity) if decision.quantity is not None else None
                    ),
                    "requestedPrice": format_nullable_decimal(decision.target_price),
                    "executedPrice": format_nullable_decimal(execution_price),
                    "executed": executed,
                    "reportSlug": report_slug,
                }

                if not executed or execution_price is None or decision.quantity is None:
                    if failure_reason is not None:
                        trade_entry["failureReason"] = failure_reason
                    trade_log.append(trade_entry)
                    decision_summaries.append(summary)
                    continue

                commission = self._commission_value(execution_price, Decimal(decision.quantity))
                trade_entry["commission"] = format_decimal(commission, places=2)
                try:
                    if decision.action == "BUY":
                        trading_service.create_operation(
                            backtest.portfolio_id,
                            BuyOperationCreate(
                                balance_id=backtest.deposit_balance_id,
                                symbol=decision.symbol,
                                quantity=Decimal(decision.quantity),
                                price=execution_price,
                                commission=commission,
                                executed_at=self._cycle_execution_time(cycle_date),
                            ),
                            backtest_id=backtest.id,
                        )
                    else:
                        if current_position is not None:
                            profit = (
                                (execution_price - current_position.average_cost)
                                * Decimal(decision.quantity)
                            ) - commission
                            trade_entry["profit"] = format_decimal(profit, places=2)
                        trading_service.create_operation(
                            backtest.portfolio_id,
                            SellOperationCreate(
                                balance_id=backtest.deposit_balance_id,
                                symbol=decision.symbol,
                                quantity=Decimal(decision.quantity),
                                price=execution_price,
                                commission=commission,
                                executed_at=self._cycle_execution_time(cycle_date),
                            ),
                            backtest_id=backtest.id,
                        )
                except Exception as exc:
                    summary["executed"] = False
                    summary["failureReason"] = str(exc)
                    trade_entry["executed"] = False
                    trade_entry["failureReason"] = str(exc)
                trade_log.append(trade_entry)
                decision_summaries.append(summary)

            backtest.recent_activity = (backtest.recent_activity or [])[-9:] + [
                {"cycleDate": cycle_date.isoformat(), "decisions": decision_summaries}
            ]
            session.commit()

        self.backtest = self._refresh_backtest()
        return trade_log

    def _resolve_execution(
        self, decision: TradeDecision, row: dict[str, Decimal]
    ) -> tuple[Decimal | None, bool, str | None]:
        return row["close"], True, None

    def _commission_value(self, execution_price: Decimal, quantity: Decimal) -> Decimal:
        if self.backtest.commission_mode == "ZERO":
            return Decimal("0")
        if self.backtest.commission_mode == "FIXED":
            return Decimal(self.backtest.commission_value)
        return execution_price * quantity * Decimal(self.backtest.commission_value)

    def _cycle_execution_time(self, cycle_date: date) -> datetime:
        return datetime.combine(cycle_date, time(20, 30), tzinfo=UTC)

    def _compute_results(
        self,
        *,
        equity_points: list[tuple[str, Decimal]],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
        trade_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        starting_value = equity_points[0][1] if equity_points else Decimal("0")
        ending_value = equity_points[-1][1] if equity_points else Decimal("0")
        total_return = (
            (ending_value - starting_value) / starting_value if starting_value else Decimal("0")
        )

        if len(equity_points) > 1 and starting_value:
            start_day = date.fromisoformat(equity_points[0][0])
            end_day = date.fromisoformat(equity_points[-1][0])
            day_count = max((end_day - start_day).days, 1)
            annualized_return = (ending_value / starting_value) ** (
                Decimal("365") / Decimal(day_count)
            ) - 1
        else:
            annualized_return = Decimal("0")

        drawdown_curve, max_drawdown = self._drawdown_metrics(equity_points)
        daily_returns = self._daily_returns(equity_points)
        sharpe_ratio = self._sharpe_ratio(daily_returns)
        total_trades = len(
            [
                trade
                for trade in trade_log
                if trade.get("executed") and trade.get("side") in {"BUY", "SELL"}
            ]
        )
        total_commission = sum(
            (
                Decimal(str(trade.get("commission", "0")))
                for trade in trade_log
                if trade.get("executed")
            ),
            start=Decimal("0"),
        )
        win_rate = self._win_rate(trade_log)

        benchmark_summary: dict[str, dict[str, str]] = {}
        benchmark_curves: dict[str, list[dict[str, str]]] = {}
        for symbol, points in benchmark_history.items():
            if not points:
                continue
            start_price = points[0][1]
            end_price = points[-1][1]
            benchmark_summary[symbol] = {
                "startingPrice": format_decimal(start_price, places=2),
                "endingPrice": format_decimal(end_price, places=2),
                "totalReturn": format_decimal(
                    (end_price - start_price) / start_price if start_price else Decimal("0"),
                    places=4,
                ),
            }
            benchmark_curves[symbol] = [
                {
                    "date": point_date,
                    "value": format_decimal(
                        price / start_price if start_price else Decimal("0"), places=4
                    ),
                }
                for point_date, price in points
            ]

        return {
            "portfolio": {
                "startingValue": format_decimal(starting_value, places=2),
                "endingValue": format_decimal(ending_value, places=2),
                "totalReturn": format_decimal(total_return, places=4),
                "annualizedReturn": format_decimal(annualized_return, places=4),
                "maxDrawdown": format_decimal(max_drawdown, places=4),
                "sharpeRatio": format_decimal(sharpe_ratio, places=2),
                "totalTrades": total_trades,
                "winRate": format_decimal(win_rate, places=4),
                "totalCommission": format_decimal(total_commission, places=2),
            },
            "benchmarks": benchmark_summary,
            "equityCurve": [
                {"date": point_date, "value": format_decimal(value, places=2)}
                for point_date, value in equity_points
            ],
            "benchmarkCurves": benchmark_curves,
            "drawdownCurve": drawdown_curve,
            "trades": trade_log,
        }

    def _drawdown_metrics(
        self, equity_points: list[tuple[str, Decimal]]
    ) -> tuple[list[dict[str, str]], Decimal]:
        running_peak = Decimal("0")
        max_drawdown = Decimal("0")
        curve: list[dict[str, str]] = []
        for point_date, value in equity_points:
            running_peak = max(running_peak, value)
            drawdown = Decimal("0") if not running_peak else (value - running_peak) / running_peak
            if drawdown < max_drawdown:
                max_drawdown = drawdown
            curve.append({"date": point_date, "value": format_decimal(drawdown, places=4)})
        return curve, max_drawdown

    def _daily_returns(self, equity_points: list[tuple[str, Decimal]]) -> list[Decimal]:
        returns: list[Decimal] = []
        for (_, previous), (_, current) in zip(equity_points, equity_points[1:], strict=False):
            if previous == 0:
                continue
            returns.append((current - previous) / previous)
        return returns

    def _sharpe_ratio(self, daily_returns: list[Decimal]) -> Decimal:
        if not daily_returns:
            return Decimal("0")
        daily_return_floats = [float(value - _RISK_FREE_RATE) for value in daily_returns]
        volatility = pstdev(daily_return_floats)
        if volatility == 0:
            return Decimal("0")
        ratio = mean(daily_return_floats) / volatility * math.sqrt(252)
        return Decimal(str(ratio))

    def _win_rate(self, trade_log: list[dict[str, Any]]) -> Decimal:
        profitable_sells = [
            trade
            for trade in trade_log
            if trade.get("executed")
            and trade.get("side") == "SELL"
            and trade.get("profit") is not None
        ]
        if not profitable_sells:
            return Decimal("0")
        wins = sum(1 for trade in profitable_sells if Decimal(str(trade["profit"])) > 0)
        return Decimal(wins) / Decimal(len(profitable_sells))

    def _refresh_backtest(self) -> Backtest:
        if self.session_factory is None:
            return self.backtest
        with self.session_factory() as session:
            refreshed = self._get_backtest(session)
            session.expunge(refreshed)
        self.backtest = refreshed
        return refreshed

    def _mark_failed(self, error_message: str) -> None:
        if self.session_factory is None:
            return
        with self.session_factory() as session:
            backtest = self._get_backtest(session)
            if backtest.status not in _TERMINAL_STATUSES:
                backtest.status = BacktestStatus.FAILED.value
            backtest.error_message = error_message
            session.commit()
        self.backtest = self._refresh_backtest()

    def _get_backtest(self, session: Session) -> Backtest:
        backtest = session.get(Backtest, self.backtest.id)
        if backtest is None:
            raise RuntimeError("Backtest not found")
        return backtest

    def _portfolio_symbols(self) -> list[str]:
        if self.session_factory is None:
            return []
        with self.session_factory() as session:
            positions = PositionRepository(session).list_for_portfolio(self.backtest.portfolio_id)
        return [position.symbol for position in positions]

    def _load_cycle_market_data(
        self, symbols: list[str], cycle_date: date
    ) -> dict[str, dict[str, Decimal]]:
        pandas = _pandas()
        market_data: dict[str, dict[str, Decimal]] = {}
        history_start = cycle_date - timedelta(days=60)
        for symbol in symbols:
            history = self._load_symbol_history(symbol, history_start, cycle_date)
            if history.empty:
                continue
            row = history.loc[: pandas.Timestamp(cycle_date)].iloc[-1]
            market_data[symbol] = {
                "open": Decimal(str(row["open"])),
                "high": Decimal(str(row["high"])),
                "low": Decimal(str(row["low"])),
                "close": Decimal(str(row["close"])),
                "volume": Decimal(str(row["volume"])),
            }
        return market_data

    def _load_benchmark_history(self, schedule: list[date]) -> dict[str, list[tuple[str, Decimal]]]:
        pandas = _pandas()
        if not schedule:
            return {}
        history: dict[str, list[tuple[str, Decimal]]] = {}
        history_start = schedule[0]
        history_end = schedule[-1]
        for symbol in self.backtest.benchmark_symbols:
            frame = self._load_symbol_history(symbol, history_start, history_end)
            if frame.empty:
                history[symbol] = []
                continue
            points: list[tuple[str, Decimal]] = []
            for cycle_date in schedule:
                subset = frame.loc[: pandas.Timestamp(cycle_date)]
                if subset.empty:
                    continue
                points.append((cycle_date.isoformat(), Decimal(str(subset.iloc[-1]["close"]))))
            history[symbol] = points
        return history

    def _load_market_row(self, symbol: str, cycle_date: date) -> dict[str, Decimal] | None:
        pandas = _pandas()
        history = self._load_symbol_history(symbol, cycle_date - timedelta(days=60), cycle_date)
        if history.empty:
            return None
        subset = history.loc[: pandas.Timestamp(cycle_date)]
        if subset.empty:
            return None
        row = subset.iloc[-1]
        return {
            "open": Decimal(str(row["open"])),
            "high": Decimal(str(row["high"])),
            "low": Decimal(str(row["low"])),
            "close": Decimal(str(row["close"])),
            "volume": Decimal(str(row["volume"])),
        }

    def _portfolio_value(
        self, market_data: dict[str, dict[str, Decimal]], cycle_date: date
    ) -> Decimal:
        if self.session_factory is None:
            return Decimal("0")
        with self.session_factory() as session:
            balances = BalanceRepository(session).list_for_portfolio(self.backtest.portfolio_id)
            positions = PositionRepository(session).list_for_portfolio(self.backtest.portfolio_id)

        total = portfolio_cash_total(balances)

        for position in positions:
            row = market_data.get(position.symbol)
            if row is None:
                row = self._load_market_row(position.symbol, cycle_date)
                if row is None:
                    continue
                market_data[position.symbol] = row
            total += position.quantity * row["close"]
        return total

    def _update_progress(self, cycle_date: date) -> None:
        if self.session_factory is None:
            return
        with self.session_factory() as session:
            backtest = self._get_backtest(session)
            backtest.completed_cycles += 1
            backtest.current_cycle_date = cycle_date
            session.commit()
        self.backtest = self._refresh_backtest()

    def _store_cycle_report(self, cycle_date: date, analysis: str) -> str:
        if self.session_factory is None:
            raise RuntimeError("Backtest engine requires a session factory")
        with self.session_factory() as session:
            service = ReportService(session)
            report = service.create_external_report(
                name=f"backtest_{self.backtest.id}_{cycle_date.strftime('%Y%m%d')}",
                slug=f"backtest_{self.backtest.id}_{cycle_date.strftime('%Y%m%d')}",
                content=analysis,
                metadata=ReportMetadata.model_validate(
                    {
                        "tags": ["backtest", f"backtest_{self.backtest.id}"],
                        "analysis": {
                            "backtestId": self.backtest.id,
                            "cycleDate": cycle_date.isoformat(),
                            "reviewType": f"backtest_{self.backtest.frequency.lower()}",
                        },
                    }
                ),
            )
        return report.slug

    def _store_prompt_report(self, cycle_date: date, system_prompt: str, user_prompt: str) -> str:
        content = (
            f"# Cycle Prompt ({cycle_date.isoformat()})\n\n"
            f"## System\n{system_prompt}\n\n"
            f"## User\n{user_prompt}"
        )
        if self.session_factory is None:
            raise RuntimeError("Backtest engine requires a session factory")
        with self.session_factory() as session:
            service = ReportService(session)
            report = service.create_external_report(
                name=f"backtest_{self.backtest.id}_prompt_{cycle_date.strftime('%Y%m%d')}",
                slug=f"backtest_{self.backtest.id}_prompt_{cycle_date.strftime('%Y%m%d')}",
                content=content,
                metadata=ReportMetadata.model_validate(
                    {
                        "tags": ["backtest", f"backtest_{self.backtest.id}", "prompt"],
                        "analysis": {
                            "backtestId": self.backtest.id,
                            "cycleDate": cycle_date.isoformat(),
                            "reviewType": "backtest_prompt",
                        },
                    }
                ),
            )
        return report.slug

    def _load_prior_reports(self, session: Session, cycle_date: date) -> list[str]:
        reports = self.repositories_report(session).list_for_backtest_tag(
            f"backtest_{self.backtest.id}"
        )
        eligible: list[tuple[date, str]] = []
        for report in reversed(reports):
            metadata = report.metadata_ or {}
            analysis = metadata.get("analysis", {}) if isinstance(metadata, dict) else {}
            review_type = analysis.get("reviewType") if isinstance(analysis, dict) else None
            if review_type == "backtest_prompt":
                continue
            cycle_date_text = analysis.get("cycleDate") if isinstance(analysis, dict) else None
            if not isinstance(cycle_date_text, str):
                continue
            report_cycle_date = date.fromisoformat(cycle_date_text)
            if report_cycle_date >= cycle_date:
                continue
            if self.backtest.frequency == "MONTHLY" and (
                report_cycle_date.year != cycle_date.year
                or report_cycle_date.month != cycle_date.month
            ):
                continue
            eligible.append((report_cycle_date, report.content))

        limit = self._prior_report_limit(self.backtest.frequency)
        eligible.sort(key=lambda item: item[0], reverse=True)
        selected = eligible if limit is None else eligible[:limit]
        return [content for _, content in reversed(selected)]

    def repositories_report(self, session: Session) -> ReportRepository:
        return ReportRepository(session)

    def _render_portfolio_state(self, positions: list[Position], balances: list[Any]) -> str:
        balance_lines = [
            f"- {balance.label}: {balance.amount} {balance.currency} ({balance.operation_type})"
            for balance in balances
        ]
        position_lines = [
            (
                f"- {position.symbol}: {position.quantity} shares @ "
                f"{position.average_cost} {position.currency}"
            )
            for position in positions
        ]
        return "\n".join(
            [
                "Portfolio state:",
                "Balances:",
                *(balance_lines or ["- None"]),
                "Positions:",
                *(position_lines or ["- None"]),
            ]
        )

    def _render_market_context(self, positions: list[Position], cycle_date: date) -> str:
        pandas = _pandas()
        lines = ["Market data (last 30 trading days OHLCV):"]
        if not positions:
            lines.append("- No held symbols for this cycle")
            return "\n".join(lines)

        for position in positions:
            history = self._load_symbol_history(
                position.symbol, cycle_date - timedelta(days=90), cycle_date
            )
            subset = history.loc[: pandas.Timestamp(cycle_date)].tail(30)
            lines.append(f"{position.symbol}:")
            for point_date, row in subset.iterrows():
                lines.append(
                    f"- {point_date.date().isoformat()}: open={row['open']} high={row['high']} "
                    f"low={row['low']} close={row['close']} volume={row['volume']}"
                )
        return "\n".join(lines)

    def _render_benchmark_context(self, cycle_date: date) -> str:
        pandas = _pandas()
        lines = ["Benchmark performance since start date:"]
        for symbol in self.backtest.benchmark_symbols:
            history = self._load_symbol_history(symbol, self.backtest.start_date, cycle_date)
            subset = history.loc[: pandas.Timestamp(cycle_date)]
            if subset.empty:
                lines.append(f"- {symbol}: unavailable")
                continue
            starting_price = Decimal(str(subset.iloc[0]["close"]))
            ending_price = Decimal(str(subset.iloc[-1]["close"]))
            total_return = (
                (ending_price - starting_price) / starting_price if starting_price else Decimal("0")
            )
            lines.append(
                f"- {symbol}: start={starting_price} end={ending_price} "
                f"total_return={format_decimal(total_return, places=4)}"
            )
        return "\n".join(lines)

    def _render_prior_reports(self, prior_reports: list[str]) -> str:
        if not prior_reports:
            return "Prior reports:\n- None"
        return "Prior reports:\n" + "\n\n".join(prior_reports)
