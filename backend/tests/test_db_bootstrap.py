from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, text

import app.db.session as db_session
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
        recovered_steps = (
            conn.execute(
                text(
                    """
                    INSERT INTO run_steps (run_id, step_index, status, origin)
                    VALUES
                        (:run_id, 1, 'running', 'planned'),
                        (:run_id, 2, 'pending', 'planned')
                    RETURNING step_index, id
                    """
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        recovered_step_ids = {row["step_index"]: row["id"] for row in recovered_steps}
        conn.execute(
            text(
                """
                INSERT INTO run_agent_invocations (
                    run_step_id, run_id, step_index, slot, agent_id, agent_key,
                    agent_version, output_schema_id, output_schema_version, status
                ) VALUES
                    (
                        :running_step_id, :run_id, 1, 'decision', 1, 'running_agent',
                        1, 1, 1, 'running'
                    ),
                    (
                        :pending_step_id, :run_id, 2, 'summary', 1, 'pending_agent',
                        1, 1, 1, 'pending'
                    )
                """
            ),
            {
                "running_step_id": recovered_step_ids[1],
                "pending_step_id": recovered_step_ids[2],
                "run_id": run_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO run_operation_invocations (
                    run_step_id, run_id, step_index, slot, operation_key, operation_kind,
                    output_schema_id, output_schema_version, status
                ) VALUES
                    (
                        :running_step_id, :run_id, 1, 'fetch', 'running_http', 'http',
                        1, 1, 'running'
                    ),
                    (
                        :pending_step_id, :run_id, 2, 'audit', 'pending_http', 'http',
                        1, 1, 'pending'
                    )
                """
            ),
            {
                "running_step_id": recovered_step_ids[1],
                "pending_step_id": recovered_step_ids[2],
                "run_id": run_id,
            },
        )
        historical_failed_run_id = conn.execute(
            text(
                """
                INSERT INTO runs (
                    target_kind, target_id, target_key, target_version,
                    workflow_package_id, workflow_package_key,
                    workflow_package_workflow_key, status, input, started_at, finished_at
                ) VALUES (
                    'workflowPackage', :package_id, :package_key, 1,
                    :package_id, :package_key, 'advisory_research',
                    'failed', '{}'::jsonb, NOW() - INTERVAL '1 hour', NOW() - INTERVAL '30 minutes'
                )
                RETURNING id
                """
            ),
            {"package_id": package["id"], "package_key": package["key"]},
        ).scalar_one()
        historical_step_id = conn.execute(
            text(
                """
                INSERT INTO run_steps (run_id, step_index, status, origin)
                VALUES (:run_id, 1, 'running', 'planned')
                RETURNING id
                """
            ),
            {"run_id": historical_failed_run_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO run_agent_invocations (
                    run_step_id, run_id, step_index, slot, agent_id, agent_key,
                    agent_version, output_schema_id, output_schema_version, status
                ) VALUES (
                    :run_step_id, :run_id, 1, 'decision', 1, 'historical_agent',
                    1, 1, 1, 'running'
                )
                """
            ),
            {"run_step_id": historical_step_id, "run_id": historical_failed_run_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO run_operation_invocations (
                    run_step_id, run_id, step_index, slot, operation_key, operation_kind,
                    output_schema_id, output_schema_version, status
                ) VALUES (
                    :run_step_id, :run_id, 1, 'fetch', 'historical_http', 'http',
                    1, 1, 'running'
                )
                """
            ),
            {"run_step_id": historical_step_id, "run_id": historical_failed_run_id},
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
        agent_invocations = conn.execute(
            text(
                """
                SELECT slot, status, error_code, error_message IS NOT NULL, finished_at IS NOT NULL
                FROM run_agent_invocations
                WHERE run_id = :run_id
                ORDER BY step_index, slot
                """
            ),
            {"run_id": run_id},
        ).all()
        operation_invocations = conn.execute(
            text(
                """
                SELECT slot, status, error_code, error_message IS NOT NULL, finished_at IS NOT NULL
                FROM run_operation_invocations
                WHERE run_id = :run_id
                ORDER BY step_index, slot
                """
            ),
            {"run_id": run_id},
        ).all()
        historical_steps = conn.execute(
            text(
                """
                SELECT step_index, status, error, finished_at
                FROM run_steps
                WHERE run_id = :run_id
                """
            ),
            {"run_id": historical_failed_run_id},
        ).all()
        historical_agent_invocations = conn.execute(
            text(
                """
                SELECT slot, status, error_code, error_message, finished_at
                FROM run_agent_invocations
                WHERE run_id = :run_id
                """
            ),
            {"run_id": historical_failed_run_id},
        ).all()
        historical_operation_invocations = conn.execute(
            text(
                """
                SELECT slot, status, error_code, error_message, finished_at
                FROM run_operation_invocations
                WHERE run_id = :run_id
                """
            ),
            {"run_id": historical_failed_run_id},
        ).all()

    assert run == ("failed", True, True)
    assert steps == [
        (1, "failed", True, True),
        (2, "skipped", True, True),
    ]
    assert agent_invocations == [
        ("decision", "failed", "startup_recovery", True, True),
        ("summary", "skipped", "startup_recovery", True, True),
    ]
    assert operation_invocations == [
        ("fetch", "failed", "startup_recovery", True, True),
        ("audit", "skipped", "startup_recovery", True, True),
    ]
    assert historical_steps == [(1, "running", None, None)]
    assert historical_agent_invocations == [("decision", "running", None, None, None)]
    assert historical_operation_invocations == [("fetch", "running", None, None, None)]


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


def test_init_db_serializes_bootstrap_with_advisory_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: object, params: dict[str, int] | None = None) -> None:
            assert params == {"lock_key": db_session._INIT_DB_ADVISORY_LOCK_KEY}
            sql = str(statement)
            if "pg_advisory_lock" in sql:
                calls.append("lock")
                return
            if "pg_advisory_unlock" in sql:
                calls.append("unlock")
                return
            raise AssertionError(sql)

    class FakeEngine:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self) -> FakeConnection:
            return FakeConnection()

    engine = FakeEngine()

    monkeypatch.setattr(db_session, "get_engine", lambda database_url=None: engine)
    monkeypatch.setattr(
        db_session,
        "validate_supported_database_engine",
        lambda candidate: calls.append(f"validate:{candidate is engine}"),
    )
    monkeypatch.setattr(
        db_session.Base.metadata,
        "create_all",
        lambda *, bind: calls.append(f"create_all:{bind is engine}"),
    )
    monkeypatch.setattr(
        db_session,
        "seed_preset_packages",
        lambda candidate: calls.append(f"seed:{candidate is engine}"),
    )
    monkeypatch.setattr(
        db_session,
        "fail_inflight_runs",
        lambda candidate: calls.append(f"recover:{candidate is engine}"),
    )

    init_db("postgresql+psycopg://example")

    assert calls == [
        "validate:True",
        "lock",
        "create_all:True",
        "seed:True",
        "recover:True",
        "unlock",
    ]


def test_init_db_releases_advisory_lock_on_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, statement: object, params: dict[str, int] | None = None) -> None:
            assert params == {"lock_key": db_session._INIT_DB_ADVISORY_LOCK_KEY}
            sql = str(statement)
            if "pg_advisory_lock" in sql:
                calls.append("lock")
                return
            if "pg_advisory_unlock" in sql:
                calls.append("unlock")
                return
            raise AssertionError(sql)

    class FakeEngine:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self) -> FakeConnection:
            return FakeConnection()

    engine = FakeEngine()

    monkeypatch.setattr(db_session, "get_engine", lambda database_url=None: engine)
    monkeypatch.setattr(db_session, "validate_supported_database_engine", lambda _: None)
    monkeypatch.setattr(
        db_session.Base.metadata,
        "create_all",
        lambda *, bind: calls.append(f"create_all:{bind is engine}"),
    )
    monkeypatch.setattr(
        db_session,
        "seed_preset_packages",
        lambda candidate: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        db_session,
        "fail_inflight_runs",
        lambda candidate: calls.append(f"recover:{candidate is engine}"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        init_db("postgresql+psycopg://example")

    assert calls == [
        "lock",
        "create_all:True",
        "unlock",
    ]


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ],
)
def test_normalize_database_url_pins_psycopg_driver(given: str, expected: str) -> None:
    from app.db.engine import _normalize_database_url

    assert _normalize_database_url(given) == expected


def test_get_engine_accepts_provider_style_url(database_url: str) -> None:
    bare_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    engine = get_engine(bare_url)
    assert engine.dialect.driver == "psycopg"
