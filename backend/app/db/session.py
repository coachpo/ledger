from __future__ import annotations

from app.db.engine import get_db_session, get_engine, get_session_factory, reset_db_caches
from app.db.upgrades import upgrade_legacy_schema as _upgrade_legacy_schema
from app.db.validation import (
    SupportsDialect,
    SupportsDialectName,
    validate_supported_database_engine,
    validate_supported_id_schema,
)
from app.models.base import Base, prune_retired_global_authoring_metadata


def init_db(database_url: str | None = None) -> None:
    """Initialize the startup-owned schema and startup repairs."""

    __import__("app.models")
    prune_retired_global_authoring_metadata()
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
    validate_supported_id_schema(engine)
    Base.metadata.create_all(bind=engine)
    _upgrade_legacy_schema(engine)


__all__ = [
    "SupportsDialect",
    "SupportsDialectName",
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "init_db",
    "reset_db_caches",
    "validate_supported_database_engine",
    "validate_supported_id_schema",
]
