from __future__ import annotations

import importlib
import random
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.repositories.trading_operation import TradingOperationRepository
from app.schemas.backtest import TradeDecision
from app.services.backtest_engine import BacktestEngine


class FakeHistoryProvider:
    def __init__(self, history_rows: list[dict[str, object]]) -> None:
        self.history_rows = history_rows
        self.fetch_history_calls = 0

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol} Holdings"

    def download_history(self, symbol: str, start: date, end: date) -> list[dict[str, object]]:
        _ = (symbol, start, end)
        self.fetch_history_calls += 1
        return self.history_rows


def build_engine(
    session_factory: sessionmaker[Session],
    *,
    backtest_id: int = 42,
    portfolio_id: int = 7,
    deposit_balance_id: int = 3,
    recent_activity: list[dict[str, Any]] | None = None,
) -> BacktestEngine:
    with session_factory() as session:
        portfolio = Portfolio(
            name="Engine Portfolio", slug="engine_portfolio", description=None, base_currency="USD"
        )
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Initial Cash",
            operation_type="DEPOSIT",
            amount=Decimal("100000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Engine Template", content="# Template")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            id=backtest_id,
            portfolio_id=portfolio.id if portfolio_id == 7 else portfolio_id,
            deposit_balance_id=balance.id if deposit_balance_id == 3 else deposit_balance_id,
            name="Engine Backtest",
            status="RUNNING",
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 12, 31),
            total_cycles=252,
            completed_cycles=0,
            template_id=template.id,
            webhook_url="http://localhost:5678/webhook/test",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
            recent_activity=recent_activity,
        )
        session.add(backtest)
        session.commit()
        session.refresh(backtest)

        return BacktestEngine(
            backtest=backtest,
            session_factory=session_factory,
            settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
            quote_provider=FakeHistoryProvider([]),
            rng=random.Random(7),
        )


def test_generate_schedule_uses_nyse_trading_days_for_each_frequency() -> None:
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        quote_provider=None,
        rng=random.Random(7),
    )

    assert engine._build_schedule(date(2024, 1, 2), date(2024, 1, 10), "DAILY") == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]
    assert engine._build_schedule(date(2024, 1, 2), date(2024, 1, 10), "WEEKLY") == [
        date(2024, 1, 5),
        date(2024, 1, 10),
    ]
    assert engine._build_schedule(date(2024, 1, 2), date(2024, 1, 31), "MONTHLY") == [
        date(2024, 1, 31),
    ]


def test_prior_report_window_matches_frequency_rules() -> None:
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        quote_provider=None,
        rng=random.Random(7),
    )

    assert engine._prior_report_limit("DAILY") == 1
    assert engine._prior_report_limit("WEEKLY") == 5
    assert engine._prior_report_limit("MONTHLY") is None


def test_load_prior_reports_excludes_prompt_reports_and_keeps_analysis_reports(
    session_factory: sessionmaker[Session],
) -> None:
    engine = build_engine(session_factory)

    with session_factory() as session:
        session.add_all(
            [
                Report(
                    name="backtest_42_prompt_20240614",
                    slug="backtest_42_prompt_20240614",
                    source="external",
                    content="prompt packet",
                    metadata_={
                        "tags": ["backtest", "backtest_42", "prompt"],
                        "analysis": {
                            "backtestId": engine.backtest.id,
                            "cycleDate": "2024-06-14",
                            "reviewType": "backtest_prompt",
                        },
                    },
                ),
                Report(
                    name="backtest_42_analysis_20240614",
                    slug="backtest_42_analysis_20240614",
                    source="external",
                    content="analysis packet",
                    metadata_={
                        "tags": ["backtest", f"backtest_{engine.backtest.id}"],
                        "analysis": {
                            "backtestId": engine.backtest.id,
                            "cycleDate": "2024-06-14",
                            "reviewType": "backtest_analysis",
                        },
                    },
                ),
            ]
        )
        session.commit()

        prior_reports = engine._load_prior_reports(session, date(2024, 6, 17))

    assert prior_reports == ["analysis packet"]


def test_market_data_cache_writes_and_reuses_parquet(tmp_path: Path) -> None:
    quote_provider = FakeHistoryProvider(
        history_rows=[
            {
                "date": "2024-01-02",
                "open": 183.0,
                "high": 186.0,
                "low": 182.5,
                "close": 185.2,
                "volume": 1000,
            },
            {
                "date": "2024-01-03",
                "open": 185.1,
                "high": 187.0,
                "low": 184.2,
                "close": 186.4,
                "volume": 1200,
            },
        ]
    )

    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir=str(tmp_path)),
        quote_provider=quote_provider,
        rng=random.Random(7),
    )

    first = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 1, 3))
    second = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 1, 3))

    assert (tmp_path / "AAPL.parquet").exists()
    assert second.equals(first)
    assert quote_provider.fetch_history_calls == 1


def test_market_data_cache_appends_only_missing_trailing_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pandas = importlib.import_module("pandas")
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir=str(tmp_path)),
        quote_provider=None,
        rng=random.Random(7),
    )

    calls: list[tuple[date, date]] = []

    def fake_download_history(symbol: str, start: date, end: date):
        calls.append((start, end))
        if (start, end) == (date(2024, 1, 2), date(2024, 1, 3)):
            index = pandas.to_datetime(["2024-01-02", "2024-01-03"])
            rows = [
                {"open": 183.0, "high": 186.0, "low": 182.5, "close": 185.2, "volume": 1000},
                {"open": 185.1, "high": 187.0, "low": 184.2, "close": 186.4, "volume": 1200},
            ]
        elif (start, end) == (date(2024, 1, 4), date(2024, 1, 5)):
            index = pandas.to_datetime(["2024-01-04", "2024-01-05"])
            rows = [
                {"open": 186.0, "high": 188.0, "low": 185.5, "close": 187.4, "volume": 1300},
                {"open": 187.3, "high": 189.0, "low": 186.8, "close": 188.1, "volume": 1400},
            ]
        else:
            raise AssertionError(f"Unexpected download window {(start, end)}")
        return pandas.DataFrame(rows, index=index)

    monkeypatch.setattr(engine, "_download_history", fake_download_history)

    first = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 1, 3))
    second = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 1, 5))

    assert len(first) == 2
    assert len(second) == 4
    assert calls == [
        (date(2024, 1, 2), date(2024, 1, 3)),
        (date(2024, 1, 4), date(2024, 1, 5)),
    ]


def test_market_data_cache_appends_history_with_duplicate_columns(tmp_path: Path) -> None:
    pandas = importlib.import_module("pandas")
    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir=str(tmp_path)),
        quote_provider=None,
        rng=random.Random(7),
    )

    cached = pandas.DataFrame(
        [
            {"open": 183.0, "high": 186.0, "low": 182.5, "close": 185.2, "volume": 1000},
            {"open": 185.1, "high": 187.0, "low": 184.2, "close": 186.4, "volume": 1200},
        ],
        index=pandas.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    cached.to_parquet(tmp_path / "AAPL.parquet")

    fetched = pandas.DataFrame(
        [
            [186.0, 188.0, 185.5, 187.4, 187.5, 1300],
            [187.3, 189.0, 186.8, 188.1, 188.2, 1400],
        ],
        index=pandas.to_datetime(["2024-01-04", "2024-01-05"]),
        columns=["open", "high", "low", "close", "close", "volume"],
    )

    engine._download_history = lambda symbol, start, end: fetched  # type: ignore[method-assign]

    frame = engine._load_symbol_history("AAPL", date(2024, 1, 2), date(2024, 1, 5))

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 4
    assert frame.loc[pandas.Timestamp("2024-01-05"), "close"] == 188.2


def test_download_history_flattens_yfinance_multiindex_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pandas = importlib.import_module("pandas")
    columns = pandas.MultiIndex.from_tuples(
        [
            ("Adj Close", "^GSPC"),
            ("Close", "^GSPC"),
            ("High", "^GSPC"),
            ("Low", "^GSPC"),
            ("Open", "^GSPC"),
            ("Volume", "^GSPC"),
        ],
        names=["Price", "Ticker"],
    )
    downloaded = pandas.DataFrame(
        [[4742.83, 4742.83, 4754.33, 4722.67, 4745.20, 3743050000]],
        index=pandas.to_datetime(["2024-01-02"]),
        columns=columns,
    )

    class FakeYFinance:
        @staticmethod
        def download(*args: object, **kwargs: object):
            _ = (args, kwargs)
            return downloaded

    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "yfinance":
            return FakeYFinance()
        return real_import_module(name)

    monkeypatch.setattr("app.services.backtest_engine.importlib.import_module", fake_import_module)

    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        quote_provider=None,
        rng=random.Random(7),
    )

    frame = engine._download_history("^GSPC", date(2024, 1, 2), date(2024, 1, 3))

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.iloc[0]["close"] == 4742.83


def test_load_symbol_history_normalizes_cached_multiindex_columns(tmp_path: Path) -> None:
    pandas = importlib.import_module("pandas")
    columns = pandas.MultiIndex.from_tuples(
        [
            ("open", "^GSPC"),
            ("high", "^GSPC"),
            ("low", "^GSPC"),
            ("close", "^GSPC"),
            ("volume", "^GSPC"),
        ]
    )
    cached = pandas.DataFrame(
        [[4745.20, 4754.33, 4722.67, 4742.83, 3743050000]],
        index=pandas.to_datetime(["2024-01-02"]),
        columns=columns,
    )
    cached.to_parquet(tmp_path / "^GSPC.parquet")

    engine = BacktestEngine(
        backtest=SimpleNamespace(frequency="DAILY"),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir=str(tmp_path)),
        quote_provider=FakeHistoryProvider([]),
        rng=random.Random(7),
    )

    frame = engine._load_symbol_history("^GSPC", date(2024, 1, 2), date(2024, 1, 2))

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.iloc[0]["close"] == 4742.83


def test_executed_trades_are_attributed_to_backtest_and_recent_activity_is_trimmed(
    session_factory: sessionmaker[Session],
) -> None:
    engine = build_engine(
        session_factory,
        backtest_id=42,
        portfolio_id=7,
        deposit_balance_id=3,
        recent_activity=[
            {
                "cycleDate": f"2024-06-{day:02d}",
                "decisions": [{"symbol": "AAPL", "action": "HOLD", "reasoning": "Still valid."}],
            }
            for day in range(1, 11)
        ],
    )

    trade_log = engine._apply_decisions(
        cycle_date=date(2024, 6, 15),
        decisions=[
            TradeDecision(
                symbol="AAPL",
                action="BUY",
                quantity=3,
                target_price=Decimal("184.4"),
                reasoning="Thesis improved.",
            )
        ],
        market_data={
            "AAPL": {
                "open": Decimal("183.50"),
                "high": Decimal("185.00"),
                "low": Decimal("183.25"),
                "close": Decimal("184.40"),
                "volume": Decimal("1000000"),
            }
        },
    )

    assert trade_log[0]["commission"] == "0.00"

    with session_factory() as session:
        operations = TradingOperationRepository(session).list_for_backtest(engine.backtest.id)
        assert operations[0].backtest_id == engine.backtest.id

    refreshed = engine._refresh_backtest()
    assert refreshed.recent_activity is not None
    assert len(refreshed.recent_activity) == 10
    assert refreshed.recent_activity[-1]["cycleDate"] == "2024-06-15"


def test_build_prompts_includes_ohlcv_history_and_benchmark_performance(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pandas = importlib.import_module("pandas")
    engine = build_engine(session_factory)

    with session_factory() as session:
        session.add(
            Position(
                portfolio_id=engine.backtest.portfolio_id,
                symbol="AAPL",
                name="Apple",
                quantity=Decimal("5"),
                average_cost=Decimal("180"),
                currency="USD",
                last_source="simulation",
            )
        )
        session.commit()

    history_frame = pandas.DataFrame(
        [
            {
                "open": 183.5,
                "high": 185.0,
                "low": 183.25,
                "close": 184.4,
                "volume": 1000000,
            },
            {
                "open": 184.4,
                "high": 186.0,
                "low": 184.0,
                "close": 185.1,
                "volume": 1200000,
            },
        ],
        index=pandas.to_datetime(["2024-06-14", "2024-06-17"]),
    )

    monkeypatch.setattr(
        engine,
        "_load_symbol_history",
        lambda symbol, start, end: history_frame,
    )

    _system_prompt, user_prompt = engine._build_prompts(date(2024, 6, 17))

    assert "Benchmark performance" in user_prompt
    assert "2024-06-14" in user_prompt
    assert "open=183.5" in user_prompt


def test_initialize_marks_backtest_running_and_sets_total_cycles(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = build_engine(session_factory)

    schedule = [date(2024, 6, 17), date(2024, 6, 18)]
    benchmark_history = {"^GSPC": [("2024-06-17", Decimal("5400.00"))]}

    monkeypatch.setattr(engine, "_build_schedule", lambda start, end, frequency: schedule)
    monkeypatch.setattr(
        engine, "_load_benchmark_history", lambda current_schedule: benchmark_history
    )

    returned_schedule, returned_benchmark_history = engine.initialize()

    assert returned_schedule == schedule
    assert returned_benchmark_history == benchmark_history

    refreshed = engine._refresh_backtest()
    assert refreshed.status == "RUNNING"
    assert refreshed.total_cycles == len(schedule)
    assert refreshed.error_message is None


def test_initialize_returns_empty_schedule_when_backtest_is_cancelled(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = build_engine(session_factory)

    with session_factory() as session:
        backtest = session.get(Backtest, engine.backtest.id)
        assert backtest is not None
        backtest.status = "CANCELLED"
        session.commit()

    monkeypatch.setattr(
        engine, "_build_schedule", lambda start, end, frequency: [date(2024, 6, 17)]
    )

    schedule, benchmark_history = engine.initialize()

    assert schedule == []
    assert benchmark_history == {}
    assert engine._refresh_backtest().status == "CANCELLED"


def test_execute_cycle_returns_market_data_and_prompt_report(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = build_engine(session_factory)
    market_data = {
        "AAPL": {
            "open": Decimal("183.50"),
            "high": Decimal("185.00"),
            "low": Decimal("183.25"),
            "close": Decimal("184.40"),
            "volume": Decimal("1000000"),
        }
    }

    with session_factory() as session:
        session.add(
            Position(
                portfolio_id=engine.backtest.portfolio_id,
                symbol="AAPL",
                name="Apple",
                quantity=Decimal("5"),
                average_cost=Decimal("180"),
                currency="USD",
                last_source="simulation",
            )
        )
        session.commit()

    monkeypatch.setattr(engine, "_load_cycle_market_data", lambda symbols, cycle_date: market_data)
    monkeypatch.setattr(
        engine, "_build_prompts", lambda cycle_date: ("system prompt", "user prompt")
    )

    cycle_ctx = engine.execute_cycle(date(2024, 6, 17))

    assert cycle_ctx["cancelled"] is False
    assert cycle_ctx["cycle_date"] == date(2024, 6, 17)
    assert cycle_ctx["market_data"] == market_data
    assert cycle_ctx["prompt_report_slug"] == "backtest_42_prompt_20240617"

    with session_factory() as session:
        report = session.scalar(
            select(Report).where(Report.slug == cycle_ctx["prompt_report_slug"])
        )
        assert report is not None
        assert report.content.startswith("# Cycle Prompt (2024-06-17)")
        assert "## System\nsystem prompt" in report.content


def test_execute_cycle_returns_cancelled_when_backtest_is_cancelled(
    session_factory: sessionmaker[Session],
) -> None:
    engine = build_engine(session_factory)

    with session_factory() as session:
        backtest = session.get(Backtest, engine.backtest.id)
        assert backtest is not None
        backtest.status = "CANCELLED"
        session.commit()

    assert engine.execute_cycle(date(2024, 6, 17)) == {"cancelled": True}


def test_record_cycle_equity_updates_progress_and_returns_portfolio_value(
    session_factory: sessionmaker[Session],
) -> None:
    engine = build_engine(session_factory)

    date_str, equity_value = engine.record_cycle_equity(date(2024, 6, 17), {})

    assert date_str == "2024-06-17"
    assert equity_value == Decimal("100000.00")

    refreshed = engine._refresh_backtest()
    assert refreshed.completed_cycles == 1
    assert refreshed.current_cycle_date == date(2024, 6, 17)


def test_finalize_persists_failed_trade_log_entries_in_results(
    session_factory: sessionmaker[Session],
) -> None:
    engine = build_engine(session_factory)

    results = engine.finalize(
        equity_points=[("2024-06-17", Decimal("100000.00"))],
        benchmark_history={},
        trade_log=[
            {
                "cycleDate": "2024-06-17",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": "2",
                "requestedPrice": None,
                "executedPrice": None,
                "executed": False,
                "failureReason": "No market data for symbol",
                "reportSlug": None,
            }
        ],
        schedule=[date(2024, 6, 17)],
    )

    assert results["trades"][0]["executed"] is False
    assert results["trades"][0]["failureReason"] == "No market data for symbol"

    refreshed = engine._refresh_backtest()
    assert refreshed.status == "COMPLETED"
    assert refreshed.current_cycle_date == date(2024, 6, 17)
    assert refreshed.results is not None
    assert refreshed.results["trades"][0]["failureReason"] == "No market data for symbol"


def test_compute_results_returns_spec_metrics_payload() -> None:
    engine = BacktestEngine(
        backtest=SimpleNamespace(),
        session_factory=None,
        settings=SimpleNamespace(market_data_cache_dir="backend/.cache/market_data"),
        quote_provider=None,
        rng=random.Random(7),
    )

    results = engine._compute_results(
        equity_points=[
            ("2024-01-02", Decimal("100000")),
            ("2024-06-28", Decimal("112250")),
            ("2024-12-31", Decimal("118450")),
        ],
        benchmark_history={
            "^GSPC": [
                ("2024-01-02", Decimal("4769.83")),
                ("2024-12-31", Decimal("5881.63")),
            ]
        },
        trade_log=[
            {
                "cycleDate": "2024-01-15",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": "5",
                "requestedPrice": "185.50",
                "executedPrice": "184.40",
                "executed": True,
                "reportSlug": "backtest_42_20240115",
                "commission": "2.50",
            },
            {
                "cycleDate": "2024-02-15",
                "symbol": "AAPL",
                "side": "SELL",
                "quantity": "5",
                "requestedPrice": "190.50",
                "executedPrice": "191.00",
                "executed": True,
                "reportSlug": "backtest_42_20240215",
                "commission": "1.25",
                "profit": "28.75",
            },
        ],
    )

    assert results["portfolio"]["totalReturn"] == "0.1845"
    assert results["portfolio"]["sharpeRatio"] is not None
    assert results["portfolio"]["totalCommission"] == "3.75"
    assert results["portfolio"]["winRate"] == "1.0000"
    assert results["drawdownCurve"][0]["value"] == "0.0000"
