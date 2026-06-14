from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import ValidationError

from app.api.dependencies import get_memory_service
from app.core.errors import validation_error
from app.schemas.memory import (
    MEMORY_ADMIN_LIST_DEFAULT_LIMIT,
    MEMORY_ADMIN_LIST_MAX_LIMIT,
    MEMORY_API_MAX_EVENTS,
    MEMORY_API_MAX_REVISIONS,
    MemoryAdminCreateRequest,
    MemoryAdminEntryRead,
    MemoryAdminEventListRead,
    MemoryAdminListQuery,
    MemoryAdminListRead,
    MemoryAdminRevisionCreateRequest,
    MemoryAdminRevisionListRead,
    MemoryAdminSort,
    MemoryAdminWorkflowVisibilityUpdateRequest,
    MemoryApiAccessRequest,
    MemoryApiEntryRead,
    MemoryApiEventListRead,
    MemoryApiListRead,
    MemoryApiListRequest,
    MemoryApiReflectRequest,
    MemoryApiResolveRequest,
    MemoryApiRevisionListRead,
    MemoryScopeType,
)
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_admin_list_query(
    *,
    package_key: str | None,
    workflow_key: str | None,
    agent_key: str | None,
    run_id: int | None,
    scope_type: MemoryScopeType | None,
    kind: str | None,
    visible_to_workflow: bool | None,
    query: str | None,
    limit: int,
    offset: int,
    sort: MemoryAdminSort,
) -> MemoryAdminListQuery:
    try:
        return MemoryAdminListQuery(
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            run_id=run_id,
            scope_type=scope_type,
            kind=kind,
            visible_to_workflow=visible_to_workflow,
            query=query,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "issue": str(error["msg"])}
            for error in exc.errors()
        ]
        raise validation_error("Request validation failed", details) from exc


@router.get("/admin/entries", response_model=MemoryAdminListRead)
def list_admin_memory_entries(
    service: Annotated[MemoryService, Depends(get_memory_service)],
    package_key: Annotated[str | None, Query(alias="packageKey", max_length=120)] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey", max_length=120)] = None,
    agent_key: Annotated[str | None, Query(alias="agentKey", max_length=120)] = None,
    run_id: Annotated[int | None, Query(alias="runId", ge=1)] = None,
    scope_type: Annotated[MemoryScopeType | None, Query(alias="scopeType")] = None,
    kind: Annotated[str | None, Query(max_length=80)] = None,
    visible_to_workflow: Annotated[bool | None, Query(alias="visibleToWorkflow")] = None,
    query: Annotated[str | None, Query(max_length=1_000)] = None,
    limit: Annotated[int, Query(ge=1, le=MEMORY_ADMIN_LIST_MAX_LIMIT)] = (
        MEMORY_ADMIN_LIST_DEFAULT_LIMIT
    ),
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[MemoryAdminSort, Query()] = "updatedAtDesc",
) -> MemoryAdminListRead:
    payload = _memory_admin_list_query(
        package_key=package_key,
        workflow_key=workflow_key,
        agent_key=agent_key,
        run_id=run_id,
        scope_type=scope_type,
        kind=kind,
        visible_to_workflow=visible_to_workflow,
        query=query,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    return service.list_admin_memory(payload)


@router.post("/admin/entries", response_model=MemoryAdminEntryRead)
def create_admin_memory_entry(
    payload: MemoryAdminCreateRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryAdminEntryRead:
    return service.create_admin_memory(payload)


@router.get("/admin/entries/{memory_id}", response_model=MemoryAdminEntryRead)
def get_admin_memory_entry(
    memory_id: str,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryAdminEntryRead:
    return service.get_admin_memory(memory_id)


@router.delete("/admin/entries/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_memory_entry(
    memory_id: str,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> Response:
    service.delete_admin_memory(memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/entries/{memory_id}/revisions", response_model=MemoryAdminRevisionListRead)
def list_admin_memory_revisions(
    memory_id: str,
    service: Annotated[MemoryService, Depends(get_memory_service)],
    limit: Annotated[int, Query(ge=1, le=MEMORY_API_MAX_REVISIONS)] = MEMORY_API_MAX_REVISIONS,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryAdminRevisionListRead:
    return service.list_admin_memory_revisions(memory_id, limit=limit, offset=offset)


@router.get("/admin/entries/{memory_id}/events", response_model=MemoryAdminEventListRead)
def list_admin_memory_events(
    memory_id: str,
    service: Annotated[MemoryService, Depends(get_memory_service)],
    limit: Annotated[int, Query(ge=1, le=MEMORY_API_MAX_EVENTS)] = MEMORY_API_MAX_EVENTS,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryAdminEventListRead:
    return service.list_admin_memory_events(memory_id, limit=limit, offset=offset)


@router.post("/admin/entries/{memory_id}/revisions", response_model=MemoryAdminEntryRead)
def create_admin_memory_revision(
    memory_id: str,
    payload: MemoryAdminRevisionCreateRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryAdminEntryRead:
    return service.create_admin_memory_revision(memory_id, payload)


@router.patch("/admin/entries/{memory_id}/workflow-visibility", response_model=MemoryAdminEntryRead)
def update_admin_memory_workflow_visibility(
    memory_id: str,
    payload: MemoryAdminWorkflowVisibilityUpdateRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> MemoryAdminEntryRead:
    return service.update_admin_memory_workflow_visibility(memory_id, payload)


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
