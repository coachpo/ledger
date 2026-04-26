from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_agent_service
from app.schemas.agent import (
    AgentCreate,
    AgentListRead,
    AgentRead,
    AgentStatus,
    AgentUpdate,
)
from app.schemas.run import RunCreatedRead
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListRead)
def list_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
    status_filter: Annotated[AgentStatus | None, Query(alias="status")] = None,
    model_name: Annotated[str | None, Query(alias="model")] = None,
) -> AgentListRead:
    return service.list_agents(status_filter=status_filter, model_name=model_name)


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return service.create_agent(payload)


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(
    agent_id: int,
    service: Annotated[AgentService, Depends(get_agent_service)],
    version: Annotated[int | None, Query()] = None,
) -> AgentRead:
    return service.get_agent(agent_id, version=version)


@router.post("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return service.update_agent(agent_id, payload)


@router.delete("/{agent_id}", response_model=AgentRead)
def archive_agent(
    agent_id: int,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return service.archive_agent(agent_id)


@router.post(
    "/{agent_id}/runs",
    response_model=RunCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run(
    agent_id: int,
    payload: dict[str, Any],
    service: Annotated[AgentService, Depends(get_agent_service)],
    version: Annotated[int | None, Query()] = None,
) -> RunCreatedRead:
    return service.create_run(agent_id, payload, version=version)
