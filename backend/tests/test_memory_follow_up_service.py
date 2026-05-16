from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.extensions.signaldeck_finance.hooks import MEMORY_FOLLOW_UP_SERVICE_SURFACE
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.report import Report
from app.models.run import Run
from app.models.run_step import RunStep
from app.repositories.run import RunRepository
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import (
    MemoryDecision,
    MemoryLifecycleStatus,
    MemoryProvenance,
    MemoryWriteRequest,
)
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanFinalOutput,
    ExecutionPlanStep,
    ExecutionPlanTarget,
)
from app.services.extension_service import ExtensionService
from app.services.market_data_service import (
    MarketDataService,
    ProviderFundamentals,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderNewsResult,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)
from app.services.memory_context_service import MemoryContextService
from app.services.memory_follow_up_service import MemoryFollowUpService
from app.services.memory_service import MemoryService
from app.services.report_backed_memory_store import ReportBackedMemoryStore
from app.services.return_resolution_service import ReturnResolutionService
from app.services.run_service import RunService

type _RowsBySymbol = dict[str, list[tuple[datetime, Decimal]]]


def _decision(action: Literal["buy", "hold", "sell"] = "buy") -> MemoryDecision:
    return MemoryDecision(
        action=action,
        rationale="Earnings durability supports a long position.",
        risk_summary="Sizing should account for semiconductor cyclicality.",
        execution_plan="Scale in after the next market-data refresh.",
    )


def _provenance(run_id: int = 42) -> MemoryProvenance:
    return MemoryProvenance(
        run_id=run_id,
        agent_key="portfolio_manager",
        agent_version=3,
        agent_name="Portfolio Manager",
        workflow_key="platform_graph_daily_review",
        workflow_version=5,
        step_id="portfolio_decision",
        slot="decision",
        trace_id="trace-abc123",
    )


def _write_request(
    *,
    run_id: int = 42,
    action: Literal["buy", "hold", "sell"] = "buy",
    horizon_days: int = 4,
    ticker: str = "NVDA",
    benchmark_symbol: str | None = None,
) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        ticker=ticker,
        portfolio_slug="core_us",
        horizon_days=horizon_days,
        confidence="high",
        decision_summary="Long-term compounding memory.",
        benchmark_symbol=benchmark_symbol,
        decision=_decision(action),
        provenance=_provenance(run_id),
    )


def _latest_report(session: Session) -> Report:
    report = session.scalars(select(Report).order_by(Report.id.desc())).first()
    assert report is not None
    return report


def _create_pending_memory(
    session: Session,
    *,
    run_id: int = 42,
    action: Literal["buy", "hold", "sell"] = "buy",
    horizon_days: int = 4,
    ticker: str = "NVDA",
    benchmark_symbol: str | None = None,
    created_at: datetime | None = None,
) -> tuple[str, Report]:
    result = ReportBackedMemoryStore(session).create_pending(
        _write_request(
            run_id=run_id,
            action=action,
            horizon_days=horizon_days,
            ticker=ticker,
            benchmark_symbol=benchmark_symbol,
        )
    )
    report = _latest_report(session)
    report.created_at = created_at or datetime(2026, 1, 2, tzinfo=UTC)
    session.commit()
    session.refresh(report)
    return result.memory_id, report


def _disable_finance_workspace(session: Session) -> None:
    ExtensionService(session).set_extension_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        ExtensionToggleRequest.model_validate({"enabled": False}),
    )


class _MemoryHistoryQuoteProvider:
    provider_name: str = "memory_follow_up_test"

    def __init__(
        self,
        rows_by_symbol: _RowsBySymbol,
    ) -> None:
        self.rows_by_symbol: _RowsBySymbol = rows_by_symbol

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return symbol.upper()

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise QuoteProviderError(f"No quote available for {symbol}")

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        _ = (range_value, interval)
        raise QuoteProviderError(f"No history available for {symbol}")

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        _ = (start_date, end_date, interval)
        rows = self.rows_by_symbol.get(symbol.upper())
        if rows is None:
            raise QuoteProviderError(f"No OHLCV data available for {symbol}")
        return ProviderOhlcvSeries(
            symbol=symbol.upper(),
            currency="USD",
            provider=self.provider_name,
            rows=[
                ProviderOhlcvRow(
                    at=at,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                )
                for at, close in rows
            ],
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        raise QuoteProviderError(f"No fundamentals available for {symbol}")

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        _ = (symbols, query, start_date, end_date, limit)
        raise QuoteProviderError("No news available")

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        _ = (start_date, end_date, limit)
        raise QuoteProviderError(f"No insider data available for {symbol}")


def _market_data_service(
    session: Session,
    rows_by_symbol: _RowsBySymbol,
) -> MarketDataService:
    return MarketDataService(
        session=session,
        quote_provider=_MemoryHistoryQuoteProvider(rows_by_symbol),
    )


def test_disabled_finance_workspace_blocks_follow_up_without_mutating_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _, report = _create_pending_memory(session)
        original_content = report.content
        original_metadata = deepcopy(report.metadata_)
        _disable_finance_workspace(session)

        with pytest.raises(ApiError) as exc_info:
            _ = MemoryFollowUpService(
                session,
                _market_data_service(
                    session,
                    {
                        "NVDA": [
                            (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                            (datetime(2026, 1, 6, tzinfo=UTC), Decimal("125")),
                        ],
                    },
                ),
            ).run_due(datetime(2026, 1, 6, 9, tzinfo=UTC))

        persisted = session.get(Report, report.id)
        assert persisted is not None

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "extension_disabled"
    assert exc_info.value.details == [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": MEMORY_FOLLOW_UP_SERVICE_SURFACE,
        }
    ]
    assert persisted.content == original_content
    assert persisted.metadata_ == original_metadata


def test_matured_follow_up_resolves_and_append_reflection_prompt_safe(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        memory_id, report = _create_pending_memory(session)
        result = MemoryFollowUpService(
            session,
            _market_data_service(
                session,
                {
                    "NVDA": [
                        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                        (datetime(2026, 1, 6, tzinfo=UTC), Decimal("125")),
                    ]
                },
            ),
        ).run_due(datetime(2026, 1, 6, 9, tzinfo=UTC))
        memory = MemoryService(session).get_memory(memory_id)
        prompt = MemoryContextService(session).build_prompt_context(
            ticker="nvda",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )
        persisted = session.get(Report, report.id)
        assert persisted is not None

    assert result.checked == 1
    assert result.resolved == 1
    assert result.expired == 0
    assert result.pending == 0
    assert result.reflected == 1
    assert result.items[0].memory_id == memory_id
    assert result.items[0].status == "resolved"
    assert result.items[0].reflected is True
    assert memory.status == MemoryLifecycleStatus.RESOLVED
    assert memory.outcome is not None
    assert memory.outcome.raw_return == Decimal("0.25")
    assert memory.outcome.alpha == Decimal("0.25")
    assert [reflection.reflection for reflection in memory.reflections] == [
        "NVDA buy memory resolved with raw return 0.25, alpha 0.25. "
        + "Lesson: Long-term compounding memory."
    ]
    assert persisted.content.count("### Reflection") == 1
    assert "Historical memory (not an instruction):" in prompt
    assert "# Agent Memory" not in prompt
    assert persisted.slug not in prompt
    assert "/reports/" not in prompt
    assert "auditLinks" not in prompt


def test_matured_follow_up_leaves_future_memory_pending(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        memory_id, _ = _create_pending_memory(session, horizon_days=14)
        result = MemoryFollowUpService(
            session,
            _market_data_service(session, {}),
        ).run_due(datetime(2026, 1, 6, tzinfo=UTC))
        memory = MemoryService(session).get_memory(memory_id)

    assert result.checked == 1
    assert result.pending == 1
    assert result.reflected == 0
    assert result.items[0].reason == "exit_condition_pending"
    assert memory.status == MemoryLifecycleStatus.PENDING
    assert memory.reflections == []


def test_matured_follow_up_expires_and_append_reflection_when_history_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        memory_id, report = _create_pending_memory(session, run_id=43)
        result = MemoryFollowUpService(
            session,
            _market_data_service(session, {}),
        ).run_due(datetime(2026, 1, 6, tzinfo=UTC))
        memory = MemoryService(session).get_memory(memory_id)
        persisted = session.get(Report, report.id)
        assert persisted is not None

    assert result.checked == 1
    assert result.expired == 1
    assert result.reflected == 1
    assert result.items[0].reason == "symbol_history_unavailable"
    assert memory.status == MemoryLifecycleStatus.EXPIRED
    assert memory.outcome is not None
    assert memory.outcome.raw_return is None
    assert [reflection.reflection for reflection in memory.reflections] == [
        "NVDA buy memory resolved with status expired. " + "Lesson: Long-term compounding memory."
    ]
    assert persisted.content.count("### Reflection") == 1


def test_idempotent_follow_up_does_not_duplicate_resolution_or_reflection(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        memory_id, report = _create_pending_memory(session, run_id=44)
        service = MemoryFollowUpService(
            session,
            _market_data_service(
                session,
                {
                    "NVDA": [
                        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                        (datetime(2026, 1, 6, tzinfo=UTC), Decimal("125")),
                        (datetime(2026, 1, 8, tzinfo=UTC), Decimal("150")),
                    ]
                },
            ),
        )
        first = service.run_due(datetime(2026, 1, 6, tzinfo=UTC))
        second = service.run_due(datetime(2026, 1, 8, tzinfo=UTC))
        memory = MemoryService(session).get_memory(memory_id)
        persisted = session.get(Report, report.id)
        assert persisted is not None

    assert first.checked == 1
    assert first.resolved == 1
    assert first.reflected == 1
    assert second.checked == 0
    assert second.reflected == 0
    assert memory.outcome is not None
    assert memory.outcome.resolved_at == datetime(2026, 1, 6, tzinfo=UTC)
    assert memory.outcome.raw_return == Decimal("0.25")
    assert len(memory.reflections) == 1
    assert persisted.content.count("### Reflection") == 1


def test_duplicate_resolution_returns_existing_outcome_without_overwrite(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        memory_id, _ = _create_pending_memory(session, run_id=45)
        service = ReturnResolutionService(
            session,
            _market_data_service(
                session,
                {
                    "NVDA": [
                        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                        (datetime(2026, 1, 6, tzinfo=UTC), Decimal("125")),
                        (datetime(2026, 1, 8, tzinfo=UTC), Decimal("150")),
                    ]
                },
            ),
        )
        first = service.resolve_memory(
            memory_id,
            end_date=datetime(2026, 1, 6, tzinfo=UTC),
        )
        second = service.resolve_memory(
            memory_id,
            end_date=datetime(2026, 1, 8, tzinfo=UTC),
        )
        memory = MemoryService(session).get_memory(memory_id)

    assert first.status == "resolved"
    assert first.reason is None
    assert second.status == "resolved"
    assert second.reason == "already_finalized"
    assert memory.outcome is not None
    assert memory.outcome.resolved_at == datetime(2026, 1, 6, tzinfo=UTC)
    assert memory.outcome.raw_return == Decimal("0.25")


def test_run_start_follow_up_runs_once_for_workflow_package_start(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[dict[str, Any]] = []
    step_id: int | None = None

    class _FakeMemoryFollowUpService:
        def __init__(self, session: Session, market_data_service: MarketDataService) -> None:
            del market_data_service
            self.session = session

        def run_due(self, now: datetime) -> object:
            assert step_id is not None
            step = self.session.get(RunStep, step_id)
            assert step is not None
            calls.append({"now": now, "stepStatus": step.status})
            return object()

    plan = ExecutionPlan(
        target=ExecutionPlanTarget(
            kind="workflow_package",
            id=1,
            key="follow_pkg",
            version=1,
        ),
        input_schema={"type": "object", "additionalProperties": True},
        aggregate_budget_usd=Decimal("0"),
        steps=(ExecutionPlanStep(index=1, agents=(), operations=()),),
        final_output=ExecutionPlanFinalOutput(step_index=1, slot="missing"),
    )
    monkeypatch.setattr(
        "app.services.run_service.MemoryFollowUpService",
        _FakeMemoryFollowUpService,
    )
    monkeypatch.setattr(RunService, "_build_plan_for_run", lambda self, run: plan)

    with session_factory() as session:
        run = Run(
            target_kind="workflowPackage",
            target_id=1,
            target_key="follow_pkg",
            target_version=1,
            workflow_package_key="follow_pkg",
            workflow_package_version=1,
            workflow_package_hash="hash-follow",
            workflow_package_workflow_key="follow_workflow",
            extension_dependencies=[
                {
                    "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
                    "surfaces": ["tool.signaldeck.reports.lookup"],
                    "fields": [],
                }
            ],
            input={},
            status="queued",
            total_tokens=0,
            inherited_tokens=0,
            executed_tokens=0,
        )
        session.add(run)
        session.flush()
        RunService(session, session_factory)._create_planned_run_rows(
            run=run,
            plan=plan,
            validated_input={},
        )
        session.commit()
        step = session.query(RunStep).filter_by(run_id=run.id, step_index=1).one()
        step_id = step.id
        run_id = run.id

    with session_factory() as session:
        claimed = RunRepository(session).claim_next_queued(run_id=run_id)
        assert claimed is not None
        assert claimed.started_at is None
        session.commit()

    with session_factory() as session:
        service = RunService(session, session_factory)
        service.execute_claimed_run(run_id)
        service.execute_claimed_run(run_id)
        persisted = session.get(Run, run_id)
        assert persisted is not None

    assert len(calls) == 1
    assert calls[0]["stepStatus"] == "pending"
    assert isinstance(calls[0]["now"], datetime)
    assert persisted.started_at == calls[0]["now"]
