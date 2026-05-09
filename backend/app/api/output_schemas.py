from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_output_schema_service
from app.schemas.output_schema import (
    OutputSchemaDraftCreate,
    OutputSchemaDraftUpdate,
    OutputSchemaKind,
    OutputSchemaListRead,
    OutputSchemaRead,
    OutputSchemaStatus,
)
from app.services.output_schema_service import OutputSchemaService

router = APIRouter(prefix="/output-schemas", tags=["output-schemas"])


@router.get("", response_model=OutputSchemaListRead)
def list_output_schemas(
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
    status_filter: Annotated[OutputSchemaStatus | None, Query(alias="status")] = None,
    kind: Annotated[OutputSchemaKind | None, Query()] = None,
) -> OutputSchemaListRead:
    return service.list_schemas(status_filter=status_filter, kind=kind)


@router.post("", response_model=OutputSchemaRead, status_code=status.HTTP_201_CREATED)
def create_output_schema_draft(
    payload: OutputSchemaDraftCreate,
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
) -> OutputSchemaRead:
    return service.create_draft(payload)


@router.get("/{schema_id}", response_model=OutputSchemaRead)
def get_output_schema(
    schema_id: int,
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
) -> OutputSchemaRead:
    return service.get_schema(schema_id)


@router.patch("/{schema_id}", response_model=OutputSchemaRead)
def update_output_schema_draft(
    schema_id: int,
    payload: OutputSchemaDraftUpdate,
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
) -> OutputSchemaRead:
    return service.update_draft(schema_id, payload)


@router.post("/{schema_id}/activate", response_model=OutputSchemaRead)
def activate_output_schema(
    schema_id: int,
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
) -> OutputSchemaRead:
    return service.activate(schema_id)


@router.delete("/{schema_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_output_schema(
    schema_id: int,
    service: Annotated[OutputSchemaService, Depends(get_output_schema_service)],
) -> Response:
    service.delete_schema(schema_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
