from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.constants import CSV_IMPORT_MODE, PORTFOLIO_CURRENCY
from app.core.errors import malformed_file_error, validation_error
from app.core.formatting import normalize_symbol, parse_decimal_string
from app.extensions.signaldeck_finance.service_gate import (
    CSV_IMPORT_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.extensions.signaldeck_finance.services.portfolio_service import PortfolioService
from app.models.position import Position
from app.repositories.position import PositionRepository
from app.schemas.csv_import import CsvAcceptedRow, CsvCommitRead, CsvPreviewRead, CsvRowError

REQUIRED_HEADERS = {"symbol", "quantity", "average_cost"}
OPTIONAL_HEADERS = {"name"}
ALLOWED_HEADERS = REQUIRED_HEADERS | OPTIONAL_HEADERS


@dataclass(slots=True)
class ParsedCsvRow:
    row: int
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    name: str | None


class CsvImportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.position_repository = PositionRepository(session)
        self.portfolio_service = PortfolioService(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=CSV_IMPORT_SERVICE_SURFACE)

    def preview(
        self, portfolio_id: int, file_name: str, content_type: str | None, content: bytes
    ) -> CsvPreviewRead:
        self._require_enabled()
        self.portfolio_service.get_portfolio_model(portfolio_id)
        parsed_rows, errors = self._parse_file(
            file_name=file_name, content_type=content_type, content=content
        )
        return CsvPreviewRead(
            file_name=file_name,
            mode=CSV_IMPORT_MODE,
            accepted_rows=[self._to_accepted_row(row) for row in parsed_rows],
            errors=errors,
        )

    def commit(
        self, portfolio_id: int, file_name: str, content_type: str | None, content: bytes
    ) -> CsvCommitRead:
        self._require_enabled()
        portfolio = self.portfolio_service.get_portfolio_model(portfolio_id)
        parsed_rows, errors = self._parse_file(
            file_name=file_name, content_type=content_type, content=content
        )
        if errors:
            raise validation_error(
                "CSV validation failed",
                details=[error.model_dump(mode="json", by_alias=True) for error in errors],
            )

        inserted = 0
        updated = 0
        unchanged = 0

        try:
            for row in parsed_rows:
                existing = self.position_repository.get_by_symbol(portfolio_id, row.symbol)
                if existing is None:
                    position = Position(
                        portfolio_id=portfolio.id,
                        symbol=row.symbol,
                        name=row.name,
                        quantity=row.quantity,
                        average_cost=row.average_cost,
                        currency=PORTFOLIO_CURRENCY,
                        last_source="csv",
                    )
                    self.position_repository.add(position)
                    inserted += 1
                    continue

                if (
                    existing.name == row.name
                    and existing.quantity == row.quantity
                    and existing.average_cost == row.average_cost
                ):
                    unchanged += 1
                    existing.last_source = "csv"
                    existing.currency = PORTFOLIO_CURRENCY
                    continue

                existing.name = row.name
                existing.quantity = row.quantity
                existing.average_cost = row.average_cost
                existing.currency = PORTFOLIO_CURRENCY
                existing.last_source = "csv"
                updated += 1

            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return CsvCommitRead(
            file_name=file_name,
            mode=CSV_IMPORT_MODE,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            errors=[],
        )

    def _parse_file(
        self, *, file_name: str, content_type: str | None, content: bytes
    ) -> tuple[list[ParsedCsvRow], list[CsvRowError]]:
        self._validate_file_metadata(file_name=file_name, content_type=content_type)
        decoded = self._decode_content(content)
        reader = csv.DictReader(StringIO(decoded))
        raw_headers = reader.fieldnames or []
        if not raw_headers:
            raise malformed_file_error("CSV file is missing headers")

        header_map = {
            header.strip().lower(): header for header in raw_headers if header is not None
        }
        missing_headers = sorted(REQUIRED_HEADERS - set(header_map))
        if missing_headers:
            raise malformed_file_error(
                "CSV file is missing required headers",
                details=[
                    {
                        "field": "headers",
                        "issue": "Missing required headers",
                        "missing": missing_headers,
                    }
                ],
            )
        unexpected_headers = sorted(set(header_map) - ALLOWED_HEADERS)
        if unexpected_headers:
            raise malformed_file_error(
                "CSV file contains unsupported headers",
                details=[
                    {
                        "field": "headers",
                        "issue": "Unsupported headers",
                        "unexpected": unexpected_headers,
                    }
                ],
            )

        parsed_rows: list[ParsedCsvRow] = []
        errors: list[CsvRowError] = []
        seen_symbols: set[str] = set()

        for row_number, record in enumerate(reader, start=2):
            normalized_record = {
                key.strip().lower(): (value.strip() if isinstance(value, str) else value)
                for key, value in record.items()
                if key is not None
            }
            if not any(value for value in normalized_record.values() if value is not None):
                continue
            row_errors, parsed_row = self._parse_row(row_number, normalized_record, seen_symbols)
            errors.extend(row_errors)
            if parsed_row is not None:
                parsed_rows.append(parsed_row)

        return parsed_rows, errors

    def _parse_row(
        self,
        row_number: int,
        record: dict[str, str | None],
        seen_symbols: set[str],
    ) -> tuple[list[CsvRowError], ParsedCsvRow | None]:
        errors: list[CsvRowError] = []
        symbol = normalize_symbol(record.get("symbol") or "")
        if not symbol:
            errors.append(CsvRowError(row=row_number, field="symbol", issue="Symbol is required"))
        elif symbol in seen_symbols:
            errors.append(
                CsvRowError(row=row_number, field="symbol", issue="Duplicate symbol in file")
            )

        quantity = self._parse_decimal(record.get("quantity"), row_number, "quantity", errors)
        average_cost = self._parse_decimal(
            record.get("average_cost"), row_number, "average_cost", errors, allow_zero=True
        )
        name = (record.get("name") or "").strip() or None

        if errors:
            return errors, None

        seen_symbols.add(symbol)
        return (
            errors,
            ParsedCsvRow(
                row=row_number,
                symbol=symbol,
                quantity=quantity,
                average_cost=average_cost,
                name=name,
            ),
        )

    def _parse_decimal(
        self,
        value: str | None,
        row_number: int,
        field_name: str,
        errors: list[CsvRowError],
        *,
        allow_zero: bool = False,
    ) -> Decimal:
        try:
            parsed = parse_decimal_string(value or "")
        except ValueError:
            errors.append(
                CsvRowError(row=row_number, field=field_name, issue="Invalid decimal value")
            )
            return Decimal("0")
        if (allow_zero and parsed < 0) or (not allow_zero and parsed <= 0):
            errors.append(
                CsvRowError(
                    row=row_number,
                    field=field_name,
                    issue=(
                        "Must be greater than or equal to zero"
                        if allow_zero
                        else "Must be greater than zero"
                    ),
                )
            )
        return parsed

    def _validate_file_metadata(self, *, file_name: str, content_type: str | None) -> None:
        has_csv_extension = Path(file_name).suffix.lower() == ".csv"
        has_csv_mime = content_type == "text/csv"
        if not has_csv_extension and not has_csv_mime:
            raise malformed_file_error("Invalid CSV file type")

    def _decode_content(self, content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise malformed_file_error("CSV file must be valid UTF-8 text") from exc

    def _to_accepted_row(self, row: ParsedCsvRow) -> CsvAcceptedRow:
        return CsvAcceptedRow(
            row=row.row,
            symbol=row.symbol,
            quantity=row.quantity,
            average_cost=row.average_cost,
            name=row.name,
        )
