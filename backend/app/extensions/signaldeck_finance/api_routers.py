from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends
from fastapi.params import Depends as DependsMarker

from app.extensions import BundledApiRouterContribution
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


def _extension_gate(surface: str) -> DependsMarker:
    from app.api.dependencies import require_extension_enabled

    return cast(
        DependsMarker,
        Depends(
            require_extension_enabled(
                extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
                surface=surface,
            )
        ),
    )


def _registration(router: APIRouter, surface: str) -> BundledApiRouterContribution:
    return BundledApiRouterContribution(
        router=router,
        surface=surface,
        dependencies=(_extension_gate(surface),),
    )


def register() -> tuple[BundledApiRouterContribution, ...]:
    from app.api.reports import router as reports_router
    from app.api.templates import router as templates_router

    return (
        _registration(templates_router, "/api/v1/templates"),
        _registration(reports_router, "/api/v1/reports"),
    )


__all__ = ["register"]
