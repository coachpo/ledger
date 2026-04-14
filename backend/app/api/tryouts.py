from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_tryout_service
from app.schemas.runtime import RuntimeRunCreated
from app.schemas.tryout import TryoutExecute, TryoutPersistRead, TryoutRead
from app.services.tryout_service import TryoutService

router = APIRouter(prefix="/tryouts", tags=["tryouts"])


@router.post("", response_model=RuntimeRunCreated, status_code=status.HTTP_201_CREATED)
def create_tryout(
    payload: TryoutExecute,
    service: Annotated[TryoutService, Depends(get_tryout_service)],
) -> RuntimeRunCreated:
    return service.create_tryout(payload)


@router.get("/{run_id}", response_model=TryoutRead)
def get_tryout(
    run_id: int,
    service: Annotated[TryoutService, Depends(get_tryout_service)],
) -> TryoutRead:
    return service.get_tryout(run_id)


@router.post("/{run_id}/persist", response_model=TryoutPersistRead)
def persist_tryout(
    run_id: int,
    service: Annotated[TryoutService, Depends(get_tryout_service)],
) -> TryoutPersistRead:
    return service.persist_tryout(run_id)
