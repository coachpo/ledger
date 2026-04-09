from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate
from app.schemas.backtest import BacktestStatus
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.backtest_engine import BacktestEngine


def build_service() -> BacktestCycleService:
    return BacktestCycleService(
        cast(Session, SimpleNamespace()),
        cast(sessionmaker[Session], SimpleNamespace()),
    )


def create_backtest(
    session_factory: sessionmaker[Session],
    *,
    current_cycle_date: date | None,
    current_cycle_status: str | None,
) -> int:
    with session_factory() as session:
        portfolio = Portfolio(
            name="Timeout Portfolio", slug="timeout_portfolio", base_currency="USD"
        )
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Cash",
            operation_type="DEPOSIT",
            amount=Decimal("1000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Timeout Template", content="# Timeout")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Timeout Backtest",
            status=BacktestStatus.RUNNING.value,
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=21,
            completed_cycles=0,
            template_id=template.id,
            webhook_url="http://localhost:5678/webhook/test",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
            current_cycle_date=current_cycle_date,
            current_cycle_status=current_cycle_status,
        )
        session.add(backtest)
        session.commit()
        return backtest.id


class FakeEngine:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.apply_calls: list[dict[str, Any]] = []
        self.record_calls: list[tuple[date, dict[str, dict[str, Decimal]]]] = []
        self.finalize_calls: list[dict[str, Any]] = []

    def _portfolio_symbols(self) -> list[str]:
        return self.symbols

    def apply_cycle_trades(
        self,
        *,
        cycle_date: date,
        decisions: list[Any],
        market_data: dict[str, dict[str, Decimal]],
        report_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        call = {
            "cycle_date": cycle_date,
            "decisions": decisions,
            "market_data": market_data,
            "report_slug": report_slug,
        }
        self.apply_calls.append(call)
        return [
            {
                "symbol": decision.symbol,
                "side": decision.action,
                "executed": None,
                "reportSlug": report_slug,
            }
            for decision in decisions
        ]

    def record_cycle_equity(
        self, cycle_date: date, market_data: dict[str, dict[str, Decimal]]
    ) -> tuple[str, Decimal]:
        self.record_calls.append((cycle_date, market_data))
        return cycle_date.isoformat(), Decimal("100000.00")

    def finalize(
        self,
        *,
        equity_points: list[tuple[str, Decimal]],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
        trade_log: list[dict[str, Any]],
        schedule: list[date],
    ) -> None:
        self.finalize_calls.append(
            {
                "equity_points": equity_points,
                "benchmark_history": benchmark_history,
                "trade_log": trade_log,
                "schedule": schedule,
            }
        )


@pytest.mark.parametrize(
    ("status"),
    [
        BacktestStatus.FAILED.value,
        BacktestStatus.CANCELLED.value,
        BacktestStatus.COMPLETED.value,
    ],
)
def test_validate_cycle_status_rejects_terminal_backtests(status: str) -> None:
    service = build_service()
    backtest = SimpleNamespace(
        status=status, current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value
    )

    with pytest.raises(ApiError, match=f"Backtest is {status}, cannot process callbacks") as exc:
        service._validate_cycle_status(
            cast(Backtest, backtest),
            date(2024, 6, 17),
            allow=[BacktestStatus.AWAITING_CALLBACK.value],
        )

    assert exc.value.code == "invalid_backtest_state"


def test_validate_cycle_status_rejects_unexpected_cycle_status() -> None:
    service = build_service()
    backtest = SimpleNamespace(
        status=BacktestStatus.RUNNING.value,
        current_cycle_status=None,
        current_cycle_date=None,
    )

    with pytest.raises(ApiError, match="expected one of") as exc:
        service._validate_cycle_status(
            cast(Backtest, backtest),
            date(2024, 6, 17),
            allow=[BacktestStatus.AWAITING_CALLBACK.value],
        )

    assert exc.value.code == "invalid_backtest_cycle_status"


def test_deterministic_cycle_buys_starter_position_for_empty_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    engine = FakeEngine([])
    cycle_date = date(2024, 6, 17)
    market_data = {
        "AAPL": {
            "open": Decimal("183.50"),
            "high": Decimal("185.00"),
            "low": Decimal("183.25"),
            "close": Decimal("184.40"),
            "volume": Decimal("1000000"),
        }
    }

    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._deterministic_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx={"market_data": market_data, "prompt_report_slug": "prompt-42"},
    )

    decision = engine.apply_calls[0]["decisions"][0]
    assert decision.symbol == "AAPL"
    assert decision.action == "BUY"
    assert decision.quantity == 2
    assert decision.reasoning == "Deterministic starter position"
    assert engine.record_calls == [(cycle_date, market_data)]
    assert len(engine.finalize_calls) == 1


def test_deterministic_cycle_holds_existing_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service()
    engine = FakeEngine(["AAPL", "MSFT"])
    cycle_date = date(2024, 6, 17)
    market_data = {
        "AAPL": {"close": Decimal("184.40")},
        "MSFT": {"close": Decimal("430.10")},
    }

    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._deterministic_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx={"market_data": market_data, "prompt_report_slug": "prompt-42"},
    )

    decisions = engine.apply_calls[0]["decisions"]
    assert [(decision.symbol, decision.action, decision.quantity) for decision in decisions] == [
        ("AAPL", "HOLD", None),
        ("MSFT", "HOLD", None),
    ]
    assert [decision.reasoning for decision in decisions] == [
        "Deterministic hold",
        "Deterministic hold",
    ]
    assert engine.record_calls == [(cycle_date, market_data)]
    assert len(engine.finalize_calls) == 1


def test_dispatch_cycle_runs_internal_langgraph_analysis_without_webhook_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    captured: dict[str, Any] = {}

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(
                report_content="# LangGraph Analysis",
                decisions=[],
            )

    class FakeEngine:
        def __init__(self) -> None:
            self.apply_calls: list[dict[str, Any]] = []
            self.record_calls: list[tuple[date, dict[str, dict[str, Decimal]]]] = []
            self.finalize_calls: list[dict[str, Any]] = []

        def execute_cycle(self, requested_cycle_date: date) -> dict[str, Any]:
            return {
                "cancelled": False,
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "market_data": {},
                "cycle_date": requested_cycle_date,
            }

        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            captured["stored_report"] = {
                "cycle_date": requested_cycle_date,
                "analysis": analysis,
            }
            return "langgraph_backtest_42_20240617"

        def apply_cycle_trades(
            self,
            *,
            cycle_date: date,
            decisions: list[Any],
            market_data: dict[str, dict[str, Decimal]],
            report_slug: str | None = None,
        ) -> list[dict[str, Any]]:
            self.apply_calls.append(
                {
                    "cycle_date": cycle_date,
                    "decisions": decisions,
                    "market_data": market_data,
                    "report_slug": report_slug,
                }
            )
            return []

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            self.record_calls.append((requested_cycle_date, market_data))
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            self.finalize_calls.append(
                {
                    "equity_points": equity_points,
                    "benchmark_history": benchmark_history,
                    "trade_log": trade_log,
                    "schedule": schedule,
                }
            )

        def _mark_failed(self, message: str) -> None:
            raise AssertionError(message)

    engine = FakeEngine()

    monkeypatch.setattr(
        service,
        "_build_engine",
        lambda backtest_id: cast(BacktestEngine, engine),
    )
    monkeypatch.setattr(service, "_build_langgraph_runner", lambda: FakeRunner())
    monkeypatch.setattr(
        service,
        "_load_prompt_report",
        lambda prompt_report_slug: f"prompt content for {prompt_report_slug}",
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    monkeypatch.setattr(
        service,
        "_resolve_public_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy webhook URL resolution should not be used")
        ),
    )

    service._dispatch_cycle(backtest_id=42, cycle_date=cycle_date)

    assert captured["request"].prompt_report_slug == "backtest_42_prompt_20240617"
    assert captured["request"].prompt_report == "prompt content for backtest_42_prompt_20240617"
    assert captured["stored_report"] == {
        "cycle_date": cycle_date,
        "analysis": "# LangGraph Analysis",
    }
    assert engine.apply_calls == [
        {
            "cycle_date": cycle_date,
            "decisions": [],
            "market_data": {},
            "report_slug": "langgraph_backtest_42_20240617",
        }
    ]
    assert engine.record_calls == [(cycle_date, {})]
    assert len(engine.finalize_calls) == 1


def test_handle_timeout_ignores_stale_timer_for_previous_cycle(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = create_backtest(
        session_factory,
        current_cycle_date=date(2024, 6, 18),
        current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value,
    )
    service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)

    service._handle_timeout(backtest_id, date(2024, 6, 17))

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == BacktestStatus.RUNNING.value
        assert backtest.current_cycle_status == BacktestStatus.AWAITING_CALLBACK.value
        assert backtest.current_cycle_date == date(2024, 6, 18)


def test_handle_timeout_fails_active_cycle_only(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = create_backtest(
        session_factory,
        current_cycle_date=date(2024, 6, 17),
        current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value,
    )
    service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)

    service._handle_timeout(backtest_id, date(2024, 6, 17))

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == BacktestStatus.FAILED.value
        assert backtest.current_cycle_status is None
        assert backtest.error_message == "Webhook callback timed out after 600s"
