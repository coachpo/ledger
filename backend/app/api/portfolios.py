from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.extensions.signaldeck_finance.dependencies import PortfolioServiceDependency
from app.schemas.portfolio import PortfolioCreate, PortfolioRead, PortfolioUpdate

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioRead])
def list_portfolios(
    service: PortfolioServiceDependency,
) -> list[PortfolioRead]:
    return service.list_portfolios()


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    service: PortfolioServiceDependency,
) -> PortfolioRead:
    return service.create_portfolio(payload)


@router.get("/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(
    portfolio_id: int,
    service: PortfolioServiceDependency,
) -> PortfolioRead:
    return service.get_portfolio(portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    service: PortfolioServiceDependency,
) -> PortfolioRead:
    return service.update_portfolio(portfolio_id, payload)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    service: PortfolioServiceDependency,
) -> Response:
    service.delete_portfolio(portfolio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
