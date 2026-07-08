from __future__ import annotations

from app.db.engine import get_db_session, get_engine, get_session_factory, reset_db_caches
from app.db.seed import seed_preset_packages
from app.db.startup_recovery import fail_inflight_runs
from app.db.validation import (
    SupportsDialect,
    SupportsDialectName,
    validate_supported_database_engine,
)
from app.models.base import Base


def init_db(database_url: str | None = None) -> None:
    """Initialize the startup-owned schema and startup repairs."""

    __import__("app.models")
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
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
