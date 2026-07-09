# ponytail: no migration framework - schema changes require DB reset; adopt Alembic when data must survive.
# ruff: noqa: E501
from __future__ import annotations

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import BindParameter

_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE = (
    "Run marked as failed during startup recovery because the previous process exited while "
    "it was still running."
)
_AGENT_PLATFORM_PENDING_SKIP_MESSAGE = (
    "Runtime row skipped during startup recovery because the parent run failed before it started."
)
_STALE_RUNNING_RUN_PREDICATE = """
status = 'running'
AND (
    lease_owner IS NULL
    OR lease_expires_at IS NULL
    OR lease_expires_at < NOW()
)
"""


def fail_inflight_runs(engine: Engine) -> int:
    table_names = set(inspect(engine).get_table_names())
    if "runs" not in table_names:
        return 0

    with engine.begin() as connection:
        recovered_run_ids = list(
            connection.execute(
                text("SELECT id FROM runs WHERE " + _STALE_RUNNING_RUN_PREDICATE)
            ).scalars()
        )
        if not recovered_run_ids:
            return 0
        run_ids_param: BindParameter[object] = bindparam("run_ids", expanding=True)
        run_result = connection.execute(
            text(
                """
                UPDATE runs
                SET status = 'failed',
                    error = COALESCE(NULLIF(error, ''), :restart_failure_message),
                    finished_at = COALESCE(finished_at, NOW()),
                    updated_at = NOW()
                WHERE id IN :run_ids
                """
            ).bindparams(run_ids_param),
            {
                "restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE,
                "run_ids": recovered_run_ids,
            },
        )
        if "run_steps" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_steps AS step
                    SET status = 'failed',
                        error = COALESCE(NULLIF(step.error, ''), :restart_failure_message),
                        finished_at = COALESCE(step.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE step.run_id IN :run_ids
                      AND step.status = 'running'
                    """
                ).bindparams(run_ids_param),
                {
                    "restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE run_steps AS step
                    SET status = 'skipped',
                        error = COALESCE(NULLIF(step.error, ''), :pending_skip_message),
                        finished_at = COALESCE(step.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE step.run_id IN :run_ids
                      AND step.status = 'pending'
                    """
                ).bindparams(run_ids_param),
                {
                    "pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
        if "run_agent_invocations" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_agent_invocations AS invocation
                    SET status = 'failed',
                        error_code = COALESCE(
                            NULLIF(invocation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(invocation.error_message, ''),
                            :restart_failure_message
                        ),
                        finished_at = COALESCE(invocation.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE invocation.run_id IN :run_ids
                      AND invocation.status = 'running'
                    """
                ).bindparams(run_ids_param),
                {
                    "restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE run_agent_invocations AS invocation
                    SET status = 'skipped',
                        error_code = COALESCE(
                            NULLIF(invocation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(invocation.error_message, ''),
                            :pending_skip_message
                        ),
                        finished_at = COALESCE(invocation.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE invocation.run_id IN :run_ids
                      AND invocation.status = 'pending'
                    """
                ).bindparams(run_ids_param),
                {
                    "pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
        if "run_operation_invocations" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_operation_invocations AS operation
                    SET status = 'failed',
                        error_code = COALESCE(
                            NULLIF(operation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(operation.error_message, ''),
                            :restart_failure_message
                        ),
                        finished_at = COALESCE(operation.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE operation.run_id IN :run_ids
                      AND operation.status = 'running'
                    """
                ).bindparams(run_ids_param),
                {
                    "restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE run_operation_invocations AS operation
                    SET status = 'skipped',
                        error_code = COALESCE(
                            NULLIF(operation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(operation.error_message, ''),
                            :pending_skip_message
                        ),
                        finished_at = COALESCE(operation.finished_at, NOW()),
                        updated_at = NOW()
                    WHERE operation.run_id IN :run_ids
                      AND operation.status = 'pending'
                    """
                ).bindparams(run_ids_param),
                {
                    "pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE,
                    "run_ids": recovered_run_ids,
                },
            )
    return max(run_result.rowcount, 0)


__all__ = ["fail_inflight_runs"]
