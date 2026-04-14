from fastapi import APIRouter

from app.api.agent_specs import router as agent_specs_router
from app.api.capabilities import router as capabilities_router
from app.api.personas import router as personas_router
from app.api.personas import studio_router as studio_personas_router
from app.api.runtime import router as runtime_router
from app.api.runtime_control import router as runtime_control_router
from app.api.studio import router as studio_router
from app.api.tryouts import router as tryouts_router
from app.api.workflow_specs import router as workflow_specs_router

v2_router = APIRouter(prefix="/api/v2")
v2_router.include_router(agent_specs_router)
v2_router.include_router(capabilities_router)
v2_router.include_router(personas_router)
v2_router.include_router(studio_personas_router)
v2_router.include_router(runtime_router)
v2_router.include_router(runtime_control_router)
v2_router.include_router(studio_router)
v2_router.include_router(tryouts_router)
v2_router.include_router(workflow_specs_router)
