from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_run_service
from app.schemas.run import RunListRead, RunRead, RunStatus
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListRead)
def list_runs(
    service: Annotated[RunService, Depends(get_run_service)],
    workflow_id: Annotated[int | None, Query(alias="workflowId")] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
    workflow_version: Annotated[int | None, Query(alias="workflowVersion")] = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListRead:
    return service.list_runs(
        workflow_id=workflow_id,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunRead)
def get_run(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunRead:
    return service.get_run(run_id)
