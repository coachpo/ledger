from __future__ import annotations

from sqlalchemy.engine import Engine

_POSTGRES_DIALECTS = {"postgresql", "postgres"}


def validate_supported_database_engine(engine: Engine) -> None:
    if engine.dialect.name in _POSTGRES_DIALECTS:
        return

    raise RuntimeError(
        f"Unsupported database engine: {engine.dialect.name}. This application requires PostgreSQL."
    )
