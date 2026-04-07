from __future__ import annotations

import httpx
import uvicorn
from fastapi import Depends, FastAPI

from app.worker.schemas import BacktestWebhookDispatch, BacktestWebhookDispatchAcceptedResponse
from app.worker.service import BacktestWebhookWorkerService
from app.worker.trading_agents_adapter import LiveTradingAgentsAdapter, TradingAgentsAdapter


def get_trading_agents_adapter() -> TradingAgentsAdapter:
    return LiveTradingAgentsAdapter()


def create_worker_http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def get_worker_service() -> BacktestWebhookWorkerService:
    return BacktestWebhookWorkerService(
        http_client_factory=create_worker_http_client,
        adapter_factory=get_trading_agents_adapter,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Ledger TradingAgents Worker", version="0.1.0")

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/trading-agents/dispatch",
        response_model=BacktestWebhookDispatchAcceptedResponse,
        status_code=202,
    )
    def dispatch_backtest_cycle(
        payload: BacktestWebhookDispatch,
        service: BacktestWebhookWorkerService = Depends(get_worker_service),
    ) -> BacktestWebhookDispatchAcceptedResponse:
        return service.dispatch_async(payload)

    return app


app = create_app()


def main() -> None:
    uvicorn.run("app.worker.main:app", host="0.0.0.0", port=8010)


if __name__ == "__main__":
    main()
