from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_model_connection_service
from app.schemas.model_connection import (
    ModelConnectionConnectionTestRead,
    ModelConnectionCreate,
    ModelConnectionListRead,
    ModelConnectionRead,
    ModelConnectionStatus,
    ModelConnectionUpdate,
)
from app.services.model_connection_service import ModelConnectionService

router = APIRouter(prefix="/model-connections", tags=["model-connections"])


@router.get("", response_model=ModelConnectionListRead)
def list_model_connections(
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
    status_filter: Annotated[ModelConnectionStatus | None, Query(alias="status")] = None,
) -> ModelConnectionListRead:
    return service.list_connections(status_filter=status_filter)


@router.post("", response_model=ModelConnectionRead, status_code=status.HTTP_201_CREATED)
def create_model_connection(
    payload: ModelConnectionCreate,
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
) -> ModelConnectionRead:
    return service.create_connection(payload)


@router.get("/{connection_id}", response_model=ModelConnectionRead)
def get_model_connection(
    connection_id: int,
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
) -> ModelConnectionRead:
    return service.get_connection(connection_id)


@router.patch("/{connection_id}", response_model=ModelConnectionRead)
def update_model_connection(
    connection_id: int,
    payload: ModelConnectionUpdate,
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
) -> ModelConnectionRead:
    return service.update_connection(connection_id, payload)


@router.post("/{connection_id}/connection-test", response_model=ModelConnectionConnectionTestRead)
def test_model_connection(
    connection_id: int,
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
) -> ModelConnectionConnectionTestRead:
    return service.test_connection(connection_id)


@router.delete("/{connection_id}", response_model=ModelConnectionRead)
def archive_model_connection(
    connection_id: int,
    service: Annotated[ModelConnectionService, Depends(get_model_connection_service)],
) -> ModelConnectionRead:
    return service.archive_connection(connection_id)
