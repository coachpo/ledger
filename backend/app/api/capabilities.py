from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_capability_registry_service
from app.schemas.runtime import CapabilityType, SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    CapabilityRegistryEntryDraftCreate,
    CapabilityRegistryEntryDraftUpdate,
    CapabilityRegistryEntryListRead,
    CapabilityRegistryEntryRead,
)
from app.services.capability_registry_service import CapabilityRegistryService

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilityRegistryEntryListRead)
def list_capabilities(
    service: Annotated[CapabilityRegistryService, Depends(get_capability_registry_service)],
    origin: Annotated[SpecOrigin | None, Query()] = None,
    status_filter: Annotated[SpecLifecycleStatus | None, Query(alias="status")] = None,
    capability_type: Annotated[CapabilityType | None, Query(alias="type")] = None,
) -> CapabilityRegistryEntryListRead:
    return service.list_specs(
        origin=origin,
        status_filter=status_filter,
        capability_type=capability_type,
    )


@router.post("", response_model=CapabilityRegistryEntryRead, status_code=status.HTTP_201_CREATED)
def create_capability_draft(
    payload: CapabilityRegistryEntryDraftCreate,
    service: Annotated[CapabilityRegistryService, Depends(get_capability_registry_service)],
) -> CapabilityRegistryEntryRead:
    return service.create_draft(payload)


@router.get("/{spec_id}", response_model=CapabilityRegistryEntryRead)
def get_capability(
    spec_id: int,
    service: Annotated[CapabilityRegistryService, Depends(get_capability_registry_service)],
) -> CapabilityRegistryEntryRead:
    return service.get_spec(spec_id)


@router.patch("/{spec_id}", response_model=CapabilityRegistryEntryRead)
def update_capability_draft(
    spec_id: int,
    payload: CapabilityRegistryEntryDraftUpdate,
    service: Annotated[CapabilityRegistryService, Depends(get_capability_registry_service)],
) -> CapabilityRegistryEntryRead:
    return service.update_draft(spec_id, payload)


@router.post("/{spec_id}/activate", response_model=CapabilityRegistryEntryRead)
def activate_capability(
    spec_id: int,
    service: Annotated[CapabilityRegistryService, Depends(get_capability_registry_service)],
) -> CapabilityRegistryEntryRead:
    return service.activate(spec_id)
