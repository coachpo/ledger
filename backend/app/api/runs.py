from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_run_service
from app.core.errors import validation_error
from app.schemas.run import (
    RunCreatedRead,
    RunListRead,
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunStepReplayCreateRequest,
    RunStepReplayDraftRead,
    RunTargetKind,
)
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListRead)
def list_runs(
    service: Annotated[RunService, Depends(get_run_service)],
    target_kind: Annotated[RunTargetKind | None, Query(alias="targetKind")] = None,
    target_id: Annotated[int | None, Query(alias="targetId")] = None,
    target_key: Annotated[str | None, Query(alias="targetKey")] = None,
    target_version: Annotated[int | None, Query(alias="targetVersion")] = None,
    workflow_package_key: Annotated[str | None, Query(alias="workflowPackageKey")] = None,
    workflow_package_id: Annotated[int | None, Query(alias="workflowPackageId")] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
    model_connection_key: Annotated[str | None, Query(alias="modelConnectionKey")] = None,
    status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListRead:
    if target_kind is None and (
        target_id is not None or target_key is not None or target_version is not None
    ):
        raise validation_error(
            "Request validation failed",
            [
                {
                    "field": "targetKind",
                    "issue": (
                        "targetKind is required when targetId, targetKey, or "
                        "targetVersion is provided"
                    ),
                }
            ],
        )

    return service.list_runs(
        target_kind=target_kind,
        target_id=target_id,
        target_key=target_key,
        target_version=target_version,
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


@router.get("/{run_id}/step-replay-draft", response_model=RunStepReplayDraftRead)
def build_run_step_replay_draft(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
    step_index: Annotated[int, Query(alias="stepIndex", ge=1)],
) -> RunStepReplayDraftRead:
    return service.build_step_replay_draft(run_id, step_index)


@router.post(
    "/{run_id}/step-replays",
    response_model=RunCreatedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_run_step_replay(
    run_id: int,
    payload: RunStepReplayCreateRequest,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunCreatedRead:
    return service.create_step_replay(run_id, payload)


@router.get("/{run_id}", response_model=RunRead)
def get_run(
    run_id: int,
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunRead:
    return service.get_run(run_id)
