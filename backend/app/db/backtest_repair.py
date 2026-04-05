from __future__ import annotations

from sqlalchemy import bindparam, inspect, text

from app.db.engine import get_engine

_INTERRUPTED_BACKTEST_MESSAGE = (
    "Process interrupted - backtest was running when the server restarted"
)


def mark_interrupted_backtests_failed(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "backtests" not in table_names:
        return

    backtest_columns = {column["name"] for column in inspector.get_columns("backtests")}
    if "status" not in backtest_columns:
        return

    interrupted_statuses = ("PENDING", "RUNNING", "AWAITING_CALLBACK", "PROCESSING_CALLBACK")
    parameters = [{"status": status} for status in interrupted_statuses]

    if "error_message" in backtest_columns:
        statement = text(
            """
            UPDATE backtests
            SET status = 'FAILED',
                error_message = :error_message
            WHERE status = :status
            """
        ).bindparams(bindparam("error_message"))
        parameters = [
            {"status": status, "error_message": _INTERRUPTED_BACKTEST_MESSAGE}
            for status in interrupted_statuses
        ]
    else:
        statement = text(
            """
            UPDATE backtests
            SET status = 'FAILED'
            WHERE status = :status
            """
        )
        parameters = [{"status": status} for status in interrupted_statuses]

    statement = statement.bindparams(bindparam("status"))

    with engine.begin() as connection:
        connection.execute(statement, parameters)
