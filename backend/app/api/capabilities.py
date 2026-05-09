from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_capability_service
from app.schemas.capability import (
    CapabilityDraftCreate,
    CapabilityDraftUpdate,
    CapabilityListRead,
    CapabilityRead,
    CapabilityStatus,
    CapabilityToolListRead,
)
from app.services.capability_service import CapabilityService

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilityListRead)
def list_capabilities(
    service: Annotated[CapabilityService, Depends(get_capability_service)],
    status_filter: Annotated[CapabilityStatus | None, Query(alias="status")] = None,
) -> CapabilityListRead:
    return service.list_capabilities(status_filter=status_filter)


@router.post("", response_model=CapabilityRead, status_code=status.HTTP_201_CREATED)
def create_capability_draft(
    payload: CapabilityDraftCreate,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.create_draft(payload)


@router.get("/tools", response_model=CapabilityToolListRead)
def list_capability_tools(
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityToolListRead:
    return service.list_available_tools()


@router.get("/{capability_id}", response_model=CapabilityRead)
def get_capability(
    capability_id: int,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.get_capability(capability_id)


@router.patch("/{capability_id}", response_model=CapabilityRead)
def update_capability_draft(
    capability_id: int,
    payload: CapabilityDraftUpdate,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.update_draft(capability_id, payload)


@router.post("/{capability_id}/activate", response_model=CapabilityRead)
def activate_capability(
    capability_id: int,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.activate(capability_id)


@router.delete("/{capability_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_capability(
    capability_id: int,
    service: Annotated[CapabilityService, Depends(get_capability_service)],
) -> Response:
    service.delete_capability(capability_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
