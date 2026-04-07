from __future__ import annotations

import json
import socket
import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.backtest_engine import BacktestEngine
from app.services.report_service import ReportService
from app.worker.main import create_app as create_worker_app
from app.worker.main import get_worker_service
from app.worker.schemas import BacktestWebhookDispatch
from app.worker.service import BacktestWebhookWorkerService
from app.worker.trading_agents_adapter import TradingAgentsAnalysis
from tests.test_backtest_engine import build_engine


def create_backtest_for_worker_integration(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        portfolio = Portfolio(
            name="Worker Integration Portfolio",
            slug="worker_integration_portfolio",
            base_currency="USD",
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
        template = TextTemplate(name="Worker Integration Template", content="# Worker Integration")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Worker Integration Backtest",
            status="RUNNING",
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=1,
            completed_cycles=0,
            template_id=template.id,
            webhook_url="http://worker.test/api/v1/trading-agents/dispatch",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
            current_cycle_date=None,
            current_cycle_status=None,
        )
        session.add(backtest)
        session.commit()
        return backtest.id


def allocate_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_dispatch_cycle_posts_to_worker_and_processes_real_callback_routes(
    session_factory: sessionmaker[Session],
    app: FastAPI,
    monkeypatch: Any,
) -> None:
    cycle_date = date(2024, 6, 17)
    backtest_id = create_backtest_for_worker_integration(session_factory)

    with session_factory() as session:
        ReportService(session).create_external_report(
            name="prompt_report",
            slug="prompt_report",
            content=(
                "# Cycle Prompt (2024-06-17)\n\n"
                "## System\n"
                "Today is 2024-06-17.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Balances:\n"
                "- Cash: 10000.00 USD (DEPOSIT)\n"
                "Positions:\n"
                "- AAPL: 5 shares @ 180.00 USD\n"
                "- MSFT: 2 shares @ 410.00 USD\n\n"
                "Market data (last 30 trading days OHLCV):\n"
                "AAPL:\n"
                "- 2024-06-17: open=182 high=184 low=181 close=183 volume=1000000\n"
                "MSFT:\n"
                "- 2024-06-17: open=412 high=414 low=409 close=410 volume=900000\n\n"
                "Benchmark performance since start date:\n"
                "- ^GSPC: start=5200 end=5250 total_return=0.0096\n\n"
                "Prior reports:\n"
                "- None"
            ),
        )

    cycle_service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)
    cycle_service._store_run_state(backtest_id, [cycle_date], {})

    class FakeEngine:
        def __init__(self) -> None:
            self.apply_calls: list[dict[str, Any]] = []
            self.finalized = False

        def execute_cycle(self, requested_cycle_date: date) -> dict[str, Any]:
            return {
                "cancelled": False,
                "prompt_report_slug": "prompt_report",
                "market_data": {},
                "cycle_date": requested_cycle_date,
            }

        def _portfolio_symbols(self) -> list[str]:
            return ["AAPL", "MSFT"]

        def _load_cycle_market_data(
            self, symbols: list[str], requested_cycle_date: date
        ) -> dict[str, dict[str, Decimal]]:
            _ = (symbols, requested_cycle_date)
            return {}

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
            return [
                {
                    "symbol": decision.symbol,
                    "side": decision.action,
                    "executed": True,
                    "executedPrice": None,
                    "failureReason": None,
                }
                for decision in decisions
            ]

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            _ = market_data
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            _ = (equity_points, benchmark_history, trade_log, schedule)
            with session_factory() as session:
                backtest = session.get(Backtest, backtest_id)
                assert backtest is not None
                backtest.status = "COMPLETED"
                backtest.results = {"worker": "done"}
                session.commit()
            self.finalized = True

        def _mark_failed(self, message: str) -> None:
            raise AssertionError(message)

    fake_engine = FakeEngine()
    monkeypatch.setattr(
        BacktestCycleService,
        "_build_engine",
        lambda self, requested_backtest_id: cast(BacktestEngine, fake_engine),
    )
    monkeypatch.setattr(
        "app.services.backtest_cycle_service.get_settings",
        lambda: SimpleNamespace(backtest_test_mode=False, public_base_url="http://ledger.test"),
    )

    with TestClient(app) as ledger_client:

        class FakeAdapter:
            def analyze_symbol(
                self,
                *,
                symbol: str,
                cycle_date: date,
                prompt_report: str,
                position_quantity: str,
            ) -> TradingAgentsAnalysis:
                _ = (cycle_date, prompt_report, position_quantity)
                return TradingAgentsAnalysis(
                    label="BUY" if symbol == "AAPL" else "UNDERWEIGHT",
                    summary="Momentum is improving." if symbol == "AAPL" else "Risk is elevated.",
                )

        def ledger_handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8")) if request.content else None
            if request.method == "GET":
                response = ledger_client.get(request.url.path)
            elif payload is not None:
                response = ledger_client.post(request.url.path, json=cast(dict[str, Any], payload))
            else:
                response = ledger_client.post(request.url.path)

            return httpx.Response(
                response.status_code,
                content=response.content,
                headers={"content-type": response.headers.get("content-type", "application/json")},
            )

        worker_service = BacktestWebhookWorkerService(
            http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(ledger_handler)),
            adapter_factory=FakeAdapter,
        )

        worker_app = create_worker_app()
        worker_app.dependency_overrides[get_worker_service] = lambda: worker_service

        with TestClient(worker_app) as worker_client:

            def fake_post(url: str, json: dict[str, Any], timeout: float):
                _ = (url, timeout)
                response = worker_client.post("/api/v1/trading-agents/dispatch", json=json)
                return SimpleNamespace(raise_for_status=response.raise_for_status)

            monkeypatch.setattr("app.services.backtest_cycle_service.httpx.post", fake_post)
            cycle_service._dispatch_cycle(backtest_id=backtest_id, cycle_date=cycle_date)
            deadline = time.monotonic() + 2
            while not fake_engine.finalized and time.monotonic() < deadline:
                time.sleep(0.01)

    assert fake_engine.finalized is True
    assert len(fake_engine.apply_calls) == 1
    decisions = fake_engine.apply_calls[0]["decisions"]
    assert [(decision.symbol, decision.action, decision.quantity) for decision in decisions] == [
        ("AAPL", "BUY", 1),
        ("MSFT", "SELL", 2),
    ]
    assert fake_engine.apply_calls[0]["report_slug"] == (
        f"tradingagents_backtest_{backtest_id}_20240617"
    )

    with session_factory() as session:
        refreshed = session.get(Backtest, backtest_id)
        assert refreshed is not None
        assert refreshed.status == "COMPLETED"
        assert refreshed.current_cycle_status is None


def test_dispatch_cycle_posts_to_real_http_worker_server(
    session_factory: sessionmaker[Session],
    app: FastAPI,
    monkeypatch: Any,
) -> None:
    cycle_date = date(2024, 6, 17)
    backtest_id = create_backtest_for_worker_integration(session_factory)
    worker_port = allocate_local_port()

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.webhook_url = f"http://127.0.0.1:{worker_port}/api/v1/trading-agents/dispatch"
        ReportService(session).create_external_report(
            name="prompt_report_http",
            slug="prompt_report_http",
            content=(
                "# Cycle Prompt (2024-06-17)\n\n"
                "## System\n"
                "Today is 2024-06-17.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Balances:\n"
                "- Cash: 10000.00 USD (DEPOSIT)\n"
                "Positions:\n"
                "- AAPL: 5 shares @ 180.00 USD\n\n"
                "Market data (last 30 trading days OHLCV):\n"
                "AAPL:\n"
                "- 2024-06-17: open=182 high=184 low=181 close=183 volume=1000000\n\n"
                "Benchmark performance since start date:\n"
                "- ^GSPC: start=5200 end=5250 total_return=0.0096\n\n"
                "Prior reports:\n"
                "- None"
            ),
        )
        session.commit()

    cycle_service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)
    cycle_service._store_run_state(backtest_id, [cycle_date], {})

    class FakeEngine:
        def __init__(self) -> None:
            self.finalized = False
            self.apply_calls: list[dict[str, Any]] = []

        def execute_cycle(self, requested_cycle_date: date) -> dict[str, Any]:
            return {
                "cancelled": False,
                "prompt_report_slug": "prompt_report_http",
                "market_data": {},
                "cycle_date": requested_cycle_date,
            }

        def _portfolio_symbols(self) -> list[str]:
            return ["AAPL"]

        def _load_cycle_market_data(
            self, symbols: list[str], requested_cycle_date: date
        ) -> dict[str, dict[str, Decimal]]:
            _ = (symbols, requested_cycle_date)
            return {}

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
            return [
                {
                    "symbol": decision.symbol,
                    "side": decision.action,
                    "executed": True,
                    "executedPrice": None,
                    "failureReason": None,
                }
                for decision in decisions
            ]

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            _ = market_data
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            _ = (equity_points, benchmark_history, trade_log, schedule)
            with session_factory() as session:
                backtest = session.get(Backtest, backtest_id)
                assert backtest is not None
                backtest.status = "COMPLETED"
                session.commit()
            self.finalized = True

        def _mark_failed(self, message: str) -> None:
            raise AssertionError(message)

    fake_engine = FakeEngine()
    monkeypatch.setattr(
        BacktestCycleService,
        "_build_engine",
        lambda self, requested_backtest_id: cast(BacktestEngine, fake_engine),
    )
    monkeypatch.setattr(
        "app.services.backtest_cycle_service.get_settings",
        lambda: SimpleNamespace(backtest_test_mode=False, public_base_url="http://ledger.test"),
    )

    with TestClient(app) as ledger_client:

        class FakeAdapter:
            def analyze_symbol(
                self,
                *,
                symbol: str,
                cycle_date: date,
                prompt_report: str,
                position_quantity: str,
            ) -> TradingAgentsAnalysis:
                _ = (cycle_date, prompt_report, position_quantity)
                return TradingAgentsAnalysis(label="BUY", summary=f"Add {symbol}.")

        def ledger_handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8")) if request.content else None
            if request.method == "GET":
                response = ledger_client.get(request.url.path)
            elif payload is not None:
                response = ledger_client.post(request.url.path, json=cast(dict[str, Any], payload))
            else:
                response = ledger_client.post(request.url.path)

            return httpx.Response(
                response.status_code,
                content=response.content,
                headers={"content-type": response.headers.get("content-type", "application/json")},
            )

        worker_service = BacktestWebhookWorkerService(
            http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(ledger_handler)),
            adapter_factory=FakeAdapter,
        )
        worker_app = create_worker_app()
        worker_app.dependency_overrides[get_worker_service] = lambda: worker_service

        config = uvicorn.Config(worker_app, host="127.0.0.1", port=worker_port, log_level="error")
        server = uvicorn.Server(config)
        server_thread = __import__("threading").Thread(target=server.run, daemon=True)
        server_thread.start()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with httpx.Client(timeout=1.0) as client:
                    if client.get(f"http://127.0.0.1:{worker_port}/health").status_code == 200:
                        break
            except Exception:
                time.sleep(0.05)
        else:
            raise AssertionError("worker server did not become ready")

        try:
            cycle_service._dispatch_cycle(backtest_id=backtest_id, cycle_date=cycle_date)
            done_deadline = time.monotonic() + 5
            while not fake_engine.finalized and time.monotonic() < done_deadline:
                time.sleep(0.01)
        finally:
            server.should_exit = True
            server_thread.join(timeout=5)

    assert fake_engine.finalized is True
    assert len(fake_engine.apply_calls) == 1
    decisions = fake_engine.apply_calls[0]["decisions"]
    assert [(decision.symbol, decision.action, decision.quantity) for decision in decisions] == [
        ("AAPL", "BUY", 1)
    ]


def test_processing_callback_timeout_marks_backtest_failed(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 17)
    backtest_id = create_backtest_for_worker_integration(session_factory)

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.current_cycle_date = cycle_date
        backtest.current_cycle_status = "PROCESSING_CALLBACK"
        backtest.status = "RUNNING"
        session.commit()

    service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)
    service._handle_timeout(backtest_id, cycle_date)

    with session_factory() as session:
        refreshed = session.get(Backtest, backtest_id)
        assert refreshed is not None
        assert refreshed.status == "FAILED"
        assert refreshed.current_cycle_status is None
        assert refreshed.error_message == "Webhook callback timed out after 600s"


def test_dispatch_cycle_requires_public_base_url_for_external_worker(
    session_factory: sessionmaker[Session],
    monkeypatch: Any,
) -> None:
    cycle_date = date(2024, 6, 17)
    backtest_id = create_backtest_for_worker_integration(session_factory)
    cycle_service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)

    class FakeEngine:
        def __init__(self) -> None:
            self.failed_message: str | None = None

        def execute_cycle(self, requested_cycle_date: date) -> dict[str, Any]:
            return {
                "cancelled": False,
                "prompt_report_slug": "prompt_report",
                "market_data": {},
                "cycle_date": requested_cycle_date,
            }

        def _mark_failed(self, message: str) -> None:
            self.failed_message = message

    fake_engine = FakeEngine()
    posted = {"called": False}

    monkeypatch.setattr(
        BacktestCycleService,
        "_build_engine",
        lambda self, requested_backtest_id: cast(BacktestEngine, fake_engine),
    )
    monkeypatch.setattr(
        "app.services.backtest_cycle_service.get_settings",
        lambda: SimpleNamespace(backtest_test_mode=False, public_base_url=None),
    )

    def fake_post(url: str, json: dict[str, Any], timeout: float):
        _ = (url, json, timeout)
        posted["called"] = True
        raise AssertionError("dispatch should not post without PUBLIC_BASE_URL")

    monkeypatch.setattr("app.services.backtest_cycle_service.httpx.post", fake_post)
    cycle_service._dispatch_cycle(backtest_id=backtest_id, cycle_date=cycle_date)

    assert fake_engine.failed_message == (
        "PUBLIC_BASE_URL is required for webhook backtests so external workers can reach "
        "report and callback URLs"
    )
    assert posted["called"] is False


def test_worker_service_parses_real_backtest_engine_prompt_report(
    session_factory: sessionmaker[Session],
    monkeypatch: Any,
) -> None:
    pandas = __import__("importlib").import_module("pandas")
    engine = build_engine(session_factory)

    with session_factory() as session:
        session.add_all(
            [
                Position(
                    portfolio_id=engine.backtest.portfolio_id,
                    symbol="AAPL",
                    name="Apple",
                    quantity=Decimal("5"),
                    average_cost=Decimal("180"),
                    currency="USD",
                    last_source="simulation",
                ),
                Position(
                    portfolio_id=engine.backtest.portfolio_id,
                    symbol="MSFT",
                    name="Microsoft",
                    quantity=Decimal("2"),
                    average_cost=Decimal("410"),
                    currency="USD",
                    last_source="simulation",
                ),
            ]
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
                "open": 412.0,
                "high": 414.0,
                "low": 409.0,
                "close": 410.0,
                "volume": 900000,
            },
        ],
        index=pandas.to_datetime(["2024-06-14", "2024-06-17"]),
    )
    monkeypatch.setattr(engine, "_load_symbol_history", lambda symbol, start, end: history_frame)

    cycle_ctx = engine.execute_cycle(date(2024, 6, 17))
    with session_factory() as session:
        prompt_report = session.execute(
            select(Report.content).where(Report.slug == cycle_ctx["prompt_report_slug"])
        ).scalar_one()

    captured_requests: list[dict[str, Any]] = []
    adapter_calls: list[tuple[str, str]] = []

    class FakeAdapter:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> TradingAgentsAnalysis:
            _ = (cycle_date, prompt_report)
            adapter_calls.append((symbol, position_quantity))
            return TradingAgentsAnalysis(label="HOLD", summary=f"Keep {symbol} unchanged.")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8")) if request.content else None
        captured_requests.append(
            {"method": request.method, "url": str(request.url), "json": payload}
        )
        if request.method == "GET":
            return httpx.Response(200, text=prompt_report)
        if str(request.url).endswith("/report"):
            return httpx.Response(201, json={"slug": "analysis_report_slug"})
        if str(request.url).endswith("/trades"):
            return httpx.Response(200, json={"executed": []})
        if str(request.url).endswith("/complete"):
            return httpx.Response(
                200,
                json={
                    "backtestId": engine.backtest.id,
                    "status": "RUNNING",
                    "completedCycles": 1,
                    "totalCycles": 1,
                    "nextCycleDate": None,
                    "finished": True,
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    worker_service = BacktestWebhookWorkerService(
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
        adapter_factory=FakeAdapter,
    )

    result = worker_service.handle_dispatch(
        BacktestWebhookDispatch.model_validate(
            {
                "backtestId": engine.backtest.id,
                "cycleDate": "2024-06-17",
                "totalCycles": 1,
                "completedCycles": 0,
                "frequency": "DAILY",
                "reportSlug": cycle_ctx["prompt_report_slug"],
                "reportDownloadUrl": "http://ledger.test/api/v1/reports/prompt_report/download",
                "callbackBaseUrl": "http://ledger.test/api/v1/backtests/42/cycles/2024-06-17",
                "benchmarkSymbols": ["^GSPC"],
            }
        )
    )

    assert result.model_dump(by_alias=True) == {
        "status": "completed",
        "reportSlug": "analysis_report_slug",
        "decisionCount": 2,
        "symbols": ["AAPL", "MSFT"],
    }
    assert adapter_calls == [("AAPL", "5"), ("MSFT", "2")]
    assert captured_requests[2]["json"] == {
        "decisions": [
            {
                "symbol": "AAPL",
                "action": "HOLD",
                "quantity": None,
                "targetPrice": None,
                "reasoning": "HOLD: Keep AAPL unchanged.",
            },
            {
                "symbol": "MSFT",
                "action": "HOLD",
                "quantity": None,
                "targetPrice": None,
                "reasoning": "HOLD: Keep MSFT unchanged.",
            },
        ],
        "reportSlug": "analysis_report_slug",
    }
