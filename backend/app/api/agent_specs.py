from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_agent_spec_service
from app.schemas.runtime import SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    AgentSpecDraftCreate,
    AgentSpecDraftUpdate,
    AgentSpecListRead,
    AgentSpecRead,
)
from app.services.agent_spec_service import AgentSpecService

router = APIRouter(prefix="/agent-specs", tags=["agent-specs"])


@router.get("", response_model=AgentSpecListRead)
def list_agent_specs(
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
    origin: Annotated[SpecOrigin | None, Query()] = None,
    status_filter: Annotated[SpecLifecycleStatus | None, Query(alias="status")] = None,
) -> AgentSpecListRead:
    return service.list_specs(origin=origin, status_filter=status_filter)


@router.post("", response_model=AgentSpecRead, status_code=status.HTTP_201_CREATED)
def create_agent_spec_draft(
    payload: AgentSpecDraftCreate,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.create_draft(payload)


@router.get("/{spec_id}", response_model=AgentSpecRead)
def get_agent_spec(
    spec_id: int,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.get_spec(spec_id)


@router.patch("/{spec_id}", response_model=AgentSpecRead)
def update_agent_spec_draft(
    spec_id: int,
    payload: AgentSpecDraftUpdate,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.update_draft(spec_id, payload)


@router.post("/{spec_id}/activate", response_model=AgentSpecRead)
def activate_agent_spec(
    spec_id: int,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.activate(spec_id)


@router.post("/{spec_id}/deprecate", response_model=AgentSpecRead)
def deprecate_agent_spec(
    spec_id: int,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.deprecate(spec_id)


@router.post("/{spec_id}/archive", response_model=AgentSpecRead)
def archive_agent_spec(
    spec_id: int,
    service: Annotated[AgentSpecService, Depends(get_agent_spec_service)],
) -> AgentSpecRead:
    return service.archive(spec_id)
