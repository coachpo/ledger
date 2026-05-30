from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_workflow_package_schedule_service
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleFireListRead,
    ScheduleListRead,
    SchedulePreviewRead,
    SchedulePreviewRequest,
    SchedulePreviewUnsavedRequest,
    ScheduleRead,
    ScheduleRunNowRead,
    ScheduleRunNowRequest,
    ScheduleStatus,
    ScheduleUpdate,
)
from app.services.workflow_package_schedule_service import WorkflowPackageScheduleService

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("", response_model=ScheduleListRead)
def list_schedules(
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
    package_id: Annotated[int | None, Query(alias="packageId", ge=1)] = None,
    package_key: Annotated[str | None, Query(alias="packageKey")] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
    status_filter: Annotated[ScheduleStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScheduleListRead:
    return service.list_schedules(
        package_id=package_id,
        package_key=package_key,
        workflow_key=workflow_key,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: ScheduleCreate,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.create_schedule(payload)


@router.post("/preview", response_model=SchedulePreviewRead)
def preview_unsaved_schedule(
    payload: SchedulePreviewUnsavedRequest,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> SchedulePreviewRead:
    return service.preview_unsaved_schedule(payload)


@router.get("/{schedule_id}", response_model=ScheduleRead)
def get_schedule(
    schedule_id: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.get_schedule(schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleRead)
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.update_schedule(schedule_id, payload)


@router.post("/{schedule_id}/archive", response_model=ScheduleRead)
def archive_schedule(
    schedule_id: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.archive_schedule(schedule_id)


@router.post("/{schedule_id}/preview", response_model=SchedulePreviewRead)
def preview_schedule(
    schedule_id: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
    payload: SchedulePreviewRequest | None = None,
) -> SchedulePreviewRead:
    return service.preview_schedule(schedule_id, payload)


@router.post(
    "/{schedule_id}/run-now",
    response_model=ScheduleRunNowRead,
    status_code=status.HTTP_201_CREATED,
)
def run_schedule_now(
    schedule_id: int,
    payload: ScheduleRunNowRequest,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRunNowRead:
    return service.run_schedule_now(schedule_id, payload)


@router.get("/{schedule_id}/fires", response_model=ScheduleFireListRead)
def list_schedule_fires(
    schedule_id: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScheduleFireListRead:
    return service.list_fire_history(schedule_id, limit=limit, offset=offset)
