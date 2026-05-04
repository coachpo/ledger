from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_run_service, get_workflow_service
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowLaunchCreateRequest,
    WorkflowLaunchCreateResponse,
    WorkflowLaunchRead,
    WorkflowListRead,
    WorkflowManifestValidationRead,
    WorkflowManifestValidationRequest,
    WorkflowRead,
    WorkflowStatus,
    WorkflowUpdateRequest,
    WorkflowVersionListRead,
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
    payload: WorkflowCreateRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.create_workflow(payload)


@router.post("/validate-manifest", response_model=WorkflowManifestValidationRead)
def validate_workflow_manifest(
    payload: WorkflowManifestValidationRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowManifestValidationRead:
    return service.validate_workflow_manifest(payload)


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
    payload: WorkflowUpdateRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.update_workflow(workflow_id, payload)


@router.get("/{workflow_id}/launch", response_model=WorkflowLaunchRead)
def get_workflow_launch(
    workflow_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
    version: Annotated[int | None, Query()] = None,
) -> WorkflowLaunchRead:
    return service.get_workflow_launch(workflow_id, version=version)


@router.get("/{workflow_id}/versions", response_model=WorkflowVersionListRead)
def list_workflow_versions(
    workflow_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> WorkflowVersionListRead:
    return service.list_workflow_versions(workflow_id)


@router.post(
    "/{workflow_id}/launches",
    response_model=WorkflowLaunchCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_launch(
    workflow_id: int,
    payload: WorkflowLaunchCreateRequest,
    service: Annotated[RunService, Depends(get_run_service)],
) -> WorkflowLaunchCreateResponse:
    return service.create_workflow_launch(workflow_id, payload)


@router.delete("/{workflow_id}", response_model=WorkflowRead)
def archive_workflow(
    workflow_id: int,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRead:
    return service.archive_workflow(workflow_id)
