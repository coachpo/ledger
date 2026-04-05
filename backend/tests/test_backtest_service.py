from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.orm import Session, sessionmaker

from app.services.backtest_service import BacktestService


def build_service() -> BacktestService:
    return BacktestService(
        cast(Session, SimpleNamespace()),
        cast(sessionmaker[Session], SimpleNamespace()),
    )


def test_run_backtest_launches_cycle_service(monkeypatch) -> None:
    service = build_service()
    calls: list[int] = []

    class FakeCycleService:
        def __init__(self, session: Any, session_factory: Any) -> None:
            assert session is service.session
            assert session_factory is service.session_factory

        def start_backtest(self, backtest_id: int) -> None:
            calls.append(backtest_id)

    class FakeThread:
        def __init__(self, *, target, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    monkeypatch.setattr("app.services.backtest_service.BacktestCycleService", FakeCycleService)
    monkeypatch.setattr("app.services.backtest_service.threading.Thread", FakeThread)

    service.run_backtest(42)

    assert calls == [42]
