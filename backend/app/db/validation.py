from __future__ import annotations

from typing import Protocol

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

_POSTGRES_DIALECTS = {"postgresql", "postgres"}


class SupportsDialect(Protocol):
    @property
    def dialect(self) -> SupportsDialectName: ...


class SupportsDialectName(Protocol):
    name: str


def validate_supported_id_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "portfolios" not in table_names:
        return

    id_column = next(
        (column for column in inspector.get_columns("portfolios") if column["name"] == "id"),
        None,
    )
    if id_column is None:
        return

    normalized_type = str(id_column["type"]).upper()
    if "INT" in normalized_type:
        return

    raise RuntimeError(
        "Legacy UUID-backed database detected. This version requires numeric ids. "
        "Create a fresh database or migrate the existing one before starting the app."
    )


def validate_supported_database_engine(engine: SupportsDialect) -> None:
    if engine.dialect.name in _POSTGRES_DIALECTS:
        return

    raise RuntimeError(
        f"Unsupported database engine: {engine.dialect.name}. This application requires PostgreSQL."
    )
