from __future__ import annotations

from decimal import Decimal

from app.core.constants import CSV_IMPORT_MODE
from app.schemas.common import CamelModel


class CsvAcceptedRow(CamelModel):
    row: int
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    name: str | None = None


class CsvRowError(CamelModel):
    row: int
    field: str
    issue: str


class CsvPreviewRead(CamelModel):
    file_name: str
    mode: str = CSV_IMPORT_MODE
    accepted_rows: list[CsvAcceptedRow]
    errors: list[CsvRowError]


class CsvCommitRead(CamelModel):
    file_name: str
    mode: str = CSV_IMPORT_MODE
    inserted: int
    updated: int
    unchanged: int
    errors: list[CsvRowError]
