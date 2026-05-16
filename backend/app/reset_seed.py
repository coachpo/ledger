from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings, reset_settings_cache
from app.db.session import get_engine, init_db, reset_db_caches

# Retained only for upgrade/startup sanitation of retired stock-analysis resources.
STARTER_PORTFOLIO_SLUG = "mag7_core"
STARTER_WORKFLOW_KEY = "stock_analysis"
STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS = (
    "financials_analyst",
    "news_analyst",
    "market_analyst",
    "industry_analyst",
    "economy_analyst",
    "price_analyst",
    "position_reader",
    "history_reader",
)
STOCK_ANALYSIS_SYNTHESIZER_KEY = "decision_synthesizer"
STOCK_ANALYSIS_NOTE_SCHEMA_KEY = "stock_analysis_note"
TRADING_DECISION_SCHEMA_KEY = "trading_decision"
STOCK_ANALYSIS_CAPABILITY_KEY = "stock_analysis_tools"
STOCK_ANALYSIS_MCP_SERVER_KEY = "stock_analysis_data"
STARTER_TEMPLATE_NAMES = (
    "Mag7 Portfolio Snapshot",
    "Mag7 Ticker Review",
)
MAG7_COMPANIES = (
    {"symbol": "AAPL", "reportSlug": "aapl_seed_report", "reportTag": "aapl_loop"},
    {"symbol": "MSFT", "reportSlug": "msft_seed_report", "reportTag": "msft_loop"},
    {"symbol": "NVDA", "reportSlug": "nvda_seed_report", "reportTag": "nvda_loop"},
    {"symbol": "AMZN", "reportSlug": "amzn_seed_report", "reportTag": "amzn_loop"},
    {"symbol": "GOOGL", "reportSlug": "googl_seed_report", "reportTag": "googl_loop"},
    {"symbol": "META", "reportSlug": "meta_seed_report", "reportTag": "meta_loop"},
    {"symbol": "TSLA", "reportSlug": "tsla_seed_report", "reportTag": "tsla_loop"},
)


@dataclass(frozen=True)
class ResetSeedSummary:
    portfolio_slugs: tuple[str, ...]
    template_names: tuple[str, ...]
    output_schema_keys: tuple[str, ...]
    capability_keys: tuple[str, ...]
    mcp_server_keys: tuple[str, ...]
    agent_keys: tuple[str, ...]
    report_slugs: tuple[str, ...]
    workflow_keys: tuple[str, ...]


def _resolve_database_url(database_url: str | None) -> str:
    return database_url or get_settings().database_url


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _validate_target_database(database_url: str) -> URL:
    target_url = make_url(database_url)
    if target_url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("Reset-and-seed requires a PostgreSQL database URL.")
    if not target_url.database or target_url.database == "postgres":
        raise RuntimeError("Refusing to wipe the admin postgres database.")
    return target_url


def recreate_database(database_url: str) -> None:
    target_url = _validate_target_database(database_url)
    admin_url = target_url.set(database="postgres")
    database_name = target_url.database or ""

    try:
        get_engine(database_url).dispose()
    finally:
        reset_db_caches()
        reset_settings_cache()

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_name)} WITH (FORCE)")
            )
            connection.execute(text(f"CREATE DATABASE {_quote_identifier(database_name)}"))
    finally:
        admin_engine.dispose()
        reset_db_caches()
        reset_settings_cache()


def seed_initial_data(database_url: str | None = None) -> ResetSeedSummary:
    del database_url
    return ResetSeedSummary(
        portfolio_slugs=(),
        template_names=(),
        output_schema_keys=(),
        capability_keys=(),
        mcp_server_keys=(),
        agent_keys=(),
        report_slugs=(),
        workflow_keys=(),
    )


def reset_and_seed_database(database_url: str | None = None) -> ResetSeedSummary:
    resolved_database_url = _resolve_database_url(database_url)
    recreate_database(resolved_database_url)
    init_db(resolved_database_url)
    return seed_initial_data(resolved_database_url)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset the SignalDeck application database and keep a clean empty workspace."
    )
    parser.add_argument("--database-url", default=None, help="Explicit PostgreSQL database URL.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for the destructive reset.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if not args.yes:
        raise SystemExit("Refusing to wipe the database without --yes.")

    summary = reset_and_seed_database(args.database_url)
    print("Reset complete.")
    print(f"Portfolios: {', '.join(summary.portfolio_slugs)}")
    print(f"Templates: {', '.join(summary.template_names)}")
    print(f"Reports: {', '.join(summary.report_slugs)}")
    print(f"Workflows: {', '.join(summary.workflow_keys)}")
    print(f"Output schemas: {', '.join(summary.output_schema_keys)}")
    print(f"Capabilities: {', '.join(summary.capability_keys)}")
    print(f"MCP servers: {', '.join(summary.mcp_server_keys)}")
    print(f"Agents: {', '.join(summary.agent_keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
