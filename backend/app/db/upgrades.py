from __future__ import annotations

import re

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.validation import validate_supported_database_engine

_OBSOLETE_TABLES = (
    "stock_analysis_versions",
    "stock_analysis_responses",
    "stock_analysis_requests",
    "stock_analysis_runs",
    "stock_analysis_conversations",
    "portfolio_stock_analysis_settings",
    "prompt_templates",
    "user_snippets",
    "llm_configs",
)
_LEGACY_SLUG_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_LEGACY_SLUG_DUPLICATE_UNDERSCORES_RE = re.compile(r"_+")


def normalize_legacy_portfolio_slug(name: str) -> str:
    normalized = _LEGACY_SLUG_INVALID_CHARS_RE.sub("_", name.strip().lower())
    normalized = _LEGACY_SLUG_DUPLICATE_UNDERSCORES_RE.sub("_", normalized).strip("_")
    if not normalized:
        normalized = "portfolio"
    if not normalized[0].isalpha():
        normalized = f"portfolio_{normalized}"
    return normalized


def build_unique_legacy_portfolio_slug(base_slug: str, used_slugs: set[str]) -> str:
    suffix = ""
    sequence = 2

    while True:
        max_base_length = 100 - len(suffix)
        trimmed_base = base_slug[:max_base_length].rstrip("_")
        if not trimmed_base:
            trimmed_base = "portfolio"[:max_base_length].rstrip("_") or "p"

        candidate = f"{trimmed_base}{suffix}"
        if candidate not in used_slugs:
            used_slugs.add(candidate)
            return candidate

        suffix = f"_{sequence}"
        sequence += 1


def upgrade_legacy_schema(engine: Engine) -> None:
    validate_supported_database_engine(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "portfolios" in table_names:
        portfolio_columns = {column["name"] for column in inspector.get_columns("portfolios")}
        if "slug" not in portfolio_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE portfolios ADD COLUMN slug VARCHAR(100)")
                legacy_portfolios = connection.exec_driver_sql(
                    "SELECT id, name FROM portfolios ORDER BY id"
                ).all()
                used_slugs: set[str] = set()
                for portfolio_id, name in legacy_portfolios:
                    connection.execute(
                        text("UPDATE portfolios SET slug = :slug WHERE id = :portfolio_id"),
                        {
                            "slug": build_unique_legacy_portfolio_slug(
                                normalize_legacy_portfolio_slug(name), used_slugs
                            ),
                            "portfolio_id": portfolio_id,
                        },
                    )
                connection.exec_driver_sql("ALTER TABLE portfolios ALTER COLUMN slug SET NOT NULL")
                connection.exec_driver_sql(
                    "ALTER TABLE portfolios ADD CONSTRAINT uq_portfolios_slug UNIQUE (slug)"
                )

    if "balances" in table_names:
        balance_columns = {column["name"] for column in inspector.get_columns("balances")}
        if "operation_type" not in balance_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE balances ADD COLUMN operation_type VARCHAR")
                connection.exec_driver_sql(
                    "UPDATE balances SET operation_type = 'DEPOSIT' WHERE operation_type IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE balances ALTER COLUMN operation_type SET NOT NULL"
                )

    if "trading_operations" in table_names:
        trading_operation_columns = {
            column["name"] for column in inspector.get_columns("trading_operations")
        }
        if "backtest_id" not in trading_operation_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE trading_operations "
                    "ADD COLUMN backtest_id INTEGER REFERENCES backtests(id) ON DELETE CASCADE"
                )

    if "reports" in table_names:
        report_columns = {column["name"] for column in inspector.get_columns("reports")}
        if "slug" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE reports ADD COLUMN slug VARCHAR(200)")
                connection.exec_driver_sql("UPDATE reports SET slug = name WHERE slug IS NULL")
                connection.exec_driver_sql("ALTER TABLE reports ALTER COLUMN slug SET NOT NULL")
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD CONSTRAINT uq_reports_slug UNIQUE (slug)"
                )
        if "source" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD COLUMN source VARCHAR(20) DEFAULT 'compiled' NOT NULL"
                )
        if "metadata" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD COLUMN metadata JSONB DEFAULT '{}' NOT NULL"
                )

    if "market_quotes" in table_names:
        market_quote_columns = {column["name"] for column in inspector.get_columns("market_quotes")}
        if "name" not in market_quote_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE market_quotes ADD COLUMN name VARCHAR(255)")

    obsolete_tables = [table_name for table_name in _OBSOLETE_TABLES if table_name in table_names]
    if not obsolete_tables:
        return

    with engine.begin() as connection:
        for table_name in obsolete_tables:
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
