from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_workflow_spec_service
from app.schemas.runtime import SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    WorkflowSpecDraftCreate,
    WorkflowSpecDraftUpdate,
    WorkflowSpecListRead,
    WorkflowSpecRead,
)
from app.services.workflow_spec_service import WorkflowSpecService

router = APIRouter(prefix="/workflow-specs", tags=["workflow-specs"])


@router.get("", response_model=WorkflowSpecListRead)
def list_workflow_specs(
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
    origin: Annotated[SpecOrigin | None, Query()] = None,
    status_filter: Annotated[SpecLifecycleStatus | None, Query(alias="status")] = None,
) -> WorkflowSpecListRead:
    return service.list_specs(origin=origin, status_filter=status_filter)


@router.post("", response_model=WorkflowSpecRead, status_code=status.HTTP_201_CREATED)
def create_workflow_spec_draft(
    payload: WorkflowSpecDraftCreate,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.create_draft(payload)


@router.get("/{spec_id}", response_model=WorkflowSpecRead)
def get_workflow_spec(
    spec_id: int,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.get_spec(spec_id)


@router.patch("/{spec_id}", response_model=WorkflowSpecRead)
def update_workflow_spec_draft(
    spec_id: int,
    payload: WorkflowSpecDraftUpdate,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.update_draft(spec_id, payload)


@router.post("/{spec_id}/activate", response_model=WorkflowSpecRead)
def activate_workflow_spec(
    spec_id: int,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.activate(spec_id)


@router.post("/{spec_id}/deprecate", response_model=WorkflowSpecRead)
def deprecate_workflow_spec(
    spec_id: int,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.deprecate(spec_id)


@router.post("/{spec_id}/archive", response_model=WorkflowSpecRead)
def archive_workflow_spec(
    spec_id: int,
    service: Annotated[WorkflowSpecService, Depends(get_workflow_spec_service)],
) -> WorkflowSpecRead:
    return service.archive(spec_id)
