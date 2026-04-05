from __future__ import annotations

from app.db.backtest_repair import mark_interrupted_backtests_failed
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


def init_db(database_url: str | None = None) -> None:
    __import__("app.models")
    engine = get_engine(database_url)
    validate_supported_database_engine(engine)
    validate_supported_id_schema(engine)
    Base.metadata.create_all(bind=engine)
    upgrade_legacy_schema(engine)
    mark_interrupted_backtests_failed(database_url)


__all__ = [
    "SupportsDialect",
    "SupportsDialectName",
    "build_unique_legacy_portfolio_slug",
    "get_db_session",
    "get_engine",
    "get_session_factory",
    "init_db",
    "mark_interrupted_backtests_failed",
    "normalize_legacy_portfolio_slug",
    "reset_db_caches",
    "upgrade_legacy_schema",
    "validate_supported_database_engine",
    "validate_supported_id_schema",
]
