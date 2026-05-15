from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.extensions.ledger_finance.dependencies import get_trading_operation_service
from app.schemas.trading_operation import (
    TradingOperationCreate,
    TradingOperationRead,
    TradingOperationResult,
)
from app.services.trading_operation_service import TradingOperationService

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/trading-operations", tags=["trading-operations"]
)


@router.get("", response_model=list[TradingOperationRead])
def list_trading_operations(
    portfolio_id: int,
    service: Annotated[TradingOperationService, Depends(get_trading_operation_service)],
) -> list[TradingOperationRead]:
    return service.list_operations(portfolio_id)


@router.post("", response_model=TradingOperationResult, status_code=status.HTTP_201_CREATED)
def create_trading_operation(
    portfolio_id: int,
    payload: TradingOperationCreate,
    service: Annotated[TradingOperationService, Depends(get_trading_operation_service)],
) -> TradingOperationResult:
    return service.create_operation(portfolio_id, payload)
