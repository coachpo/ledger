from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_run_service
from app.core.errors import validation_error
from app.schemas.run import RunListRead, RunRead, RunStatus, RunTargetKind
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListRead)
def list_runs(
    service: Annotated[RunService, Depends(get_run_service)],
    target_kind: Annotated[RunTargetKind | None, Query(alias="targetKind")] = None,
    target_id: Annotated[int | None, Query(alias="targetId")] = None,
    target_key: Annotated[str | None, Query(alias="targetKey")] = None,
    target_version: Annotated[int | None, Query(alias="targetVersion")] = None,
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
