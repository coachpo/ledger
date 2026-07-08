from fastapi import APIRouter

from app.extensions.registry import INSTALLED_EXTENSIONS

api_router = APIRouter(prefix="/api/v1")
for extension in INSTALLED_EXTENSIONS:
    for router in extension.api_routers:
        api_router.include_router(router)
