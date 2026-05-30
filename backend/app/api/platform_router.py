# pyright: reportMissingImports=false
from fastapi import APIRouter

from app.api.extensions import router as extensions_router
from app.api.memory import router as memory_router
from app.api.model_connections import router as model_connections_router
from app.api.runs import router as runs_router
from app.api.schedules import router as schedules_router
from app.api.tools import router as tools_router
from app.api.workflow_packages import router as workflow_packages_router

platform_router = APIRouter(prefix="/api")
platform_router.include_router(extensions_router)
platform_router.include_router(memory_router)
platform_router.include_router(model_connections_router)
platform_router.include_router(tools_router)
platform_router.include_router(workflow_packages_router)
platform_router.include_router(schedules_router)
platform_router.include_router(runs_router)
