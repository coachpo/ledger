from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.extensions.ledger_finance.dependencies import get_balance_service
from app.schemas.balance import BalanceCreate, BalanceRead, BalanceUpdate
from app.services.balance_service import BalanceService

router = APIRouter(prefix="/portfolios/{portfolio_id}/balances", tags=["balances"])


@router.get("", response_model=list[BalanceRead])
def list_balances(
    portfolio_id: int,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> list[BalanceRead]:
    return service.list_balances(portfolio_id)


@router.post("", response_model=BalanceRead, status_code=status.HTTP_201_CREATED)
def create_balance(
    portfolio_id: int,
    payload: BalanceCreate,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> BalanceRead:
    return service.create_balance(portfolio_id, payload)


@router.patch("/{balance_id}", response_model=BalanceRead)
def update_balance(
    portfolio_id: int,
    balance_id: int,
    payload: BalanceUpdate,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> BalanceRead:
    return service.update_balance(portfolio_id, balance_id, payload)


@router.delete("/{balance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_balance(
    portfolio_id: int,
    balance_id: int,
    service: Annotated[BalanceService, Depends(get_balance_service)],
) -> Response:
    service.delete_balance(portfolio_id, balance_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
