from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies import get_run_service
from app.core.errors import validation_error
from app.schemas.run import (
    RunCreatedRead,
    RunForkCreateRequest,
    RunForkDraftRead,
    RunListRead,
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
)
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListRead)
def list_runs(
    request: Request,
    service: Annotated[RunService, Depends(get_run_service)],
    workflow_package_key: Annotated[str | None, Query(alias="workflowPackageKey")] = None,
    workflow_package_id: Annotated[int | None, Query(alias="workflowPackageId")] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
    model_connection_key: Annotated[str | None, Query(alias="modelConnectionKey")] = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListRead:
    if any(key in request.query_params for key in ("targetKind", "targetId", "targetKey")):
        raise validation_error(
            "Request validation failed",
            [
                {
                    "field": "targetKind",
                    "issue": (
                        "targetKind, targetId, and targetKey are no longer supported "
                        "for runs filtering; use workflowPackageId, "
                        "workflowPackageKey, or workflowKey."
                    ),
                }
            ],
        )

    return service.list_runs(
        workflow_package_key=workflow_package_key,
        workflow_package_id=workflow_package_id,
        workflow_key=workflow_key,
        model_connection_key=model_connection_key,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}/rerun-draft", response_model=RunRerunDraftRead)
def build_run_rerun_draft(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunRerunDraftRead:
    return service.build_rerun_draft(run_id)


@router.post(
    "/{run_id}/reruns",
    response_model=RunCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_run_rerun(
    run_id: int,
    payload: RunRerunCreateRequest,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunCreatedRead:
    return service.create_rerun(run_id, payload)


@router.get("/{run_id}/fork-draft", response_model=RunForkDraftRead)
def build_run_fork_draft(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
    source_invocation_id: Annotated[int, Query(alias="sourceInvocationId", ge=1)],
) -> RunForkDraftRead:
    return service.build_fork_draft(run_id, source_invocation_id)


@router.post(
    "/{run_id}/forks",
    response_model=RunCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_run_fork(
    run_id: int,
    payload: RunForkCreateRequest,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunCreatedRead:
    return service.create_fork(run_id, payload)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> Response:
    service.delete_run(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{run_id}", response_model=RunRead)
def get_run(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunRead:
    return service.get_run(run_id)
