from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

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


@router.get("/{scheduleId}", response_model=ScheduleRead)
def get_schedule(
    scheduleId: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.get_schedule(scheduleId)


@router.patch("/{scheduleId}", response_model=ScheduleRead)
def update_schedule(
    scheduleId: int,
    payload: ScheduleUpdate,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRead:
    return service.update_schedule(scheduleId, payload)


@router.delete("/{scheduleId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    scheduleId: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> Response:
    service.delete_schedule(scheduleId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{scheduleId}/preview", response_model=SchedulePreviewRead)
def preview_schedule(
    scheduleId: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
    payload: SchedulePreviewRequest | None = None,
) -> SchedulePreviewRead:
    return service.preview_schedule(scheduleId, payload)


@router.post(
    "/{scheduleId}/run-now",
    response_model=ScheduleRunNowRead,
    status_code=status.HTTP_201_CREATED,
)
def run_schedule_now(
    scheduleId: int,
    payload: ScheduleRunNowRequest,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
) -> ScheduleRunNowRead:
    return service.run_schedule_now(scheduleId, payload)


@router.get("/{scheduleId}/fires", response_model=ScheduleFireListRead)
def list_schedule_fires(
    scheduleId: int,
    service: Annotated[
        WorkflowPackageScheduleService,
        Depends(get_workflow_package_schedule_service),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScheduleFireListRead:
    return service.list_fire_history(scheduleId, limit=limit, offset=offset)
