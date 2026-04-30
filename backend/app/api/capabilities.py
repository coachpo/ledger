from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_capability_service
from app.schemas.skill import (
    CapabilityDraftCreate,
    CapabilityDraftUpdate,
    CapabilityListRead,
    CapabilityRead,
    SkillStatus,
)
from app.services.skill_service import SkillService

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilityListRead)
def list_capabilities(
    service: Annotated[SkillService, Depends(get_capability_service)],
    status_filter: Annotated[SkillStatus | None, Query(alias="status")] = None,
) -> CapabilityListRead:
    return service.list_capabilities(status_filter=status_filter)


@router.post("", response_model=CapabilityRead, status_code=status.HTTP_201_CREATED)
def create_capability_draft(
    payload: CapabilityDraftCreate,
    service: Annotated[SkillService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.create_capability_draft(payload)


@router.get("/{capability_id}", response_model=CapabilityRead)
def get_capability(
    capability_id: int,
    service: Annotated[SkillService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.get_capability(capability_id)


@router.patch("/{capability_id}", response_model=CapabilityRead)
def update_capability_draft(
    capability_id: int,
    payload: CapabilityDraftUpdate,
    service: Annotated[SkillService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.update_capability_draft(capability_id, payload)


@router.post("/{capability_id}/activate", response_model=CapabilityRead)
def activate_capability(
    capability_id: int,
    service: Annotated[SkillService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.activate_capability(capability_id)


@router.delete("/{capability_id}", response_model=CapabilityRead)
def archive_capability(
    capability_id: int,
    service: Annotated[SkillService, Depends(get_capability_service)],
) -> CapabilityRead:
    return service.archive_capability(capability_id)
