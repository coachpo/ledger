from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_orchestration_service
from app.schemas.orchestration import (
    MentionCatalogRead,
    OrchestrationCharacterCreate,
    OrchestrationCharacterRead,
    OrchestrationCharacterUpdate,
    OrchestrationRoleCreate,
    OrchestrationRoleRead,
    OrchestrationRoleUpdate,
)
from app.services.orchestration_service import OrchestrationService

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


@router.get("/roles", response_model=list[OrchestrationRoleRead])
def list_roles(
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> list[OrchestrationRoleRead]:
    return service.list_roles()


@router.post("/roles", response_model=OrchestrationRoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: OrchestrationRoleCreate,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationRoleRead:
    return service.create_role(payload)


@router.get("/roles/{role_id}", response_model=OrchestrationRoleRead)
def get_role(
    role_id: int,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationRoleRead:
    return service.get_role(role_id)


@router.patch("/roles/{role_id}", response_model=OrchestrationRoleRead)
def update_role(
    role_id: int,
    payload: OrchestrationRoleUpdate,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationRoleRead:
    return service.update_role(role_id, payload)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> Response:
    service.delete_role(role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/characters", response_model=list[OrchestrationCharacterRead])
def list_characters(
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> list[OrchestrationCharacterRead]:
    return service.list_characters()


@router.post(
    "/characters", response_model=OrchestrationCharacterRead, status_code=status.HTTP_201_CREATED
)
def create_character(
    payload: OrchestrationCharacterCreate,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationCharacterRead:
    return service.create_character(payload)


@router.get("/characters/{character_id}", response_model=OrchestrationCharacterRead)
def get_character(
    character_id: int,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationCharacterRead:
    return service.get_character(character_id)


@router.patch("/characters/{character_id}", response_model=OrchestrationCharacterRead)
def update_character(
    character_id: int,
    payload: OrchestrationCharacterUpdate,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> OrchestrationCharacterRead:
    return service.update_character(character_id, payload)


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    character_id: int,
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> Response:
    service.delete_character(character_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/mentions/catalog", response_model=MentionCatalogRead)
def list_mention_catalog(
    service: Annotated[OrchestrationService, Depends(get_orchestration_service)],
) -> MentionCatalogRead:
    return service.list_mention_catalog()
