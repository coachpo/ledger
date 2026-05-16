from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import APIRouter, Depends
from fastapi.params import Depends as DependsMarker

from app.api.balances import router as balances_router
from app.api.dependencies import require_extension_enabled
from app.api.market_data import router as market_data_router
from app.api.portfolios import router as portfolios_router
from app.api.positions import router as positions_router
from app.api.reports import router as reports_router
from app.api.templates import router as templates_router
from app.api.trading_operations import router as trading_operations_router
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceApiRouterRegistration:
    router: APIRouter
    surface: str
    dependencies: tuple[DependsMarker, ...]


def _extension_gate(surface: str) -> DependsMarker:
    return cast(
        DependsMarker,
        Depends(
            require_extension_enabled(
                extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
                surface=surface,
            )
        ),
    )


def _registration(router: APIRouter, surface: str) -> FinanceWorkspaceApiRouterRegistration:
    return FinanceWorkspaceApiRouterRegistration(
        router=router,
        surface=surface,
        dependencies=(_extension_gate(surface),),
    )


def register() -> tuple[FinanceWorkspaceApiRouterRegistration, ...]:
    return (
        _registration(portfolios_router, "/api/v1/portfolios"),
        _registration(balances_router, "/api/v1/portfolios/{portfolio_id}/balances"),
        _registration(positions_router, "/api/v1/portfolios/{portfolio_id}/positions"),
        _registration(
            trading_operations_router,
            "/api/v1/portfolios/{portfolio_id}/trading-operations",
        ),
        _registration(market_data_router, "/api/v1/portfolios/{portfolio_id}/market-data"),
        _registration(templates_router, "/api/v1/templates"),
        _registration(reports_router, "/api/v1/reports"),
    )


__all__ = ["FinanceWorkspaceApiRouterRegistration", "register"]
