from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_persona_profile_service
from app.schemas.runtime import PersonaProfileKind, SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    PersonaProfileDraftCreate,
    PersonaProfileDraftUpdate,
    PersonaProfileListRead,
    PersonaProfileRead,
    StudioVersionHistoryRead,
)
from app.services.persona_profile_service import PersonaProfileService

router = APIRouter(prefix="/personas", tags=["personas"])
studio_router = APIRouter(prefix="/studio/persona-profiles", tags=["studio-persona-profiles"])


@router.get("", response_model=PersonaProfileListRead)
def list_persona_profiles(
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
    origin: Annotated[SpecOrigin | None, Query()] = None,
    status_filter: Annotated[SpecLifecycleStatus | None, Query(alias="status")] = None,
    kind: Annotated[PersonaProfileKind | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> PersonaProfileListRead:
    return service.list_profiles(
        origin=origin,
        status_filter=status_filter,
        kind=kind,
        enabled=enabled,
    )


@router.get("/{persona_key}", response_model=PersonaProfileRead)
def get_persona_profile(
    persona_key: str,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.get_profile(persona_key)


@studio_router.get("", response_model=PersonaProfileListRead)
def list_studio_persona_profiles(
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
    origin: Annotated[SpecOrigin | None, Query()] = None,
    status_filter: Annotated[SpecLifecycleStatus | None, Query(alias="status")] = None,
    kind: Annotated[PersonaProfileKind | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> PersonaProfileListRead:
    return service.list_profiles(
        origin=origin,
        status_filter=status_filter,
        kind=kind,
        enabled=enabled,
    )


@studio_router.post("", response_model=PersonaProfileRead, status_code=status.HTTP_201_CREATED)
def create_studio_persona_profile_draft(
    payload: PersonaProfileDraftCreate,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.create_draft(payload)


@studio_router.get("/{persona_key}", response_model=PersonaProfileRead)
def get_studio_persona_profile(
    persona_key: str,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.get_profile(persona_key)


@studio_router.get("/{persona_key}/versions", response_model=StudioVersionHistoryRead)
def list_studio_persona_profile_versions(
    persona_key: str,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> StudioVersionHistoryRead:
    return service.list_versions(persona_key)


@studio_router.get("/{persona_key}/versions/{version}", response_model=PersonaProfileRead)
def get_studio_persona_profile_version(
    persona_key: str,
    version: int,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.get_version(persona_key, version)


@studio_router.patch("/{persona_key}/versions/{version}", response_model=PersonaProfileRead)
def update_studio_persona_profile_draft(
    persona_key: str,
    version: int,
    payload: PersonaProfileDraftUpdate,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.update_draft(persona_key, version, payload)


@studio_router.post("/{persona_key}/versions/{version}/activate", response_model=PersonaProfileRead)
def activate_studio_persona_profile(
    persona_key: str,
    version: int,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.activate(persona_key, version)


@studio_router.post(
    "/{persona_key}/versions/{version}/deprecate", response_model=PersonaProfileRead
)
def deprecate_studio_persona_profile(
    persona_key: str,
    version: int,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.deprecate(persona_key, version)


@studio_router.post("/{persona_key}/versions/{version}/archive", response_model=PersonaProfileRead)
def archive_studio_persona_profile(
    persona_key: str,
    version: int,
    service: Annotated[PersonaProfileService, Depends(get_persona_profile_service)],
) -> PersonaProfileRead:
    return service.archive(persona_key, version)
