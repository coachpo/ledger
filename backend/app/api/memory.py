from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_memory_service
from app.schemas.memory import (
    MEMORY_API_MAX_EVENTS,
    MEMORY_API_MAX_REVISIONS,
    MemoryApiAccessRequest,
    MemoryApiEntryRead,
    MemoryApiEventListRead,
    MemoryApiListRead,
    MemoryApiListRequest,
    MemoryApiReflectRequest,
    MemoryApiResolveRequest,
    MemoryApiRevisionListRead,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", response_model=MemoryApiListRead)
def list_memory(
    payload: MemoryApiListRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryApiListRead:
    return service.list_api_memory(payload)


@router.post("/{memory_id}/detail", response_model=MemoryApiEntryRead)
def get_memory_detail(
    memory_id: str,
    payload: MemoryApiAccessRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryApiEntryRead:
    return service.get_api_memory(memory_id, payload)


@router.post("/{memory_id}/revisions", response_model=MemoryApiRevisionListRead)
def list_memory_revisions(
    memory_id: str,
    payload: MemoryApiAccessRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
    limit: Annotated[int, Query(ge=1, le=MEMORY_API_MAX_REVISIONS)] = (MEMORY_API_MAX_REVISIONS),
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryApiRevisionListRead:
    return service.list_api_memory_revisions(
        memory_id,
        payload,
        limit=limit,
        offset=offset,
    )


@router.post("/{memory_id}/events", response_model=MemoryApiEventListRead)
def list_memory_events(
    memory_id: str,
    payload: MemoryApiAccessRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
    limit: Annotated[int, Query(ge=1, le=MEMORY_API_MAX_EVENTS)] = MEMORY_API_MAX_EVENTS,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryApiEventListRead:
    return service.list_api_memory_events(
        memory_id,
        payload,
        limit=limit,
        offset=offset,
    )


@router.post("/{memory_id}/actions/resolve", response_model=MemoryApiEntryRead)
def resolve_memory(
    memory_id: str,
    payload: MemoryApiResolveRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryApiEntryRead:
    return service.resolve_api_memory(memory_id, payload)


@router.post("/{memory_id}/actions/reflect", response_model=MemoryApiEntryRead)
def reflect_memory(
    memory_id: str,
    payload: MemoryApiReflectRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryApiEntryRead:
    return service.reflect_api_memory(memory_id, payload)
