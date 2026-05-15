from fastapi import APIRouter

from app.extensions.ledger_finance.api_routers import (
    register as register_finance_workspace_api_routers,
)

api_router = APIRouter(prefix="/api/v1")
for registration in register_finance_workspace_api_routers():
    api_router.include_router(
        registration.router,
        dependencies=list(registration.dependencies),
    )
