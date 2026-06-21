from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.extensions.signaldeck_finance.dependencies import BalanceServiceDependency
from app.schemas.balance import BalanceCreate, BalanceRead, BalanceUpdate

router = APIRouter(prefix="/portfolios/{portfolio_id}/balances", tags=["balances"])


@router.get("", response_model=list[BalanceRead])
def list_balances(
    portfolio_id: int,
    service: BalanceServiceDependency,
) -> list[BalanceRead]:
    return service.list_balances(portfolio_id)


@router.post("", response_model=BalanceRead, status_code=status.HTTP_201_CREATED)
def create_balance(
    portfolio_id: int,
    payload: BalanceCreate,
    service: BalanceServiceDependency,
) -> BalanceRead:
    return service.create_balance(portfolio_id, payload)


@router.patch("/{balance_id}", response_model=BalanceRead)
def update_balance(
    portfolio_id: int,
    balance_id: int,
    payload: BalanceUpdate,
    service: BalanceServiceDependency,
) -> BalanceRead:
    return service.update_balance(portfolio_id, balance_id, payload)


@router.delete("/{balance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_balance(
    portfolio_id: int,
    balance_id: int,
    service: BalanceServiceDependency,
) -> Response:
    service.delete_balance(portfolio_id, balance_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
