from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.engine import get_db_session, get_engine, get_session_factory, reset_db_caches
from app.db.seed import seed_preset_packages
from app.db.startup_recovery import fail_inflight_runs
from app.db.validation import (
    SupportsDialect,
    SupportsDialectName,
    validate_supported_database_engine,
)
from app.models.base import Base

_INIT_DB_ADVISORY_LOCK_KEY = 772114523790049232


@contextmanager
def _init_db_lock(engine: Engine) -> Iterator[None]:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_key)"),
            {"lock_key": _INIT_DB_ADVISORY_LOCK_KEY},
        )
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": _INIT_DB_ADVISORY_LOCK_KEY},
            )


def init_db(database_url: str | None = None) -> None:
    """Initialize the startup-owned schema and startup repairs."""

    __import__("app.models")
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
    with _init_db_lock(engine):
        Base.metadata.create_all(bind=engine)
        seed_preset_packages(engine)
        fail_inflight_runs(engine)


__all__ = [
    "SupportsDialect",
    "SupportsDialectName",
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "init_db",
    "reset_db_caches",
    "validate_supported_database_engine",
]
