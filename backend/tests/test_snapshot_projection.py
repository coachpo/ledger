from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.db.upgrades import upgrade_legacy_schema
from app.models.backtest import Backtest
from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.models.text_template import TextTemplate
from app.services.backtest_snapshot_projector import BacktestSnapshotProjector


def _create_backtest(session: Session, *, name: str) -> Backtest:
    portfolio = Portfolio(name=f"{name} Portfolio", slug=f"{name}_portfolio", base_currency="USD")
    session.add(portfolio)
    session.flush()

    balance = Balance(
        portfolio_id=portfolio.id,
        label="Cash",
        operation_type="DEPOSIT",
        amount=Decimal("1000.00"),
        currency="USD",
    )
    template = TextTemplate(name=f"{name} Template", content="# Snapshot Projector Test")
    session.add_all([balance, template])
    session.flush()

    backtest = Backtest(
        portfolio_id=portfolio.id,
        deposit_balance_id=balance.id,
        name=name,
        orchestration_pattern_key="seeded_internal_backtest_v1",
        workflow_spec_key="seeded_internal_backtest_v1",
        workflow_spec_version=1,
        execution_owner="runtime_v2",
        status="RUNNING",
        frequency="DAILY",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 31),
        total_cycles=5,
        completed_cycles=0,
        template_id=template.id,
        webhook_url="internal://ledger",
        webhook_timeout=600,
        price_mode="CLOSING_PRICE",
        commission_mode="ZERO",
        commission_value=Decimal("0"),
        benchmark_symbols=["^GSPC"],
    )
    session.add(backtest)
    session.flush()
    return backtest


def _build_run(
    *,
    backtest_id: int,
    cycle_date: date,
    attempt_number: int,
    status: str,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type="backtest",
        caller_id=backtest_id,
        execution_kind="workflow",
        workflow_spec_key="seeded_internal_backtest_v1",
        workflow_spec_version=1,
        agent_spec_key=None,
        agent_spec_version=None,
        caller_scope_key=cycle_date.isoformat(),
        caller_identity_key=None,
        attempt_number=attempt_number,
        status=status,
        input_hash=(str(attempt_number) * 64)[:64],
        output_hash=None,
        retention_class="persistent",
        expires_at=None,
        trace_summary={
            "eventCount": 0,
            "toolCallCount": 0,
            "warningCount": 0,
            "lastEventAt": None,
        },
        approval_summary={
            "totalCount": 0,
            "pendingCount": 0,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 0,
        },
    )


def _build_artifact(
    *,
    run_id: int,
    prompt_report_slug: str,
    source_handle: str,
    legacy_role_id: int | None = None,
    legacy_role_version: int | None = None,
    legacy_character_id: int | None = None,
    legacy_character_version: int | None = None,
) -> RuntimeRunArtifact:
    return RuntimeRunArtifact(
        run_id=run_id,
        entry_prompt_hash="e" * 64,
        full_user_prompt_hash="f" * 64,
        authored_entry_prompt_body=f"Ask @{source_handle}.",
        compiled_entry_prompt_body="Compiled entry.",
        execution_context_body="Execution context.",
        prompt_report_slug=prompt_report_slug,
        raw_mention_handles=[source_handle],
        resolved_persona_profile_refs=[
            {
                "personaProfileKey": (
                    f"character:{source_handle}"
                    if legacy_character_id is not None
                    else f"builtin:{source_handle}"
                ),
                "personaProfileVersion": 1,
                "selectionSource": "mention_resolution",
            }
        ],
        report_markdown=None,
        normalized_trade_decisions=None,
        resolved_builtin_versions=(
            [
                {
                    "canonical_target_id": f"builtin:{source_handle}",
                    "handle": source_handle,
                    "revision": 1,
                }
            ]
            if legacy_character_id is None
            else []
        ),
        resolved_role_versions=(
            [
                {
                    "canonical_target_id": f"role:{source_handle}_role",
                    "role_id": legacy_role_id,
                    "version": legacy_role_version,
                }
            ]
            if legacy_role_id is not None and legacy_role_version is not None
            else []
        ),
        resolved_character_versions=(
            [
                {
                    "canonical_target_id": f"character:{source_handle}",
                    "character_id": legacy_character_id,
                    "version": legacy_character_version,
                }
            ]
            if legacy_character_id is not None and legacy_character_version is not None
            else []
        ),
        resolved_bundle_versions=[],
        resolved_tool_versions=[],
        resolved_connector_versions=[],
        mentioned_target_outputs=[
            {
                "handle": source_handle,
                "canonical_target_id": (
                    f"character:{source_handle}"
                    if legacy_character_id is not None
                    else f"builtin:{source_handle}"
                ),
                "target_type": ("character" if legacy_character_id is not None else "builtin"),
                "output_markdown": f"{source_handle} output",
            }
        ],
        resolved_mentions=[
            {
                "originalText": f"@{source_handle}",
                "sourceHandle": source_handle,
                "canonicalTargetId": (
                    f"character:{source_handle}"
                    if legacy_character_id is not None
                    else f"builtin:{source_handle}"
                ),
                "targetType": ("character" if legacy_character_id is not None else "builtin"),
                "mentionOrder": 0,
                "personaProfileKey": (
                    f"character:{source_handle}"
                    if legacy_character_id is not None
                    else f"builtin:{source_handle}"
                ),
                "personaProfileVersion": 1,
                "legacyRoleId": legacy_role_id,
                "legacyRoleVersion": legacy_role_version,
                "legacyCharacterId": legacy_character_id,
                "legacyCharacterVersion": legacy_character_version,
            }
        ],
        resolved_workflow_agent_refs=None,
        resolved_capabilities=[],
        final_output=None,
        terminal_error_code=None,
        terminal_error_message=None,
    )


def test_snapshot_projector_overwrites_cycle_row_for_latest_attempt_only(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 19)

    with session_factory() as session:
        backtest = _create_backtest(session, name="snapshot_latest_attempt")
        first_run = _build_run(
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            attempt_number=1,
            status="FAILED",
        )
        session.add(first_run)
        session.flush()
        session.add(
            _build_artifact(
                run_id=first_run.id,
                prompt_report_slug="attempt_one_prompt",
                source_handle="librarian",
            )
        )
        session.commit()

        projector = BacktestSnapshotProjector(session)
        assert projector.project_latest_attempt(first_run.id) is True

        first_snapshot = session.scalar(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest.id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        )
        assert first_snapshot is not None
        assert first_snapshot.prompt_report_slug == "attempt_one_prompt"
        assert first_snapshot.resolved_mentions == [
            {
                "original_text": "@librarian",
                "handle": "librarian",
                "canonical_target_id": "builtin:librarian",
                "target_type": "builtin",
                "role_id": None,
                "role_version": None,
                "character_id": None,
                "character_version": None,
                "mention_order": 0,
            }
        ]
        assert first_snapshot.approval_trace == "not_required"

        second_run = _build_run(
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            attempt_number=2,
            status="SUCCEEDED",
        )
        session.add(second_run)
        session.flush()
        session.add(
            _build_artifact(
                run_id=second_run.id,
                prompt_report_slug="attempt_two_prompt",
                source_handle="analyst",
                legacy_role_id=31,
                legacy_role_version=4,
                legacy_character_id=44,
                legacy_character_version=7,
            )
        )
        session.commit()

        assert projector.project_latest_attempt(second_run.id) is True
        assert projector.project_latest_attempt(first_run.id) is False

        snapshots = session.scalars(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest.id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        ).all()
        snapshot_payloads = [
            {
                "prompt_report_slug": item.prompt_report_slug,
                "resolved_mentions": list(item.resolved_mentions),
                "resolved_role_versions": list(item.resolved_role_versions),
                "resolved_character_versions": list(item.resolved_character_versions),
            }
            for item in snapshots
        ]

    assert len(snapshot_payloads) == 1
    snapshot = snapshot_payloads[0]
    assert snapshot["prompt_report_slug"] == "attempt_two_prompt"
    assert snapshot["resolved_mentions"] == [
        {
            "original_text": "@analyst",
            "handle": "analyst",
            "canonical_target_id": "character:analyst",
            "target_type": "character",
            "role_id": 31,
            "role_version": 4,
            "character_id": 44,
            "character_version": 7,
            "mention_order": 0,
        }
    ]
    assert snapshot["resolved_role_versions"] == [
        {
            "canonical_target_id": "role:analyst_role",
            "role_id": 31,
            "version": 4,
        }
    ]
    assert snapshot["resolved_character_versions"] == [
        {
            "canonical_target_id": "character:analyst",
            "character_id": 44,
            "version": 7,
        }
    ]


def test_snapshot_projector_projects_tool_and_approval_traces_from_runtime_records(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 20)

    with session_factory() as session:
        backtest = _create_backtest(session, name="snapshot_trace_projection")
        run = _build_run(
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            attempt_number=1,
            status="CANCELLED",
        )
        session.add(run)
        session.flush()
        approval_one = RuntimeApproval(
            run_id=run.id,
            step_key="analysis",
            capability_key="ledger.mcp.market_data",
            status="APPROVED",
            actor="tester",
            reason="approved for execution",
            resolved_at=utcnow(),
        )
        approval_two = RuntimeApproval(
            run_id=run.id,
            step_key="analysis",
            capability_key="ledger.mcp.market_data",
            status="EXPIRED",
            actor=None,
            reason="Run cancelled before approval resolution",
            resolved_at=utcnow(),
        )
        session.add_all([approval_one, approval_two])
        session.flush()
        artifact = _build_artifact(
            run_id=run.id,
            prompt_report_slug="trace_projection_prompt",
            source_handle="librarian",
        )
        artifact.resolved_capabilities = [
            {
                "capabilityKey": "ledger.mcp.market_data",
                "capabilityVersion": 1,
                "capabilityType": "connector",
                "approvalMode": "required",
                "displayName": "Market Data",
                "transport": "mcp",
                "lifecycle": "approved",
                "effectiveConfig": {},
            }
        ]
        session.add(artifact)
        session.flush()
        session.add_all(
            [
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=0,
                    event_type="APPROVAL_REQUESTED",
                    step_key="analysis",
                    capability_key="ledger.mcp.market_data",
                    approval_id=approval_one.id,
                    payload={"approvalId": approval_one.id, "status": "PENDING"},
                ),
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=1,
                    event_type="APPROVAL_REQUESTED",
                    step_key="analysis",
                    capability_key="ledger.mcp.market_data",
                    approval_id=approval_two.id,
                    payload={"approvalId": approval_two.id, "status": "PENDING"},
                ),
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=2,
                    event_type="TOOL_CALLED",
                    step_key="analysis",
                    capability_key="ledger.mcp.market_data",
                    payload={
                        "call_index": 0,
                        "tool_id": "ledger.mcp.market_data",
                        "status": "success",
                        "latency_ms": 6,
                        "argument_hash": "a" * 64,
                        "result_hash": "b" * 64,
                    },
                ),
            ]
        )
        session.commit()

        projector = BacktestSnapshotProjector(session)
        assert projector.project_latest_attempt(run.id) is True
        snapshot = session.scalar(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest.id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        )
        assert snapshot is not None
        snapshot_payload = {
            "tool_call_trace": list(snapshot.tool_call_trace),
            "approval_trace": snapshot.approval_trace,
        }

    assert snapshot_payload["tool_call_trace"] == [
        {
            "call_index": 0,
            "tool_id": "ledger.mcp.market_data",
            "status": "success",
            "latency_ms": 6,
            "argument_hash": "a" * 64,
            "result_hash": "b" * 64,
        }
    ]
    assert snapshot_payload["approval_trace"] == [
        {
            "call_index": 0,
            "tool_id": "ledger.mcp.market_data",
            "status": "approved",
            "kind": "connector",
            "transport": "mcp",
        },
        {
            "call_index": 1,
            "tool_id": "ledger.mcp.market_data",
            "status": "expired",
            "kind": "connector",
            "transport": "mcp",
        },
    ]


def test_snapshot_projector_rechecks_latest_attempt_before_commit(
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 21)

    with session_factory() as session:
        backtest = _create_backtest(session, name="snapshot_recheck_latest_attempt")
        first_run = _build_run(
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            attempt_number=1,
            status="FAILED",
        )
        second_run = _build_run(
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            attempt_number=2,
            status="SUCCEEDED",
        )
        session.add_all([first_run, second_run])
        session.flush()
        session.add_all(
            [
                _build_artifact(
                    run_id=first_run.id,
                    prompt_report_slug="attempt_one_prompt",
                    source_handle="librarian",
                ),
                _build_artifact(
                    run_id=second_run.id,
                    prompt_report_slug="attempt_two_prompt",
                    source_handle="analyst",
                    legacy_role_id=31,
                    legacy_role_version=4,
                    legacy_character_id=44,
                    legacy_character_version=7,
                ),
            ]
        )
        session.commit()

        projector = BacktestSnapshotProjector(session)
        assert projector.project_latest_attempt(second_run.id) is True

        latest_attempts = [first_run, second_run]
        call_count = 0

        def fake_is_latest_attempt(run: RuntimeRun) -> bool:
            nonlocal call_count
            expected = latest_attempts[min(call_count, len(latest_attempts) - 1)]
            call_count += 1
            return run.id == expected.id

        monkeypatch.setattr(projector, "_is_latest_attempt", fake_is_latest_attempt)

        assert projector.project_latest_attempt(first_run.id) is False
        assert call_count == 2

        snapshot = session.scalar(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest.id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        )
        assert snapshot is not None
        snapshot_payload = {
            "prompt_report_slug": snapshot.prompt_report_slug,
            "resolved_mentions": list(snapshot.resolved_mentions),
        }

    assert snapshot_payload == {
        "prompt_report_slug": "attempt_two_prompt",
        "resolved_mentions": [
            {
                "original_text": "@analyst",
                "handle": "analyst",
                "canonical_target_id": "character:analyst",
                "target_type": "character",
                "role_id": 31,
                "role_version": 4,
                "character_id": 44,
                "character_version": 7,
                "mention_order": 0,
            }
        ],
    }


def test_snapshot_projector_replaces_upgraded_legacy_snapshot_rows_with_runtime_projection(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 22)

    with session_factory() as session:
        backtest = _create_backtest(session, name="snapshot_upgrade_runtime_projection")
        backtest_id = backtest.id
        session.commit()
        engine = cast(Engine, session.get_bind())

    with engine.begin() as connection:
        connection.exec_driver_sql(
            'DROP TABLE IF EXISTS "backtest_orchestration_snapshots" CASCADE'
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE backtest_orchestration_snapshots (
                id SERIAL PRIMARY KEY,
                backtest_id INTEGER NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
                cycle_date DATE NOT NULL,
                snapshot_type VARCHAR(50) NOT NULL,
                snapshot JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_backtest_orchestration_snapshots_cycle
                    UNIQUE (backtest_id, cycle_date)
            )
            """
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO backtest_orchestration_snapshots (
                backtest_id,
                cycle_date,
                snapshot_type,
                snapshot
            ) VALUES (
                {backtest_id},
                DATE '{cycle_date.isoformat()}',
                'mentioned_targets',
                jsonb_build_object(
                    'prompt_report_slug', 'legacy_prompt',
                    'orchestration_pattern_key', 'analyst_reviewer_v1',
                    'pattern_policy_version', 1,
                    'entry_prompt_hash', repeat('1', 64),
                    'full_user_prompt_hash', repeat('2', 64),
                    'resolved_mentions', jsonb_build_array(
                        jsonb_build_object('handle', 'librarian')
                    ),
                    'mentioned_target_outputs', jsonb_build_array(
                        jsonb_build_object(
                            'handle',
                            'librarian',
                            'output_markdown',
                            'legacy context summary'
                        )
                    ),
                    'built_in_revisions', jsonb_build_array('librarian')
                )
            )
            """
        )

    upgrade_legacy_schema(engine)

    with session_factory() as session:
        upgraded_snapshot = session.scalar(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest_id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        )
        assert upgraded_snapshot is not None
        assert upgraded_snapshot.prompt_report_slug == "legacy_prompt"
        assert upgraded_snapshot.orchestration_pattern_key == "analyst_reviewer_v1"
        assert list(upgraded_snapshot.resolved_mentions) == [{"handle": "librarian"}]
        assert list(upgraded_snapshot.resolved_builtin_versions) == [
            {
                "canonical_target_id": "builtin:librarian",
                "handle": "librarian",
                "revision": 1,
            }
        ]

        run = _build_run(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            attempt_number=2,
            status="SUCCEEDED",
        )
        session.add(run)
        session.flush()
        session.add(
            _build_artifact(
                run_id=run.id,
                prompt_report_slug="runtime_prompt",
                source_handle="analyst",
                legacy_role_id=31,
                legacy_role_version=4,
                legacy_character_id=44,
                legacy_character_version=7,
            )
        )
        session.commit()

        projector = BacktestSnapshotProjector(session)
        assert projector.project_latest_attempt(run.id) is True
        session.expire_all()

        snapshots = session.scalars(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == backtest_id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        ).all()
        assert len(snapshots) == 1

        snapshot = snapshots[0]
        snapshot_payload = {
            "prompt_report_slug": snapshot.prompt_report_slug,
            "orchestration_pattern_key": snapshot.orchestration_pattern_key,
            "resolved_mentions": list(snapshot.resolved_mentions),
            "resolved_builtin_versions": list(snapshot.resolved_builtin_versions),
            "resolved_role_versions": list(snapshot.resolved_role_versions),
            "resolved_character_versions": list(snapshot.resolved_character_versions),
        }

    assert snapshot_payload == {
        "prompt_report_slug": "runtime_prompt",
        "orchestration_pattern_key": "seeded_internal_backtest_v1",
        "resolved_mentions": [
            {
                "original_text": "@analyst",
                "handle": "analyst",
                "canonical_target_id": "character:analyst",
                "target_type": "character",
                "role_id": 31,
                "role_version": 4,
                "character_id": 44,
                "character_version": 7,
                "mention_order": 0,
            }
        ],
        "resolved_builtin_versions": [],
        "resolved_role_versions": [
            {
                "canonical_target_id": "role:analyst_role",
                "role_id": 31,
                "version": 4,
            }
        ],
        "resolved_character_versions": [
            {
                "canonical_target_id": "character:analyst",
                "character_id": 44,
                "version": 7,
            }
        ],
    }
