from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import inspect, text

from app.core.formatting import utcnow
from app.db.engine import get_engine
from app.schemas.runtime import ApprovalSummary, TraceSummary

_INTERRUPTED_BACKTEST_MESSAGE = (
    "Process interrupted - backtest was running when the server restarted"
)
_INTERRUPTED_RUNTIME_RUN_MESSAGE = (
    "Process interrupted - runtime run was active when the server restarted"
)
_INTERRUPTED_RUNTIME_APPROVAL_REASON = (
    "Approval expired because the server restarted before the run could resume"
)
_INTERRUPTED_BACKTEST_STATUSES = (
    "PENDING",
    "RUNNING",
    "AWAITING_CALLBACK",
    "PROCESSING_CALLBACK",
)
_ACTIVE_RUNTIME_RUN_STATUSES = {"QUEUED", "RUNNING"}
_RESUMABLE_RUNTIME_RUN_STATUS = "WAITING_APPROVAL"
_RUNTIME_V2_EXECUTION_OWNER = "runtime_v2"
_RUNTIME_RESTART_ERROR_CODE = "server_restart_repair"


def mark_interrupted_backtests_failed(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "backtests" not in table_names:
        return

    backtest_columns = {column["name"] for column in inspector.get_columns("backtests")}
    if "status" not in backtest_columns:
        return

    runtime_aware = {
        "execution_owner",
        "current_run_id",
    } <= backtest_columns and {
        "runtime_runs",
        "runtime_run_artifacts",
        "runtime_approvals",
        "runtime_trace_events",
    } <= table_names

    with engine.begin() as connection:
        interrupted_backtests = connection.execute(
            text(
                "SELECT id, status"
                + (", execution_owner, current_run_id" if runtime_aware else "")
                + " FROM backtests "
                + (
                    "WHERE status IN ("
                    "'PENDING', 'RUNNING', 'AWAITING_CALLBACK', 'PROCESSING_CALLBACK'"
                    ") ORDER BY id"
                )
            )
        ).mappings()

        legacy_backtest_ids: list[int] = []
        for row in interrupted_backtests:
            backtest_id = int(row["id"])
            if not runtime_aware or row.get("execution_owner") != _RUNTIME_V2_EXECUTION_OWNER:
                legacy_backtest_ids.append(backtest_id)
                continue

            _repair_runtime_owned_backtest(
                connection,
                backtest_id=backtest_id,
                backtest_status=str(row["status"]),
                current_run_id=_coerce_optional_int(row.get("current_run_id")),
                backtest_columns=backtest_columns,
            )

        if legacy_backtest_ids:
            _mark_backtests_failed_by_id(
                connection,
                backtest_ids=legacy_backtest_ids,
                backtest_columns=backtest_columns,
                error_message=_INTERRUPTED_BACKTEST_MESSAGE,
                clear_current_run=True,
            )


def _repair_runtime_owned_backtest(
    connection: Any,
    *,
    backtest_id: int,
    backtest_status: str,
    current_run_id: int | None,
    backtest_columns: set[str],
) -> None:
    if current_run_id is None:
        if backtest_status in {"PENDING", "RUNNING"}:
            _mark_backtests_failed_by_id(
                connection,
                backtest_ids=[backtest_id],
                backtest_columns=backtest_columns,
                error_message=_INTERRUPTED_BACKTEST_MESSAGE,
                clear_current_run=True,
                current_cycle_status="FAILED",
            )
        return

    runtime_run = (
        connection.execute(
            text("SELECT id, status FROM runtime_runs WHERE id = :run_id"),
            {"run_id": current_run_id},
        )
        .mappings()
        .first()
    )
    if runtime_run is None:
        _clear_backtest_current_run(
            connection, backtest_id=backtest_id, backtest_columns=backtest_columns
        )
        return

    run_status = str(runtime_run["status"])
    if run_status == _RESUMABLE_RUNTIME_RUN_STATUS:
        return
    if run_status in _ACTIVE_RUNTIME_RUN_STATUSES:
        repaired_at = utcnow()
        _mark_runtime_run_failed(
            connection,
            run_id=current_run_id,
            repaired_at=repaired_at,
        )
        _mark_backtests_failed_by_id(
            connection,
            backtest_ids=[backtest_id],
            backtest_columns=backtest_columns,
            error_message=_INTERRUPTED_BACKTEST_MESSAGE,
            clear_current_run=True,
            current_cycle_status="FAILED",
            updated_at=repaired_at,
        )
        return

    _mark_backtests_failed_by_id(
        connection,
        backtest_ids=[backtest_id],
        backtest_columns=backtest_columns,
        error_message=_INTERRUPTED_BACKTEST_MESSAGE,
        clear_current_run=True,
        current_cycle_status="FAILED",
    )


def _mark_runtime_run_failed(connection: Any, *, run_id: int, repaired_at: datetime) -> None:
    connection.execute(
        text(
            "UPDATE runtime_runs SET status = 'FAILED', updated_at = :updated_at WHERE id = :run_id"
        ),
        {"run_id": run_id, "updated_at": repaired_at},
    )
    connection.execute(
        text(
            "UPDATE runtime_run_artifacts "
            "SET terminal_error_code = :terminal_error_code, "
            "terminal_error_message = :terminal_error_message "
            "WHERE run_id = :run_id"
        ),
        {
            "run_id": run_id,
            "terminal_error_code": _RUNTIME_RESTART_ERROR_CODE,
            "terminal_error_message": _INTERRUPTED_RUNTIME_RUN_MESSAGE,
        },
    )
    connection.execute(
        text(
            "UPDATE runtime_approvals "
            "SET status = 'EXPIRED', reason = :reason, resolved_at = :resolved_at "
            "WHERE run_id = :run_id AND status = 'PENDING'"
        ),
        {
            "run_id": run_id,
            "reason": _INTERRUPTED_RUNTIME_APPROVAL_REASON,
            "resolved_at": repaired_at,
        },
    )

    latest_event_index = connection.execute(
        text(
            "SELECT COALESCE(MAX(event_index), -1) FROM runtime_trace_events WHERE run_id = :run_id"
        ),
        {"run_id": run_id},
    ).scalar_one()
    connection.execute(
        text(
            "INSERT INTO runtime_trace_events "
            "(run_id, event_index, event_type, payload, created_at) "
            "VALUES ("
            ":run_id, :event_index, 'RUN_FAILED', CAST(:payload AS JSONB), :created_at"
            ")"
        ),
        {
            "run_id": run_id,
            "event_index": int(latest_event_index) + 1,
            "payload": json.dumps(
                {
                    "code": _RUNTIME_RESTART_ERROR_CODE,
                    "message": _INTERRUPTED_RUNTIME_RUN_MESSAGE,
                    "source": "startup_repair",
                }
            ),
            "created_at": repaired_at,
        },
    )
    _refresh_runtime_run_summaries(connection, run_id=run_id, updated_at=repaired_at)


def _refresh_runtime_run_summaries(
    connection: Any,
    *,
    run_id: int,
    updated_at: datetime,
) -> None:
    trace_row = (
        connection.execute(
            text(
                "SELECT "
                "COUNT(*) AS event_count, "
                "COUNT(*) FILTER (WHERE event_type = 'TOOL_CALLED') AS tool_call_count, "
                "COUNT(*) FILTER (WHERE event_type = 'WARNING_EMITTED') AS warning_count, "
                "MAX(created_at) AS last_event_at "
                "FROM runtime_trace_events WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        .mappings()
        .one()
    )
    approval_rows = connection.execute(
        text(
            "SELECT status, COUNT(*) AS item_count "
            "FROM runtime_approvals WHERE run_id = :run_id GROUP BY status"
        ),
        {"run_id": run_id},
    ).mappings()

    approval_counts = {str(row["status"]): int(row["item_count"]) for row in approval_rows}
    trace_summary = TraceSummary(
        event_count=int(trace_row["event_count"] or 0),
        tool_call_count=int(trace_row["tool_call_count"] or 0),
        warning_count=int(trace_row["warning_count"] or 0),
        last_event_at=trace_row["last_event_at"],
    ).model_dump(by_alias=True, mode="json")
    approval_summary = ApprovalSummary(
        total_count=sum(approval_counts.values()),
        pending_count=approval_counts.get("PENDING", 0),
        approved_count=approval_counts.get("APPROVED", 0),
        denied_count=approval_counts.get("DENIED", 0),
        expired_count=approval_counts.get("EXPIRED", 0),
    ).model_dump(by_alias=True, mode="json")

    connection.execute(
        text(
            "UPDATE runtime_runs "
            "SET trace_summary = CAST(:trace_summary AS JSONB), "
            "approval_summary = CAST(:approval_summary AS JSONB), "
            "updated_at = :updated_at "
            "WHERE id = :run_id"
        ),
        {
            "run_id": run_id,
            "trace_summary": json.dumps(trace_summary),
            "approval_summary": json.dumps(approval_summary),
            "updated_at": updated_at,
        },
    )


def _mark_backtests_failed_by_id(
    connection: Any,
    *,
    backtest_ids: list[int],
    backtest_columns: set[str],
    error_message: str,
    clear_current_run: bool,
    current_cycle_status: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    if not backtest_ids:
        return

    assignments = ["status = 'FAILED'"]
    parameters: list[dict[str, Any]] = []
    if "error_message" in backtest_columns:
        assignments.append("error_message = :error_message")
    if clear_current_run and "current_run_id" in backtest_columns:
        assignments.append("current_run_id = NULL")
    if "current_cycle_status" in backtest_columns:
        if current_cycle_status is None:
            assignments.append("current_cycle_status = NULL")
        else:
            assignments.append("current_cycle_status = :current_cycle_status")
    if "updated_at" in backtest_columns:
        assignments.append("updated_at = :updated_at")

    statement = text(f"UPDATE backtests SET {', '.join(assignments)} WHERE id = :backtest_id")
    effective_updated_at = updated_at or utcnow()
    for backtest_id in backtest_ids:
        params: dict[str, Any] = {"backtest_id": backtest_id}
        if "error_message" in backtest_columns:
            params["error_message"] = error_message
        if "current_cycle_status" in backtest_columns and current_cycle_status is not None:
            params["current_cycle_status"] = current_cycle_status
        if "updated_at" in backtest_columns:
            params["updated_at"] = effective_updated_at
        parameters.append(params)
    connection.execute(statement, parameters)


def _clear_backtest_current_run(
    connection: Any,
    *,
    backtest_id: int,
    backtest_columns: set[str],
) -> None:
    if "current_run_id" not in backtest_columns:
        return

    assignments = ["current_run_id = NULL"]
    if "current_cycle_status" in backtest_columns:
        assignments.append("current_cycle_status = NULL")
    if "updated_at" in backtest_columns:
        assignments.append("updated_at = :updated_at")

    params: dict[str, Any] = {"backtest_id": backtest_id}
    if "updated_at" in backtest_columns:
        params["updated_at"] = utcnow()

    connection.execute(
        text(f"UPDATE backtests SET {', '.join(assignments)} WHERE id = :backtest_id"),
        params,
    )


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Unsupported current_run_id value: {value!r}")
