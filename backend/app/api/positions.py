from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.extensions.signaldeck_finance.dependencies import (
    CsvImportServiceDependency,
    PositionServiceDependency,
)
from app.schemas.csv_import import CsvCommitRead, CsvPreviewRead
from app.schemas.position import (
    PositionCreate,
    PositionRead,
    PositionSymbolLookupRead,
    PositionUpdate,
)

router = APIRouter(prefix="/portfolios/{portfolio_id}/positions", tags=["positions"])


@router.get("", response_model=list[PositionRead])
def list_positions(
    portfolio_id: int,
    service: PositionServiceDependency,
) -> list[PositionRead]:
    return service.list_positions(portfolio_id)


@router.post("", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
def create_position(
    portfolio_id: int,
    payload: PositionCreate,
    service: PositionServiceDependency,
) -> PositionRead:
    return service.create_position(portfolio_id, payload)


@router.get("/lookup", response_model=PositionSymbolLookupRead)
def lookup_position_symbol(
    portfolio_id: int,
    symbol: Annotated[str, Query(..., min_length=1)],
    service: PositionServiceDependency,
) -> PositionSymbolLookupRead:
    return service.lookup_symbol(portfolio_id, symbol)


@router.patch("/{position_id}", response_model=PositionRead)
def update_position(
    portfolio_id: int,
    position_id: int,
    payload: PositionUpdate,
    service: PositionServiceDependency,
) -> PositionRead:
    return service.update_position(portfolio_id, position_id, payload)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(
    portfolio_id: int,
    position_id: int,
    service: PositionServiceDependency,
) -> Response:
    service.delete_position(portfolio_id, position_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/imports/preview", response_model=CsvPreviewRead)
async def preview_position_import(
    portfolio_id: int,
    file: Annotated[UploadFile, File(...)],
    service: CsvImportServiceDependency,
) -> CsvPreviewRead:
    content = await file.read()
    return service.preview(
        portfolio_id, file.filename or "positions.csv", file.content_type, content
    )


@router.post("/imports/commit", response_model=CsvCommitRead)
async def commit_position_import(
    portfolio_id: int,
    file: Annotated[UploadFile, File(...)],
    service: CsvImportServiceDependency,
) -> CsvCommitRead:
    content = await file.read()
    return service.commit(
        portfolio_id, file.filename or "positions.csv", file.content_type, content
    )
