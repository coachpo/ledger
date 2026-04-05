from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_backtest_service
from app.schemas.backtest import BacktestCreate, BacktestRead
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("", response_model=list[BacktestRead])
def list_backtests(
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> list[BacktestRead]:
    return service.list_backtests()


@router.post("", response_model=BacktestRead, status_code=status.HTTP_201_CREATED)
def create_backtest(
    payload: BacktestCreate,
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestRead:
    return service.create_backtest(payload)


@router.get("/{backtest_id}", response_model=BacktestRead)
def get_backtest(
    backtest_id: int,
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestRead:
    return service.get_backtest(backtest_id)


@router.post("/{backtest_id}/cancel", response_model=BacktestRead)
def cancel_backtest(
    backtest_id: int,
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestRead:
    return service.cancel_backtest(backtest_id)


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest(
    backtest_id: int,
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> Response:
    service.delete_backtest(backtest_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
