from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_skill_service
from app.schemas.skill import (
    SkillDraftCreate,
    SkillDraftUpdate,
    SkillListRead,
    SkillRead,
    SkillStatus,
)
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillListRead)
def list_skills(
    service: Annotated[SkillService, Depends(get_skill_service)],
    status_filter: Annotated[SkillStatus | None, Query(alias="status")] = None,
) -> SkillListRead:
    return service.list_skills(status_filter=status_filter)


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
def create_skill_draft(
    payload: SkillDraftCreate,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillRead:
    return service.create_draft(payload)


@router.get("/{skill_id}", response_model=SkillRead)
def get_skill(
    skill_id: int,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillRead:
    return service.get_skill(skill_id)


@router.patch("/{skill_id}", response_model=SkillRead)
def update_skill_draft(
    skill_id: int,
    payload: SkillDraftUpdate,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillRead:
    return service.update_draft(skill_id, payload)


@router.post("/{skill_id}/activate", response_model=SkillRead)
def activate_skill(
    skill_id: int,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillRead:
    return service.activate(skill_id)


@router.delete("/{skill_id}", response_model=SkillRead)
def archive_skill(
    skill_id: int,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> SkillRead:
    return service.archive(skill_id)
