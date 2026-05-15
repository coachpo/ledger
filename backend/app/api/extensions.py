from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_extension_service
from app.schemas.extension import ExtensionListRead, ExtensionRead, ExtensionToggleRequest
from app.services.extension_service import ExtensionService

router = APIRouter(prefix="/extensions", tags=["extensions"])


@router.get("", response_model=ExtensionListRead)
def list_extensions(
    service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> ExtensionListRead:
    return service.list_extensions()


@router.patch("/{extension_key}", response_model=ExtensionRead)
def toggle_extension(
    extension_key: str,
    payload: ExtensionToggleRequest,
    service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> ExtensionRead:
    return service.set_extension_enabled(extension_key, payload)
