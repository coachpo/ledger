from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Connection, Engine

_BUNDLED_PACKAGE_PRESET_SQL_FILES = (
    "tradingagents_advisory_research.sql",
    "digital_oracle_researcher.sql",
)


def _preset_package_sql_path(sql_file: str) -> Path:
    return Path(__file__).with_name(sql_file)


def _insert_bundled_package_preset(connection: Connection, preset_sql_path: Path) -> None:
    connection.exec_driver_sql(preset_sql_path.read_text(encoding="utf-8"))


def seed_preset_packages(engine: Engine) -> None:
    with engine.begin() as connection:
        # Bundled preset SQL uses ON CONFLICT DO UPDATE; these packages are
        # managed/read-only and restart seeding can overwrite same-key edits.
        for sql_file in _BUNDLED_PACKAGE_PRESET_SQL_FILES:
            _insert_bundled_package_preset(connection, _preset_package_sql_path(sql_file))


__all__ = ["seed_preset_packages"]
