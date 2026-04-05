from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_portfolio_service
from app.schemas.portfolio import PortfolioCreate, PortfolioRead, PortfolioUpdate
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioRead])
def list_portfolios(
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> list[PortfolioRead]:
    return service.list_portfolios()


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> PortfolioRead:
    return service.create_portfolio(payload)


@router.get("/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(
    portfolio_id: int,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> PortfolioRead:
    return service.get_portfolio(portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> PortfolioRead:
    return service.update_portfolio(portfolio_id, payload)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    service: Annotated[PortfolioService, Depends(get_portfolio_service)],
) -> Response:
    service.delete_portfolio(portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
