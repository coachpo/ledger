from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate
from app.services.runtime_control_service import BACKTEST_RUNTIME_V2_FLAG_KEY, RuntimeControlService


def _create_backtest(
    session: Session,
    *,
    name: str,
    status: str,
    execution_owner: str | None,
) -> Backtest:
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
    template = TextTemplate(name=f"{name} Template", content="# Runtime Control")
    session.add_all([balance, template])
    session.flush()

    backtest = Backtest(
        portfolio_id=portfolio.id,
        deposit_balance_id=balance.id,
        name=name,
        orchestration_pattern_key="seeded_internal_backtest_v1",
        execution_owner=execution_owner,
        status=status,
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
    return backtest


def test_runtime_control_flag_route_reads_and_applies_mutation(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    get_response = client.get(f"/api/v2/runtime/control/flags/{BACKTEST_RUNTIME_V2_FLAG_KEY}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["flagKey"] == BACKTEST_RUNTIME_V2_FLAG_KEY
    assert get_response.json()["enabled"] is False

    patch_response = client.patch(
        f"/api/v2/runtime/control/flags/{BACKTEST_RUNTIME_V2_FLAG_KEY}",
        json={
            "enabled": True,
            "actor": "release-manager",
            "reason": "enable runtime-backed backtests",
        },
    )
    assert patch_response.status_code == 200, patch_response.json()
    assert patch_response.json()["flagKey"] == BACKTEST_RUNTIME_V2_FLAG_KEY
    assert patch_response.json()["enabled"] is True

    with session_factory() as session:
        events = RuntimeControlService(session).list_flag_events(BACKTEST_RUNTIME_V2_FLAG_KEY).items
        assert [event.result for event in events] == ["applied"]
        assert events[0].actor == "release-manager"
        assert events[0].reason == "enable runtime-backed backtests"


def test_runtime_control_flag_route_rejection_records_audit_event(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _create_backtest(
            session,
            name="runtime_pending",
            status="RUNNING",
            execution_owner="runtime_v2",
        )

    enable_response = client.patch(
        f"/api/v2/runtime/control/flags/{BACKTEST_RUNTIME_V2_FLAG_KEY}",
        json={
            "enabled": True,
            "actor": "release-manager",
            "reason": "enable runtime-backed backtests",
        },
    )
    assert enable_response.status_code == 200, enable_response.json()

    reject_response = client.patch(
        f"/api/v2/runtime/control/flags/{BACKTEST_RUNTIME_V2_FLAG_KEY}",
        json={
            "enabled": False,
            "actor": "release-manager",
            "reason": "rollback to legacy path",
        },
    )
    assert reject_response.status_code == 400, reject_response.json()
    assert reject_response.json()["code"] == "runtime_flag_change_rejected"

    with session_factory() as session:
        service = RuntimeControlService(session)
        flag = service.get_flag(BACKTEST_RUNTIME_V2_FLAG_KEY)
        events = service.list_flag_events(BACKTEST_RUNTIME_V2_FLAG_KEY).items
        assert flag.enabled is True
        assert [event.result for event in events] == ["rejected", "applied"]
        assert "rollback to legacy path" in events[0].reason
        assert "runtime_v2 backtests exist" in events[0].reason
