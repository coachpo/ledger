from __future__ import annotations

from fastapi import APIRouter, status

from app.extensions.signaldeck_finance.dependencies import TradingOperationServiceDependency
from app.schemas.trading_operation import (
    TradingOperationCreate,
    TradingOperationRead,
    TradingOperationResult,
)

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/trading-operations", tags=["trading-operations"]
)


@router.get("", response_model=list[TradingOperationRead])
def list_trading_operations(
    portfolio_id: int,
    service: TradingOperationServiceDependency,
) -> list[TradingOperationRead]:
    return service.list_operations(portfolio_id)


@router.post("", response_model=TradingOperationResult, status_code=status.HTTP_201_CREATED)
def create_trading_operation(
    portfolio_id: int,
    payload: TradingOperationCreate,
    service: TradingOperationServiceDependency,
) -> TradingOperationResult:
    return service.create_operation(portfolio_id, payload)
