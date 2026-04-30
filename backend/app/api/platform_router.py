from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.capabilities import router as capabilities_router
from app.api.mcp_servers import router as mcp_servers_router
from app.api.model_connections import router as model_connections_router
from app.api.output_schemas import router as output_schemas_router
from app.api.runs import router as runs_router
from app.api.skills import router as skills_router
from app.api.workflows import router as workflows_router

platform_router = APIRouter(prefix="/api")
platform_router.include_router(agents_router)
platform_router.include_router(capabilities_router)
platform_router.include_router(skills_router)
platform_router.include_router(mcp_servers_router)
platform_router.include_router(model_connections_router)
platform_router.include_router(output_schemas_router)
platform_router.include_router(workflows_router)
platform_router.include_router(runs_router)
