from __future__ import annotations

from typing import Protocol

_POSTGRES_DIALECTS = {"postgresql", "postgres"}


class SupportsDialect(Protocol):
    @property
    def dialect(self) -> SupportsDialectName: ...


class SupportsDialectName(Protocol):
    name: str


def validate_supported_database_engine(engine: SupportsDialect) -> None:
    if engine.dialect.name in _POSTGRES_DIALECTS:
        return

    raise RuntimeError(
        f"Unsupported database engine: {engine.dialect.name}. This application requires PostgreSQL."
    )
