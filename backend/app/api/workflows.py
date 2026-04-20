from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_run_service, get_workflow_service
from app.schemas.run import RunCreatedRead
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListRead,
    WorkflowRead,
    WorkflowStatus,
    WorkflowUpdate,
)
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowListRead)
def list_workflows(
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    status_filter: Annotated[WorkflowStatus | None, Query(alias="status")] = None,
) -> WorkflowListRead:
    return service.list_workflows(status_filter=status_filter)


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.create_workflow(payload)


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(
    workflow_id: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    version: Annotated[int | None, Query()] = None,
) -> WorkflowRead:
    return service.get_workflow(workflow_id, version=version)


@router.post("/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.update_workflow(workflow_id, payload)


@router.post(
    "/{workflow_id}/runs",
    response_model=RunCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_run(
    workflow_id: int,
    payload: dict[str, Any],
    service: Annotated[RunService, Depends(get_run_service)],
    version: Annotated[int | None, Query()] = None,
) -> RunCreatedRead:
    return service.create_run(workflow_id, payload, version=version)


@router.delete("/{workflow_id}", response_model=WorkflowRead)
def archive_workflow(
    workflow_id: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.archive_workflow(workflow_id)
