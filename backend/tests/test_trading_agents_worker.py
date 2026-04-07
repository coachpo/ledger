from __future__ import annotations

import importlib
import json
import threading
import time
from datetime import date
from typing import Any

import httpx
from fastapi.testclient import TestClient


def load_worker_components() -> tuple[Any, Any, Any]:
    try:
        module = importlib.import_module("app.worker.main")
    except ModuleNotFoundError as exc:
        raise AssertionError(f"TradingAgents worker app is missing: {exc}") from exc

    return module.create_app, module.get_worker_service, module.BacktestWebhookWorkerService


class FakeTradingAgentsAdapter:
    def __init__(self, responses: dict[str, tuple[str, str]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def analyze_symbol(
        self,
        *,
        symbol: str,
        cycle_date: date,
        prompt_report: str,
        position_quantity: str,
    ) -> Any:
        self.calls.append(
            {
                "symbol": symbol,
                "cycle_date": cycle_date,
                "prompt_report": prompt_report,
                "position_quantity": position_quantity,
            }
        )
        label, summary = self.responses[symbol]
        return {"label": label, "summary": summary}


def build_worker_service(
    *,
    prompt_report: str,
    adapter: FakeTradingAgentsAdapter,
    captured_requests: list[dict[str, Any]],
) -> Any:
    _, _, service_cls = load_worker_components()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = None
        if request.content:
            payload = json.loads(request.content.decode("utf-8"))
        captured_requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "json": payload,
            }
        )

        if request.method == "GET" and str(request.url) == (
            "http://ledger.test/api/v1/reports/prompt_report/download"
        ):
            return httpx.Response(200, text=prompt_report)

        if request.method == "POST" and str(request.url).endswith("/report"):
            return httpx.Response(201, json={"slug": "analysis_report_slug"})

        if request.method == "POST" and str(request.url).endswith("/trades"):
            return httpx.Response(200, json={"executed": []})

        if request.method == "POST" and str(request.url).endswith("/complete"):
            return httpx.Response(
                200,
                json={
                    "backtestId": 42,
                    "status": "RUNNING",
                    "completedCycles": 3,
                    "totalCycles": 10,
                    "nextCycleDate": "2024-06-24",
                    "finished": False,
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    return service_cls(
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
        adapter_factory=lambda: adapter,
    )


def build_dispatch_payload() -> dict[str, Any]:
    return {
        "backtestId": 42,
        "cycleDate": "2024-06-17",
        "totalCycles": 10,
        "completedCycles": 2,
        "frequency": "DAILY",
        "reportSlug": "prompt_report",
        "reportDownloadUrl": "http://ledger.test/api/v1/reports/prompt_report/download",
        "callbackBaseUrl": "http://ledger.test/api/v1/backtests/42/cycles/2024-06-17",
        "benchmarkSymbols": ["^GSPC"],
    }


def wait_for_request_count(captured_requests: list[dict[str, Any]], expected_count: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if len(captured_requests) >= expected_count:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"Timed out waiting for {expected_count} captured requests; got {len(captured_requests)}"
    )


def test_worker_service_dispatch_uploads_analysis_sends_trades_and_completes_cycle() -> None:
    from app.worker.schemas import BacktestWebhookDispatch

    _, _, _ = load_worker_components()
    captured_requests: list[dict[str, Any]] = []
    adapter = FakeTradingAgentsAdapter(
        {
            "AAPL": ("BUY", "Momentum is improving."),
            "MSFT": ("UNDERWEIGHT", "Risk is elevated."),
        }
    )
    service = build_worker_service(
        prompt_report=(
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
        adapter=adapter,
        captured_requests=captured_requests,
    )

    response = service.handle_dispatch(
        BacktestWebhookDispatch.model_validate(build_dispatch_payload())
    )

    assert response.model_dump(by_alias=True) == {
        "status": "completed",
        "reportSlug": "analysis_report_slug",
        "decisionCount": 2,
        "symbols": ["AAPL", "MSFT"],
    }
    assert [(call["symbol"], call["position_quantity"]) for call in adapter.calls] == [
        ("AAPL", "5"),
        ("MSFT", "2"),
    ]

    assert [(request["method"], request["url"]) for request in captured_requests] == [
        ("GET", "http://ledger.test/api/v1/reports/prompt_report/download"),
        ("POST", "http://ledger.test/api/v1/backtests/42/cycles/2024-06-17/report"),
        ("POST", "http://ledger.test/api/v1/backtests/42/cycles/2024-06-17/trades"),
        ("POST", "http://ledger.test/api/v1/backtests/42/cycles/2024-06-17/complete"),
    ]

    assert captured_requests[1]["json"] == {
        "name": "tradingagents_backtest_42_20240617",
        "content": (
            "# TradingAgents Analysis\n\n"
            "- Backtest ID: 42\n"
            "- Cycle date: 2024-06-17\n"
            "- Prompt report slug: prompt_report\n\n"
            "## AAPL\n"
            "- Label: BUY\n"
            "- Held quantity: 5\n"
            "- Summary: Momentum is improving.\n\n"
            "## MSFT\n"
            "- Label: UNDERWEIGHT\n"
            "- Held quantity: 2\n"
            "- Summary: Risk is elevated."
        ),
        "tags": ["tradingagents", "phase1"],
    }
    assert captured_requests[2]["json"] == {
        "decisions": [
            {
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 1,
                "targetPrice": None,
                "reasoning": "BUY: Momentum is improving.",
            },
            {
                "symbol": "MSFT",
                "action": "SELL",
                "quantity": 2,
                "targetPrice": None,
                "reasoning": "UNDERWEIGHT: Risk is elevated.",
            },
        ],
        "reportSlug": "analysis_report_slug",
    }
    assert captured_requests[3]["json"] is None


def test_worker_route_accepts_dispatch_and_processes_callbacks_in_background() -> None:
    create_app, get_worker_service, _ = load_worker_components()
    captured_requests: list[dict[str, Any]] = []
    adapter_started = threading.Event()
    allow_adapter_finish = threading.Event()

    class SlowTradingAgentsAdapter(FakeTradingAgentsAdapter):
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> Any:
            adapter_started.set()
            allow_adapter_finish.wait(timeout=1.5)
            return super().analyze_symbol(
                symbol=symbol,
                cycle_date=cycle_date,
                prompt_report=prompt_report,
                position_quantity=position_quantity,
            )

    adapter = SlowTradingAgentsAdapter(
        {
            "AAPL": ("BUY", "Momentum is improving."),
            "MSFT": ("UNDERWEIGHT", "Risk is elevated."),
        }
    )
    service = build_worker_service(
        prompt_report=(
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
        adapter=adapter,
        captured_requests=captured_requests,
    )

    app = create_app()
    app.dependency_overrides[get_worker_service] = lambda: service

    with TestClient(app) as client:
        started_at = time.monotonic()
        response = client.post(
            "/api/v1/trading-agents/dispatch",
            json=build_dispatch_payload(),
        )
        elapsed = time.monotonic() - started_at

        assert response.status_code == 202
        assert response.json() == {
            "status": "accepted",
            "backtestId": 42,
            "cycleDate": "2024-06-17",
        }
        assert elapsed < 0.5
        assert adapter_started.wait(timeout=1)

        allow_adapter_finish.set()
        wait_for_request_count(captured_requests, 4)


def test_worker_service_with_no_positions_sends_empty_trade_list() -> None:
    from app.worker.schemas import BacktestWebhookDispatch

    captured_requests: list[dict[str, Any]] = []
    adapter = FakeTradingAgentsAdapter({})
    service = build_worker_service(
        prompt_report=(
            "# Cycle Prompt (2024-06-17)\n\n"
            "## System\n"
            "Today is 2024-06-17.\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Balances:\n"
            "- Cash: 10000.00 USD (DEPOSIT)\n"
            "Positions:\n"
            "- None\n\n"
            "Market data (last 30 trading days OHLCV):\n"
            "- No held symbols for this cycle\n\n"
            "Benchmark performance since start date:\n"
            "- ^GSPC: start=5200 end=5250 total_return=0.0096\n\n"
            "Prior reports:\n"
            "- None"
        ),
        adapter=adapter,
        captured_requests=captured_requests,
    )

    response = service.handle_dispatch(
        BacktestWebhookDispatch.model_validate(build_dispatch_payload())
    )

    assert response.model_dump(by_alias=True) == {
        "status": "completed",
        "reportSlug": "analysis_report_slug",
        "decisionCount": 0,
        "symbols": [],
    }
    assert adapter.calls == []
    assert captured_requests[2]["json"] == {
        "decisions": [],
        "reportSlug": "analysis_report_slug",
    }
    assert captured_requests[1]["json"]["content"] == (
        "# TradingAgents Analysis\n\n"
        "- Backtest ID: 42\n"
        "- Cycle date: 2024-06-17\n"
        "- Prompt report slug: prompt_report\n\n"
        "No held symbols were found in the prompt report."
    )


def test_worker_service_preserves_fractional_sell_quantities_by_holding() -> None:
    from app.worker.schemas import BacktestWebhookDispatch

    captured_requests: list[dict[str, Any]] = []
    adapter = FakeTradingAgentsAdapter({"AAPL": ("UNDERWEIGHT", "Trim the position.")})
    service = build_worker_service(
        prompt_report=(
            "# Cycle Prompt (2024-06-17)\n\n"
            "## System\n"
            "Today is 2024-06-17.\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Balances:\n"
            "- Cash: 10000.00 USD (DEPOSIT)\n"
            "Positions:\n"
            "- AAPL: 2.5 shares @ 180.00 USD\n\n"
            "Market data (last 30 trading days OHLCV):\n"
            "AAPL:\n"
            "- 2024-06-17: open=182 high=184 low=181 close=183 volume=1000000\n\n"
            "Benchmark performance since start date:\n"
            "- ^GSPC: start=5200 end=5250 total_return=0.0096\n\n"
            "Prior reports:\n"
            "- None"
        ),
        adapter=adapter,
        captured_requests=captured_requests,
    )

    response = service.handle_dispatch(
        BacktestWebhookDispatch.model_validate(build_dispatch_payload())
    )

    assert response.model_dump(by_alias=True) == {
        "status": "completed",
        "reportSlug": "analysis_report_slug",
        "decisionCount": 1,
        "symbols": ["AAPL"],
    }
    assert captured_requests[2]["json"] == {
        "decisions": [
            {
                "symbol": "AAPL",
                "action": "HOLD",
                "quantity": None,
                "targetPrice": None,
                "reasoning": (
                    "UNDERWEIGHT: Trim the position. Fractional held quantity 2.5 is "
                    "not supported for SELL in phase 1."
                ),
            }
        ],
        "reportSlug": "analysis_report_slug",
    }


def test_live_adapter_analyze_symbol_uses_installed_tradingagents_modules(
    monkeypatch: Any,
) -> None:
    from app.worker.trading_agents_adapter import LiveTradingAgentsAdapter

    default_config_module = importlib.import_module("tradingagents.default_config")
    trading_graph_module = importlib.import_module("tradingagents.graph.trading_graph")

    class FakeGraph:
        def __init__(self, *, debug: bool, config: dict[str, Any]) -> None:
            assert debug is False
            assert config == {"providers": ["fake"]}

        def propagate(self, symbol: str, cycle_date: str) -> tuple[dict[str, str], str]:
            assert symbol == "AAPL"
            assert cycle_date == "2024-06-17"
            return {"final_trade_decision": "Detailed TradingAgents thesis."}, "BUY"

    adapter = LiveTradingAgentsAdapter()
    monkeypatch.setattr(default_config_module, "DEFAULT_CONFIG", {"providers": ["fake"]})
    monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", FakeGraph)

    analysis = adapter.analyze_symbol(
        symbol="AAPL",
        cycle_date=date(2024, 6, 17),
        prompt_report="# Prompt",
        position_quantity="5",
    )

    assert analysis.label == "BUY"
    assert analysis.summary == "Detailed TradingAgents thesis."


def test_live_adapter_uses_installed_tradingagents_dependency(monkeypatch: Any) -> None:
    from app.worker.trading_agents_adapter import LiveTradingAgentsAdapter

    for env_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)

    adapter = LiveTradingAgentsAdapter()

    try:
        graph = adapter._get_graph()
    except Exception as exc:
        assert "api_key" in str(exc).lower() or "api key" in str(exc).lower()
    else:
        assert graph is not None


def test_live_adapter_applies_runtime_config_overrides(monkeypatch: Any) -> None:
    from app.worker.trading_agents_adapter import LiveTradingAgentsAdapter

    default_config_module = importlib.import_module("tradingagents.default_config")
    trading_graph_module = importlib.import_module("tradingagents.graph.trading_graph")

    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "http://192.168.1.222:8087/v1")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.4-mini")

    captured: dict[str, Any] = {}

    class FakeGraph:
        def __init__(self, *, debug: bool, config: dict[str, Any]) -> None:
            captured["debug"] = debug
            captured["config"] = config

        def propagate(self, symbol: str, cycle_date: str) -> tuple[dict[str, str], str]:
            return {
                "final_trade_decision": f"Configured analysis for {symbol} on {cycle_date}."
            }, "HOLD"

    adapter = LiveTradingAgentsAdapter()
    monkeypatch.setattr(default_config_module, "DEFAULT_CONFIG", {"providers": ["fake"]})
    monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", FakeGraph)

    analysis = adapter.analyze_symbol(
        symbol="TSLA",
        cycle_date=date(2025, 1, 15),
        prompt_report="# Prompt",
        position_quantity="5",
    )

    assert captured == {
        "debug": False,
        "config": {
            "providers": ["fake"],
            "llm_provider": "openai",
            "backend_url": "http://192.168.1.222:8087/v1",
            "quick_think_llm": "gpt-5.4-mini",
            "deep_think_llm": "gpt-5.4-mini",
        },
    }
    assert analysis.label == "HOLD"
