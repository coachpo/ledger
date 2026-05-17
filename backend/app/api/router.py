from fastapi import APIRouter

from app.extensions.registry import get_bundled_extension_registry

api_router = APIRouter(prefix="/api/v1")
for contribution in get_bundled_extension_registry().list_api_router_contributions():
    api_router.include_router(
        contribution.router,
        dependencies=list(contribution.dependencies),
    )
