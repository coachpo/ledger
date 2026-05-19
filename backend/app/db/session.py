from __future__ import annotations

from app.db.engine import get_db_session, get_engine, get_session_factory, reset_db_caches
from app.db.upgrades import (
    build_unique_legacy_portfolio_slug,
    normalize_legacy_portfolio_slug,
    upgrade_legacy_schema,
)
from app.db.validation import (
    SupportsDialect,
    SupportsDialectName,
    validate_supported_database_engine,
    validate_supported_id_schema,
)
from app.models.base import Base

_OPTIONAL_PGVECTOR_TABLE_NAMES = frozenset({"agent_memory_embeddings"})


def init_db(database_url: str | None = None) -> None:
    """Initialize the startup-owned schema and compatibility repairs."""

    __import__("app.models")
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
    validate_supported_id_schema(engine)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table
            for table in Base.metadata.sorted_tables
            if table.name not in _OPTIONAL_PGVECTOR_TABLE_NAMES
        ],
    )
    upgrade_legacy_schema(engine)


__all__ = [
    "SupportsDialect",
    "SupportsDialectName",
    "build_unique_legacy_portfolio_slug",
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "init_db",
    "normalize_legacy_portfolio_slug",
    "reset_db_caches",
    "upgrade_legacy_schema",
    "validate_supported_database_engine",
    "validate_supported_id_schema",
]
