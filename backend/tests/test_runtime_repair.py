from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import get_session_factory, init_db
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.models.text_template import TextTemplate


def _seed_runtime_backtest(
    database_url: str,
    *,
    backtest_status: str,
    execution_owner: str,
    run_status: str | None,
    include_pending_approval: bool = False,
) -> tuple[int, int | None]:
    session_factory = get_session_factory(database_url)
    with session_factory() as session:
        portfolio = Portfolio(name="Runtime Repair", slug="runtime_repair", base_currency="USD")
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Cash",
            operation_type="DEPOSIT",
            amount=Decimal("1000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Runtime Repair Template", content="# Runtime Repair")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name=f"Runtime Repair {backtest_status}",
            orchestration_pattern_key="seeded_internal_backtest_v1",
            execution_owner=execution_owner,
            status=backtest_status,
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            current_cycle_date=date(2024, 1, 15),
            total_cycles=5,
            completed_cycles=2,
            template_id=template.id,
            webhook_url="internal://ledger",
            webhook_timeout=600,
            current_cycle_status="RUNNING",
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        session.add(backtest)
        session.flush()

        run_id: int | None = None
        if run_status is not None:
            run = RuntimeRun(
                caller_type="backtest",
                caller_id=backtest.id,
                execution_kind="workflow",
                workflow_spec_key="seeded_internal_backtest_v1",
                workflow_spec_version=1,
                agent_spec_key=None,
                agent_spec_version=None,
                caller_scope_key="2024-01-15",
                caller_identity_key=None,
                attempt_number=1,
                status=run_status,
                input_hash="1" * 64,
                output_hash=None,
                retention_class="persistent",
            )
            session.add(run)
            session.flush()
            session.add(
                RuntimeRunArtifact(
                    run_id=run.id,
                    entry_prompt_hash="a" * 64,
                    full_user_prompt_hash="b" * 64,
                    raw_mention_handles=[],
                    resolved_persona_profile_refs=[],
                    resolved_builtin_versions=[],
                    resolved_role_versions=[],
                    resolved_character_versions=[],
                    resolved_bundle_versions=[],
                    resolved_tool_versions=[],
                    resolved_connector_versions=[],
                    mentioned_target_outputs=[],
                    resolved_mentions=[],
                    resolved_capabilities=[],
                )
            )
            session.add(
                RuntimeTraceEvent(
                    run_id=run.id,
                    event_index=0,
                    event_type="RUN_CREATED",
                    payload={"source": "test"},
                )
            )
            if include_pending_approval:
                session.add(
                    RuntimeApproval(
                        run_id=run.id,
                        step_key="analysis",
                        capability_key="connector.persona",
                        status="PENDING",
                    )
                )
            backtest.current_run_id = run.id
            run_id = run.id

        session.commit()
        return backtest.id, run_id


@pytest.mark.parametrize("run_status", ["QUEUED", "RUNNING"])
def test_init_db_repairs_interrupted_runtime_runs_fail_closed(
    database_url: str,
    run_status: str,
) -> None:
    init_db(database_url)
    backtest_id, run_id = _seed_runtime_backtest(
        database_url,
        backtest_status="RUNNING",
        execution_owner="runtime_v2",
        run_status=run_status,
        include_pending_approval=True,
    )

    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == "FAILED"
        assert backtest.current_run_id is None
        assert backtest.current_cycle_status == "FAILED"
        assert "Process interrupted" in (backtest.error_message or "")

        assert run_id is not None
        run = session.get(RuntimeRun, run_id)
        assert run is not None
        assert run.status == "FAILED"
        assert run.approval_summary == {
            "totalCount": 1,
            "pendingCount": 0,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 1,
        }

        artifact = session.get(RuntimeRunArtifact, run_id)
        assert artifact is not None
        assert artifact.terminal_error_code == "server_restart_repair"
        assert "runtime run was active" in (artifact.terminal_error_message or "")

        approval = session.scalar(select(RuntimeApproval).where(RuntimeApproval.run_id == run_id))
        assert approval is not None
        assert approval.status == "EXPIRED"
        assert "server restarted" in (approval.reason or "")
        assert approval.resolved_at is not None

        trace_events = list(
            session.scalars(
                select(RuntimeTraceEvent)
                .where(RuntimeTraceEvent.run_id == run_id)
                .order_by(RuntimeTraceEvent.event_index.asc())
            )
        )
        assert [event.event_type for event in trace_events] == ["RUN_CREATED", "RUN_FAILED"]
        assert trace_events[-1].payload["code"] == "server_restart_repair"
        assert run.trace_summary["eventCount"] == 2


def test_init_db_leaves_waiting_approval_runtime_runs_resumable(database_url: str) -> None:
    init_db(database_url)
    backtest_id, run_id = _seed_runtime_backtest(
        database_url,
        backtest_status="RUNNING",
        execution_owner="runtime_v2",
        run_status="WAITING_APPROVAL",
        include_pending_approval=True,
    )

    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == "RUNNING"
        assert backtest.current_run_id == run_id
        assert backtest.error_message is None

        assert run_id is not None
        run = session.get(RuntimeRun, run_id)
        assert run is not None
        assert run.status == "WAITING_APPROVAL"

        artifact = session.get(RuntimeRunArtifact, run_id)
        assert artifact is not None
        assert artifact.terminal_error_code is None
        assert artifact.terminal_error_message is None

        approval = session.scalar(select(RuntimeApproval).where(RuntimeApproval.run_id == run_id))
        assert approval is not None
        assert approval.status == "PENDING"

        trace_events = list(
            session.scalars(
                select(RuntimeTraceEvent)
                .where(RuntimeTraceEvent.run_id == run_id)
                .order_by(RuntimeTraceEvent.event_index.asc())
            )
        )
        assert [event.event_type for event in trace_events] == ["RUN_CREATED"]


def test_init_db_repairs_stranded_runtime_backtests_without_current_run(database_url: str) -> None:
    init_db(database_url)
    backtest_id, run_id = _seed_runtime_backtest(
        database_url,
        backtest_status="RUNNING",
        execution_owner="runtime_v2",
        run_status=None,
    )
    assert run_id is None

    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == "FAILED"
        assert backtest.current_run_id is None
        assert backtest.current_cycle_status == "FAILED"
        assert "Process interrupted" in (backtest.error_message or "")
