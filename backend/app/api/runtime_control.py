from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_runtime_control_service
from app.schemas.runtime import RuntimeControlFlagRead, RuntimeControlFlagUpdateRequest
from app.services.runtime_control_service import RuntimeControlService

router = APIRouter(prefix="/runtime/control", tags=["runtime-control"])


@router.get("/flags/{flag_key}", response_model=RuntimeControlFlagRead)
def get_runtime_control_flag(
    flag_key: str,
    service: Annotated[RuntimeControlService, Depends(get_runtime_control_service)],
) -> RuntimeControlFlagRead:
    return service.get_flag(flag_key)


@router.patch("/flags/{flag_key}", response_model=RuntimeControlFlagRead)
def update_runtime_control_flag(
    flag_key: str,
    payload: RuntimeControlFlagUpdateRequest,
    service: Annotated[RuntimeControlService, Depends(get_runtime_control_service)],
) -> RuntimeControlFlagRead:
    return service.set_flag(
        flag_key=flag_key,
        enabled=payload.enabled,
        actor=payload.actor,
        reason=payload.reason,
    )
