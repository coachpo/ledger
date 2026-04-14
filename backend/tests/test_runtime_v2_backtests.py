from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.db.session import get_session_factory, init_db
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.report import Report
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.text_template import TextTemplate
from app.services.runtime_control_service import BACKTEST_RUNTIME_V2_FLAG_KEY, RuntimeControlService


def create_portfolio(
    client: TestClient,
    *,
    name: str,
    slug: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/portfolios",
        json={
            "name": name,
            "slug": slug,
            "description": f"{name} description",
            "baseCurrency": "USD",
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_balance(
    client: TestClient,
    portfolio_id: int,
    *,
    label: str,
    amount: str = "1000.00",
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/balances",
        json={"label": label, "amount": amount, "operationType": "DEPOSIT"},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_template(
    client: TestClient,
    *,
    name: str,
    content: str = "# Template",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def build_backtest_payload(
    portfolio_id: int,
    *,
    template_id: int,
    name: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "portfolioId": portfolio_id,
        "templateId": template_id,
        "createTemplate": False,
        "launchMode": "internal",
        "frequency": "DAILY",
        "startDate": "2024-01-02",
        "endDate": "2024-03-29",
        "webhookUrl": "http://localhost:5678/webhook/test",
        "webhookTimeout": 600,
        "priceMode": "CLOSING_PRICE",
        "commissionMode": "ZERO",
        "commissionValue": "0",
        "benchmarkSymbols": ["^GSPC"],
    }
    if overrides:
        payload.update(overrides)
    return payload


@pytest.fixture()
def submitted_backtests(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    submitted: list[int] = []

    monkeypatch.setattr(
        "app.services.backtest_service.BacktestService.run_backtest",
        lambda self, backtest_id: submitted.append(backtest_id),
    )
    return submitted


def _enable_runtime_v2(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        RuntimeControlService(session).set_backtest_runtime_v2_enabled(
            enabled=True,
            actor="test-suite",
            reason="exercise runtime-backed backtest flows",
        )


def _create_backtest(
    client: TestClient,
    *,
    portfolio_name: str,
    portfolio_slug: str,
    template_name: str,
    backtest_name: str,
    launch_mode: str = "internal",
    webhook_url: str | None = "http://localhost:5678/webhook/test",
    webhook_timeout: int | None = 600,
) -> dict[str, Any]:
    portfolio = create_portfolio(client, name=portfolio_name, slug=portfolio_slug)
    create_balance(client, portfolio["id"], label=f"{portfolio_name} Cash", amount="5000.00")
    template = create_template(client, name=template_name)
    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            name=backtest_name,
            overrides={
                "launchMode": launch_mode,
                "webhookUrl": webhook_url,
                "webhookTimeout": webhook_timeout,
            },
        ),
    )
    assert response.status_code == 201, response.json()
    return response.json()


def _seed_runtime_run(
    session_factory: sessionmaker[Session],
    *,
    backtest_id: int,
    status: str,
    cycle_date: date = date(2024, 1, 2),
    pending_approval: bool = False,
    terminal_error_message: str | None = None,
) -> int:
    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        run = RuntimeRun(
            caller_type="backtest",
            caller_id=backtest.id,
            execution_kind="workflow",
            workflow_spec_key=backtest.workflow_spec_key,
            workflow_spec_version=backtest.workflow_spec_version,
            agent_spec_key=None,
            agent_spec_version=None,
            caller_scope_key=cycle_date.isoformat(),
            caller_identity_key=None,
            attempt_number=1,
            status=status,
            input_hash="r" * 64,
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
                "totalCount": 1 if pending_approval else 0,
                "pendingCount": 1 if pending_approval else 0,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
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
                terminal_error_code=(
                    "adapter_execution_failed" if terminal_error_message else None
                ),
                terminal_error_message=terminal_error_message,
            )
        )
        if pending_approval:
            session.add(
                RuntimeApproval(
                    run_id=run.id,
                    step_key="analysis",
                    capability_key="connector.market_data",
                    status="PENDING",
                )
            )
        session.commit()
        return run.id


def test_runtime_and_legacy_backtests_coexist_with_runtime_status_projection(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    runtime_backtest = _create_backtest(
        client,
        portfolio_name="Runtime Projection",
        portfolio_slug="runtime_projection",
        template_name="Runtime Projection Template",
        backtest_name="Runtime Projection Backtest",
    )
    legacy_backtest = _create_backtest(
        client,
        portfolio_name="Legacy Callback",
        portfolio_slug="legacy_callback_projection",
        template_name="Legacy Callback Template",
        backtest_name="Legacy Callback Backtest",
        launch_mode="legacy_callback",
        webhook_url="http://localhost:8765/webhook/legacy",
        webhook_timeout=90,
    )
    assert submitted_backtests == [runtime_backtest["id"], legacy_backtest["id"]]

    run_id = _seed_runtime_run(
        session_factory,
        backtest_id=runtime_backtest["id"],
        status="WAITING_APPROVAL",
        pending_approval=True,
    )

    with session_factory() as session:
        runtime_row = session.get(Backtest, runtime_backtest["id"])
        legacy_row = session.get(Backtest, legacy_backtest["id"])
        assert runtime_row is not None
        assert legacy_row is not None
        runtime_row.status = "PENDING"
        runtime_row.current_run_id = run_id
        runtime_row.current_cycle_status = None
        legacy_row.status = "RUNNING"
        legacy_row.current_cycle_date = date(2024, 1, 2)
        legacy_row.current_cycle_status = "AWAITING_CALLBACK"
        session.commit()

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    items = {item["id"]: item for item in list_response.json()}

    assert items[runtime_backtest["id"]]["status"] == "RUNNING"
    assert items[runtime_backtest["id"]]["currentCycleStatus"] == "WAITING_APPROVAL"
    assert "executionOwner" not in items[runtime_backtest["id"]]
    assert "currentRunId" not in items[runtime_backtest["id"]]

    assert items[legacy_backtest["id"]]["status"] == "RUNNING"
    assert items[legacy_backtest["id"]]["currentCycleStatus"] == "AWAITING_CALLBACK"

    get_response = client.get(f"/api/v1/backtests/{runtime_backtest['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "RUNNING"
    assert get_response.json()["currentCycleStatus"] == "WAITING_APPROVAL"
    assert "executionOwner" not in get_response.json()
    assert "currentRunId" not in get_response.json()


def test_runtime_backtest_projects_succeeded_last_completed_run_for_non_terminal_and_final_cycles(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name="Runtime Success Projection",
        portfolio_slug="runtime_success_projection",
        template_name="Runtime Success Projection Template",
        backtest_name="Runtime Success Projection Backtest",
    )
    assert submitted_backtests == [created["id"]]

    run_id = _seed_runtime_run(session_factory, backtest_id=created["id"], status="SUCCEEDED")

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "RUNNING"
        backtest.total_cycles = 2
        backtest.completed_cycles = 1
        backtest.current_run_id = None
        backtest.last_completed_run_id = run_id
        backtest.current_cycle_status = None
        session.commit()

    detail_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "RUNNING"
    assert detail_response.json()["currentCycleStatus"] == "COMPLETED"

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "COMPLETED"
        backtest.total_cycles = 2
        backtest.completed_cycles = 2
        session.commit()

    final_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert final_response.status_code == 200
    assert final_response.json()["status"] == "COMPLETED"
    assert final_response.json()["currentCycleStatus"] == "COMPLETED"


@pytest.mark.parametrize("runtime_status", ["QUEUED", "RUNNING"])
def test_runtime_backtest_projects_active_current_run_states_as_running(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
    runtime_status: str,
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name=f"Runtime Active {runtime_status}",
        portfolio_slug=f"runtime_active_{runtime_status.lower()}",
        template_name=f"Runtime Active {runtime_status} Template",
        backtest_name=f"Runtime Active {runtime_status} Backtest",
    )
    assert submitted_backtests == [created["id"]]

    run_id = _seed_runtime_run(
        session_factory,
        backtest_id=created["id"],
        status=runtime_status,
    )

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "PENDING"
        backtest.current_run_id = run_id
        backtest.current_cycle_status = None
        session.commit()

    detail_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "RUNNING"
    assert detail_response.json()["currentCycleStatus"] == "RUNNING"


def test_runtime_backtest_projects_failed_current_run_state(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name="Runtime Failure Projection",
        portfolio_slug="runtime_failure_projection",
        template_name="Runtime Failure Projection Template",
        backtest_name="Runtime Failure Projection Backtest",
    )
    assert submitted_backtests == [created["id"]]

    run_id = _seed_runtime_run(
        session_factory,
        backtest_id=created["id"],
        status="FAILED",
        terminal_error_message="Adapter execution failed",
    )

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "RUNNING"
        backtest.current_run_id = run_id
        backtest.current_cycle_status = None
        session.commit()

    detail_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "FAILED"
    assert detail_response.json()["currentCycleStatus"] == "FAILED"
    assert detail_response.json()["errorMessage"] == "Adapter execution failed"
    assert "executionOwner" not in detail_response.json()
    assert "currentRunId" not in detail_response.json()


def test_cancel_runtime_backtest_pre_run_pending_marks_row_cancelled_without_runtime_run(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name="Runtime Pre Run Cancel",
        portfolio_slug="runtime_pre_run_cancel",
        template_name="Runtime Pre Run Cancel Template",
        backtest_name="Runtime Pre Run Cancel Backtest",
    )
    assert submitted_backtests == [created["id"]]

    cancel_response = client.post(f"/api/v1/backtests/{created['id']}/cancel")
    assert cancel_response.status_code == 200, cancel_response.json()
    assert cancel_response.json()["status"] == "CANCELLED"
    assert cancel_response.json()["currentCycleStatus"] == "CANCELLED"
    assert "currentRunId" not in cancel_response.json()

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        assert backtest.status == "CANCELLED"
        assert backtest.current_cycle_status == "CANCELLED"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id is None
        assert session.scalar(select(func.count(RuntimeRun.id))) == 0


def test_cancel_runtime_backtest_waiting_approval_cancels_run_and_expires_approvals(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name="Runtime Approval Cancel",
        portfolio_slug="runtime_approval_cancel",
        template_name="Runtime Approval Cancel Template",
        backtest_name="Runtime Approval Cancel Backtest",
    )
    assert submitted_backtests == [created["id"]]

    run_id = _seed_runtime_run(
        session_factory,
        backtest_id=created["id"],
        status="WAITING_APPROVAL",
        pending_approval=True,
    )

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "RUNNING"
        backtest.current_run_id = run_id
        backtest.current_cycle_date = date(2024, 1, 2)
        backtest.current_cycle_status = None
        session.commit()

    cancel_response = client.post(f"/api/v1/backtests/{created['id']}/cancel")
    assert cancel_response.status_code == 200, cancel_response.json()
    assert cancel_response.json()["status"] == "CANCELLED"
    assert cancel_response.json()["currentCycleStatus"] == "CANCELLED"

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        run = session.get(RuntimeRun, run_id)
        approval = session.scalar(select(RuntimeApproval).where(RuntimeApproval.run_id == run_id))
        assert backtest is not None
        assert run is not None
        assert approval is not None
        assert backtest.status == "CANCELLED"
        assert backtest.current_cycle_status == "CANCELLED"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id == run_id
        assert run.status == "CANCELLED"
        assert approval.status == "EXPIRED"
        assert "cancelled" in (approval.reason or "").lower()


def test_cancel_runtime_backtest_delegates_runtime_cancel_without_inner_commit(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_runtime_v2(session_factory)
    created = _create_backtest(
        client,
        portfolio_name="Runtime Cancel Ownership",
        portfolio_slug="runtime_cancel_ownership",
        template_name="Runtime Cancel Ownership Template",
        backtest_name="Runtime Cancel Ownership Backtest",
    )
    assert submitted_backtests == [created["id"]]

    run_id = _seed_runtime_run(
        session_factory,
        backtest_id=created["id"],
        status="WAITING_APPROVAL",
        pending_approval=True,
    )

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "RUNNING"
        backtest.current_run_id = run_id
        backtest.current_cycle_date = date(2024, 1, 2)
        backtest.current_cycle_status = None
        session.commit()

    commit_flags: list[bool] = []

    def fake_cancel_run(self, run_id: int, *, commit: bool = True):
        commit_flags.append(commit)
        run = self.run_repository.get(run_id)
        assert run is not None
        run.status = "CANCELLED"
        for approval in self.approval_repository.list_pending_for_run(run_id):
            approval.status = "EXPIRED"
            approval.actor = None
            approval.reason = "cancelled by owning backtest service"
            approval.resolved_at = utcnow()
        return None

    monkeypatch.setattr(
        "app.services.backtest_service.AgentRuntimeService.cancel_run",
        fake_cancel_run,
    )

    cancel_response = client.post(f"/api/v1/backtests/{created['id']}/cancel")
    assert cancel_response.status_code == 200, cancel_response.json()
    assert commit_flags == [False]

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        run = session.get(RuntimeRun, run_id)
        approval = session.scalar(select(RuntimeApproval).where(RuntimeApproval.run_id == run_id))
        assert backtest is not None
        assert run is not None
        assert approval is not None
        assert backtest.status == "CANCELLED"
        assert backtest.current_cycle_status == "CANCELLED"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id == run_id
        assert run.status == "CANCELLED"
        assert approval.status == "EXPIRED"


def test_callback_ingress_rejects_runtime_backtests_while_legacy_callback_rows_still_work(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)
    runtime_backtest = _create_backtest(
        client,
        portfolio_name="Runtime Callback Reject",
        portfolio_slug="runtime_callback_reject",
        template_name="Runtime Callback Reject Template",
        backtest_name="Runtime Callback Reject Backtest",
    )
    legacy_backtest = _create_backtest(
        client,
        portfolio_name="Legacy Callback Allowed",
        portfolio_slug="legacy_callback_allowed",
        template_name="Legacy Callback Allowed Template",
        backtest_name="Legacy Callback Allowed Backtest",
        launch_mode="legacy_callback",
        webhook_url="http://localhost:8765/webhook/legacy",
        webhook_timeout=90,
    )
    assert submitted_backtests == [runtime_backtest["id"], legacy_backtest["id"]]

    with session_factory() as session:
        runtime_row = session.get(Backtest, runtime_backtest["id"])
        legacy_row = session.get(Backtest, legacy_backtest["id"])
        assert runtime_row is not None
        assert legacy_row is not None
        runtime_row.status = "RUNNING"
        runtime_row.current_cycle_date = date(2024, 1, 2)
        runtime_row.current_cycle_status = "AWAITING_CALLBACK"
        legacy_row.status = "RUNNING"
        legacy_row.current_cycle_date = date(2024, 1, 2)
        legacy_row.current_cycle_status = "AWAITING_CALLBACK"
        session.commit()

    legacy_response = client.post(
        f"/api/v1/backtests/{legacy_backtest['id']}/cycles/2024-01-02/report",
        json={"name": "legacy-cycle-report", "content": "# Legacy Report", "tags": ["legacy"]},
    )
    assert legacy_response.status_code == 201, legacy_response.json()
    assert legacy_response.json()["slug"] == "legacy_cycle_report"

    runtime_response = client.post(
        f"/api/v1/backtests/{runtime_backtest['id']}/cycles/2024-01-02/report",
        json={"name": "runtime-cycle-report", "content": "# Runtime Report", "tags": ["runtime"]},
    )
    assert runtime_response.status_code == 400
    assert runtime_response.json()["code"] == "invalid_backtest_state"

    with session_factory() as session:
        assert (
            session.scalar(select(Report).where(Report.slug == "legacy_cycle_report")) is not None
        )
        assert session.scalar(select(Report).where(Report.slug == "runtime-cycle-report")) is None


def test_init_db_repairs_stale_pre_run_runtime_backtests(database_url: str) -> None:
    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        portfolio = Portfolio(
            name="Runtime Repair Pending",
            slug="runtime_repair_pending",
            base_currency="USD",
        )
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Cash",
            operation_type="DEPOSIT",
            amount=Decimal("1000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Runtime Repair Pending Template", content="# Pending")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Runtime Repair Pending Backtest",
            orchestration_pattern_key="seeded_internal_backtest_v1",
            launch_mode="internal",
            workflow_spec_key="seeded_internal_backtest_v1",
            workflow_spec_version=1,
            execution_owner="runtime_v2",
            status="PENDING",
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
        session.commit()
        pending_backtest_id = backtest.id

    init_db(database_url)

    with session_factory() as session:
        backtest = session.get(Backtest, pending_backtest_id)
        assert backtest is not None
        assert backtest.status == "FAILED"
        assert backtest.current_cycle_status == "FAILED"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id is None
        assert "Process interrupted" in (backtest.error_message or "")


def test_init_db_replay_preserves_mixed_runtime_and_legacy_backtests_and_blocks_rollback(
    client: TestClient,
    submitted_backtests: list[int],
    database_url: str,
    session_factory: sessionmaker[Session],
) -> None:
    _enable_runtime_v2(session_factory)

    waiting_backtest = _create_backtest(
        client,
        portfolio_name="Runtime Waiting Replay",
        portfolio_slug="runtime_waiting_replay",
        template_name="Runtime Waiting Replay Template",
        backtest_name="Runtime Waiting Replay Backtest",
    )
    repaired_backtest = _create_backtest(
        client,
        portfolio_name="Runtime Repaired Replay",
        portfolio_slug="runtime_repaired_replay",
        template_name="Runtime Repaired Replay Template",
        backtest_name="Runtime Repaired Replay Backtest",
    )
    orphaned_backtest = _create_backtest(
        client,
        portfolio_name="Runtime Orphaned Replay",
        portfolio_slug="runtime_orphaned_replay",
        template_name="Runtime Orphaned Replay Template",
        backtest_name="Runtime Orphaned Replay Backtest",
    )
    legacy_backtest = _create_backtest(
        client,
        portfolio_name="Legacy Replay",
        portfolio_slug="legacy_replay",
        template_name="Legacy Replay Template",
        backtest_name="Legacy Replay Backtest",
        launch_mode="legacy_callback",
        webhook_url="http://localhost:8765/webhook/legacy-replay",
        webhook_timeout=90,
    )
    assert submitted_backtests == [
        waiting_backtest["id"],
        repaired_backtest["id"],
        orphaned_backtest["id"],
        legacy_backtest["id"],
    ]

    waiting_run_id = _seed_runtime_run(
        session_factory,
        backtest_id=waiting_backtest["id"],
        status="WAITING_APPROVAL",
        cycle_date=date(2024, 1, 2),
        pending_approval=True,
    )
    repaired_run_id = _seed_runtime_run(
        session_factory,
        backtest_id=repaired_backtest["id"],
        status="RUNNING",
        cycle_date=date(2024, 1, 3),
        pending_approval=True,
    )

    with session_factory() as session:
        waiting_row = session.get(Backtest, waiting_backtest["id"])
        repaired_row = session.get(Backtest, repaired_backtest["id"])
        orphaned_row = session.get(Backtest, orphaned_backtest["id"])
        legacy_row = session.get(Backtest, legacy_backtest["id"])
        assert waiting_row is not None
        assert repaired_row is not None
        assert orphaned_row is not None
        assert legacy_row is not None

        waiting_row.status = "RUNNING"
        waiting_row.current_cycle_date = date(2024, 1, 2)
        waiting_row.current_cycle_status = None
        waiting_row.current_run_id = waiting_run_id

        repaired_row.status = "RUNNING"
        repaired_row.current_cycle_date = date(2024, 1, 3)
        repaired_row.current_cycle_status = None
        repaired_row.current_run_id = repaired_run_id

        orphaned_row.status = "RUNNING"
        orphaned_row.current_cycle_date = date(2024, 1, 4)
        orphaned_row.current_cycle_status = "RUNNING"

        legacy_row.status = "RUNNING"
        legacy_row.current_cycle_date = date(2024, 1, 5)
        legacy_row.current_cycle_status = "AWAITING_CALLBACK"

        session.commit()

    with session_factory() as session:
        session.execute(
            text("ALTER TABLE backtests DROP CONSTRAINT IF EXISTS backtests_current_run_id_fkey")
        )
        session.execute(
            text("UPDATE backtests SET current_run_id = :run_id WHERE id = :backtest_id"),
            {"run_id": 999999, "backtest_id": orphaned_backtest["id"]},
        )
        session.commit()

    init_db(database_url)

    with session_factory() as session:
        waiting_row = session.get(Backtest, waiting_backtest["id"])
        repaired_row = session.get(Backtest, repaired_backtest["id"])
        orphaned_row = session.get(Backtest, orphaned_backtest["id"])
        legacy_row = session.get(Backtest, legacy_backtest["id"])
        waiting_run = session.get(RuntimeRun, waiting_run_id)
        repaired_run = session.get(RuntimeRun, repaired_run_id)

        assert waiting_row is not None
        assert repaired_row is not None
        assert orphaned_row is not None
        assert legacy_row is not None
        assert waiting_run is not None
        assert repaired_run is not None

        assert waiting_row.status == "RUNNING"
        assert waiting_row.current_run_id == waiting_run_id
        assert waiting_row.error_message is None
        assert waiting_run.status == "WAITING_APPROVAL"

        assert repaired_row.status == "FAILED"
        assert repaired_row.current_cycle_status == "FAILED"
        assert repaired_row.current_run_id is None
        assert "Process interrupted" in (repaired_row.error_message or "")
        assert repaired_run.status == "FAILED"

        assert orphaned_row.status == "RUNNING"
        assert orphaned_row.current_run_id is None
        assert orphaned_row.current_cycle_status is None
        assert orphaned_row.error_message is None

        assert legacy_row.status == "FAILED"
        assert legacy_row.current_cycle_status is None
        assert "Process interrupted" in (legacy_row.error_message or "")

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200, list_response.json()
    items = {item["id"]: item for item in list_response.json()}

    assert items[waiting_backtest["id"]]["status"] == "RUNNING"
    assert items[waiting_backtest["id"]]["currentCycleStatus"] == "WAITING_APPROVAL"
    assert "currentRunId" not in items[waiting_backtest["id"]]
    assert "executionOwner" not in items[waiting_backtest["id"]]

    assert items[repaired_backtest["id"]]["status"] == "FAILED"
    assert items[repaired_backtest["id"]]["currentCycleStatus"] == "FAILED"
    assert "Process interrupted" in (items[repaired_backtest["id"]]["errorMessage"] or "")

    assert items[orphaned_backtest["id"]]["status"] == "RUNNING"
    assert items[orphaned_backtest["id"]]["currentCycleStatus"] is None

    assert items[legacy_backtest["id"]]["status"] == "FAILED"
    assert items[legacy_backtest["id"]]["currentCycleStatus"] is None

    disable_response = client.patch(
        f"/api/v2/runtime/control/flags/{BACKTEST_RUNTIME_V2_FLAG_KEY}",
        json={
            "enabled": False,
            "actor": "release-manager",
            "reason": "rollback after init replay",
        },
    )
    assert disable_response.status_code == 400, disable_response.json()
    assert disable_response.json()["code"] == "runtime_flag_change_rejected"

    with session_factory() as session:
        service = RuntimeControlService(session)
        flag = service.get_flag(BACKTEST_RUNTIME_V2_FLAG_KEY)
        events = service.list_flag_events(BACKTEST_RUNTIME_V2_FLAG_KEY).items

        assert flag.enabled is True
        assert [event.result for event in events] == ["rejected", "applied"]
        assert f"{waiting_backtest['id']}:RUNNING" in events[0].reason
        assert f"{orphaned_backtest['id']}:RUNNING" in events[0].reason
        assert f"{repaired_backtest['id']}:FAILED" not in events[0].reason
        assert f"{legacy_backtest['id']}:" not in events[0].reason
