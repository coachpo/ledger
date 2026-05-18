from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_agent_service  # type: ignore[attr-defined]
from app.schemas.agent import (
    AgentListRead,
    AgentManifestValidationRead,
    AgentManifestValidationRequest,
    AgentManifestWriteRequest,
    AgentRead,
    AgentStatus,
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
    payload: AgentManifestWriteRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return service.create_agent_from_manifest(payload.manifest_source)


@router.post("/validate-manifest", response_model=AgentManifestValidationRead)
def validate_agent_manifest(
    payload: AgentManifestValidationRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentManifestValidationRead:
    return service.validate_agent_manifest(payload)


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
    payload: AgentManifestWriteRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRead:
    return service.update_agent_from_manifest(agent_id, payload.manifest_source)


@router.delete("/{agent_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: int,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> Response:
    service.delete_agent(agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
