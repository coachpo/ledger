from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
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


def test_runtime_control_service_rejects_unsafe_runtime_backtest_rollback(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _create_backtest(
            session,
            name="runtime_pending",
            status="PENDING",
            execution_owner="runtime_v2",
        )
        _create_backtest(
            session,
            name="runtime_between_cycle",
            status="RUNNING",
            execution_owner="runtime_v2",
        )

    with session_factory() as session:
        service = RuntimeControlService(session)
        enabled_flag = service.set_backtest_runtime_v2_enabled(
            enabled=True,
            actor="release-manager",
            reason="enable runtime-backed backtests",
        )
        assert enabled_flag.enabled is True

        with pytest.raises(ApiError, match="Cannot disable") as exc_info:
            service.set_backtest_runtime_v2_enabled(
                enabled=False,
                actor="release-manager",
                reason="rollback to legacy path",
            )

        assert exc_info.value.code == "runtime_flag_change_rejected"

        flag = service.get_flag(BACKTEST_RUNTIME_V2_FLAG_KEY)
        assert flag.enabled is True

        events = service.list_flag_events(BACKTEST_RUNTIME_V2_FLAG_KEY).items
        assert [event.result for event in events] == ["rejected", "applied"]
        assert events[0].old_enabled is True
        assert events[0].new_enabled is False
        assert "rollback to legacy path" in events[0].reason
        assert "runtime_v2 backtests exist" in events[0].reason


def test_runtime_control_service_applies_safe_runtime_backtest_flag_flips(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _create_backtest(
            session,
            name="runtime_terminal",
            status="FAILED",
            execution_owner="runtime_v2",
        )

    with session_factory() as session:
        service = RuntimeControlService(session)
        enabled_flag = service.set_backtest_runtime_v2_enabled(
            enabled=True,
            actor="release-manager",
            reason="enable runtime-backed backtests",
        )
        disabled_flag = service.set_backtest_runtime_v2_enabled(
            enabled=False,
            actor="release-manager",
            reason="rollback after terminalizing runtime-owned rows",
        )

        assert enabled_flag.enabled is True
        assert disabled_flag.enabled is False

        events = service.list_flag_events(BACKTEST_RUNTIME_V2_FLAG_KEY).items
        assert [event.result for event in events] == ["applied", "applied"]
        assert events[0].old_enabled is True
        assert events[0].new_enabled is False
        assert events[1].old_enabled is False
        assert events[1].new_enabled is True
