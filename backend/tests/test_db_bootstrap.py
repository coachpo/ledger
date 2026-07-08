from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.session import get_engine, init_db
from app.db.startup_recovery import fail_inflight_runs


def test_fresh_bootstrap_creates_schema_and_seeds(database_url: str) -> None:
    init_db(database_url)
    engine = get_engine(database_url)

    names = set(inspect(engine).get_table_names())
    assert {"workflow_packages", "runs", "run_steps"} <= names
    with engine.connect() as conn:
        keys = set(
            conn.execute(
                text(
                    """
                    SELECT key
                    FROM workflow_packages
                    WHERE key IN (
                        'tradingagents_advisory_research',
                        'digital_oracle_researcher'
                    )
                    """
                )
            ).scalars()
        )
    assert keys == {"tradingagents_advisory_research", "digital_oracle_researcher"}


def test_bootstrap_is_idempotent(database_url: str) -> None:
    init_db(database_url)
    engine = get_engine(database_url)
    sentinel = "2026-01-01 00:00:00+00"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE workflow_packages
                SET updated_at = :sentinel
                WHERE key IN (
                    'tradingagents_advisory_research',
                    'digital_oracle_researcher'
                )
                """
            ),
            {"sentinel": sentinel},
        )

    init_db(database_url)

    with engine.connect() as conn:
        changed = conn.execute(
            text(
                """
                SELECT count(*)
                FROM workflow_packages
                WHERE key IN (
                    'tradingagents_advisory_research',
                    'digital_oracle_researcher'
                )
                  AND updated_at != :sentinel
                """
            ),
            {"sentinel": sentinel},
        ).scalar_one()
    assert changed == 0


def test_startup_recovery_fails_inflight_run_and_steps(database_url: str) -> None:
    init_db(database_url)
    engine = get_engine(database_url)

    with engine.begin() as conn:
        package = (
            conn.execute(
                text(
                    """
                    SELECT id, key
                    FROM workflow_packages
                    WHERE key = 'tradingagents_advisory_research'
                    """
                )
            )
            .mappings()
            .one()
        )
        run_id = conn.execute(
            text(
                """
                INSERT INTO runs (
                    target_kind, target_id, target_key, target_version,
                    workflow_package_id, workflow_package_key,
                    workflow_package_workflow_key, status, input, started_at
                ) VALUES (
                    'workflowPackage', :package_id, :package_key, 1,
                    :package_id, :package_key, 'advisory_research',
                    'running', '{}'::jsonb, NOW()
                )
                RETURNING id
                """
            ),
            {"package_id": package["id"], "package_key": package["key"]},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO run_steps (run_id, step_index, status, origin)
                VALUES
                    (:run_id, 1, 'running', 'planned'),
                    (:run_id, 2, 'pending', 'planned')
                """
            ),
            {"run_id": run_id},
        )

    assert fail_inflight_runs(engine) == 1

    with engine.connect() as conn:
        run = conn.execute(
            text(
                """
                SELECT status, error IS NOT NULL, finished_at IS NOT NULL
                FROM runs
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        ).one()
        steps = conn.execute(
            text(
                """
                SELECT step_index, status, error IS NOT NULL, finished_at IS NOT NULL
                FROM run_steps
                WHERE run_id = :run_id
                ORDER BY step_index
                """
            ),
            {"run_id": run_id},
        ).all()

    assert run == ("failed", True, True)
    assert steps == [
        (1, "failed", True, True),
        (2, "skipped", True, True),
    ]


def test_startup_recovery_keeps_running_run_with_active_scheduler_lease(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = get_engine(database_url)

    with engine.begin() as conn:
        package = (
            conn.execute(
                text(
                    """
                    SELECT id, key
                    FROM workflow_packages
                    WHERE key = 'tradingagents_advisory_research'
                    """
                )
            )
            .mappings()
            .one()
        )
        run_id = conn.execute(
            text(
                """
                INSERT INTO runs (
                    target_kind, target_id, target_key, target_version,
                    workflow_package_id, workflow_package_key,
                    workflow_package_workflow_key, status, input, started_at,
                    lease_owner, lease_expires_at
                ) VALUES (
                    'workflowPackage', :package_id, :package_key, 1,
                    :package_id, :package_key, 'advisory_research',
                    'running', '{}'::jsonb, NOW(),
                    'scheduler:test:1', NOW() + INTERVAL '5 minutes'
                )
                RETURNING id
                """
            ),
            {"package_id": package["id"], "package_key": package["key"]},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO run_steps (run_id, step_index, status, origin)
                VALUES
                    (:run_id, 1, 'running', 'planned'),
                    (:run_id, 2, 'pending', 'planned')
                """
            ),
            {"run_id": run_id},
        )

    assert fail_inflight_runs(engine) == 0

    with engine.connect() as conn:
        run = conn.execute(
            text(
                """
                SELECT status, error, finished_at IS NOT NULL
                FROM runs
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        ).one()
        steps = conn.execute(
            text(
                """
                SELECT step_index, status, error, finished_at IS NOT NULL
                FROM run_steps
                WHERE run_id = :run_id
                ORDER BY step_index
                """
            ),
            {"run_id": run_id},
        ).all()

    assert run == ("running", None, False)
    assert steps == [
        (1, "running", None, False),
        (2, "pending", None, False),
    ]


def test_startup_recovery_fails_running_run_without_lease_expiration(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = get_engine(database_url)

    with engine.begin() as conn:
        package = (
            conn.execute(
                text(
                    """
                    SELECT id, key
                    FROM workflow_packages
                    WHERE key = 'tradingagents_advisory_research'
                    """
                )
            )
            .mappings()
            .one()
        )
        run_id = conn.execute(
            text(
                """
                INSERT INTO runs (
                    target_kind, target_id, target_key, target_version,
                    workflow_package_id, workflow_package_key,
                    workflow_package_workflow_key, status, input, started_at,
                    lease_owner, lease_expires_at
                ) VALUES (
                    'workflowPackage', :package_id, :package_key, 1,
                    :package_id, :package_key, 'advisory_research',
                    'running', '{}'::jsonb, NOW(),
                    'scheduler:test:1', NULL
                )
                RETURNING id
                """
            ),
            {"package_id": package["id"], "package_key": package["key"]},
        ).scalar_one()

    assert fail_inflight_runs(engine) == 1

    with engine.connect() as conn:
        run = conn.execute(
            text(
                """
                SELECT status, error IS NOT NULL, finished_at IS NOT NULL
                FROM runs
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        ).one()

    assert run == ("failed", True, True)
