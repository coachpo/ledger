from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_backtest_cycle_service
from app.schemas.backtest_callback import (
    CycleCompleteResponse,
    CycleReportUpload,
    CycleReportUploadResponse,
    CycleTradesRequest,
    CycleTradesResponse,
)
from app.services.backtest_cycle_service import BacktestCycleService

router = APIRouter(prefix="/backtests", tags=["backtest-callbacks"])


@router.post(
    "/{backtest_id}/cycles/{cycle_date}/report",
    response_model=CycleReportUploadResponse,
    status_code=201,
)
def upload_cycle_report(
    backtest_id: int,
    cycle_date: date,
    payload: CycleReportUpload,
    service: Annotated[BacktestCycleService, Depends(get_backtest_cycle_service)],
) -> CycleReportUploadResponse:
    slug = service.handle_report_callback(backtest_id, cycle_date, payload)
    return CycleReportUploadResponse(slug=slug)


@router.post(
    "/{backtest_id}/cycles/{cycle_date}/trades",
    response_model=CycleTradesResponse,
)
def execute_cycle_trades(
    backtest_id: int,
    cycle_date: date,
    payload: CycleTradesRequest,
    service: Annotated[BacktestCycleService, Depends(get_backtest_cycle_service)],
) -> CycleTradesResponse:
    return service.handle_trades_callback(backtest_id, cycle_date, payload)


@router.post(
    "/{backtest_id}/cycles/{cycle_date}/complete",
    response_model=CycleCompleteResponse,
)
def complete_cycle(
    backtest_id: int,
    cycle_date: date,
    service: Annotated[BacktestCycleService, Depends(get_backtest_cycle_service)],
) -> CycleCompleteResponse:
    return service.handle_cycle_complete(backtest_id, cycle_date)
