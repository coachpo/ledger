from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.langgraph.runner import BacktestLangGraphResult
from app.models.agent_spec import AgentSpec
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.report import Report
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.text_template import TextTemplate
from app.models.trading_operation import TradingOperation
from app.models.workflow_spec import WorkflowSpec
from app.schemas.backtest import TradeDecision
from app.services.backtest_engine import BacktestEngine
from app.services.backtest_runtime_adapter import BacktestRuntimeAdapter
from app.services.execution_adapters import BacktestLangGraphExecutionAdapter


def _build_agent_spec(*, key: str, version: int = 1) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status="ACTIVE",
        name=f"{key} v{version}",
        instructions=f"Instructions for {key}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_workflow_spec(
    *,
    agent_key: str,
    key: str,
    version: int = 1,
    execution_mode: str,
    default_tool_ids: list[str] | None = None,
    connector_ids: list[str] | None = None,
) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin="managed",
        status="ACTIVE",
        name=f"{key} v{version}",
        graph_definition={
            "entryStepKey": "analysis",
            "steps": [
                {
                    "stepKey": "analysis",
                    "agentSpecKey": agent_key,
                    "agentSpecVersion": 1,
                }
            ],
        },
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        mention_policy={"version": 1, "allowCharacters": False, "allowedBuiltinHandles": []},
        execution_mode=execution_mode,
        default_tool_ids=list(default_tool_ids or []),
        allowed_capability_bundle_keys=[],
        connector_ids=list(connector_ids or []),
        review_mode=None,
        approval_policy_overrides=[],
    )


class StaticQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol} Holdings"

    def download_history(self, symbol: str, start: date, end: date) -> list[dict[str, object]]:
        _ = (symbol, start, end)
        return []


class RecordingRunner:
    def __init__(self, result: BacktestLangGraphResult) -> None:
        self.result = result
        self.requests: list[Any] = []

    def run_cycle(self, request: Any) -> BacktestLangGraphResult:
        self.requests.append(request)
        return self.result


@dataclass(frozen=True)
class BacktestRuntimeFixture:
    backtest_id: int
    workflow_key: str
    cycle_date: date
    schedule: tuple[date, ...]
    prompt_report_slug: str
    prompt_report_content: str
    cycle_ctx: dict[str, Any]
    engine: BacktestEngine


def _create_runtime_fixture(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    *,
    key_prefix: str,
    workflow_key: str,
    execution_mode: str,
    schedule: tuple[date, ...],
    default_tool_ids: list[str] | None = None,
    connector_ids: list[str] | None = None,
) -> BacktestRuntimeFixture:
    cycle_date = schedule[0]
    prompt_report_content = f"# Prompt\n\nOriginal prompt for {key_prefix}."
    agent_key = f"{key_prefix}_runtime_backtest_agent"
    with session_factory() as session:
        session.add(_build_agent_spec(key=agent_key, version=1))
        session.add(
            _build_workflow_spec(
                agent_key=agent_key,
                key=workflow_key,
                execution_mode=execution_mode,
                default_tool_ids=default_tool_ids,
                connector_ids=connector_ids,
            )
        )

        portfolio = Portfolio(
            name=f"{key_prefix} Portfolio",
            slug=f"{key_prefix}_portfolio",
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
        template = TextTemplate(name=f"{key_prefix} Template", content="# Runtime Adapter")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name=f"{key_prefix} Backtest",
            orchestration_pattern_key="seeded_internal_backtest_v1",
            workflow_spec_key=workflow_key,
            workflow_spec_version=1,
            execution_owner="runtime_v2",
            status="RUNNING",
            frequency="DAILY",
            start_date=schedule[0],
            end_date=schedule[-1],
            total_cycles=len(schedule),
            completed_cycles=0,
            template_id=template.id,
            webhook_url="internal://ledger",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=[],
            results={
                "_run_state": {
                    "schedule": [scheduled.isoformat() for scheduled in schedule],
                    "benchmark_history": {},
                    "trade_log": [],
                    "equity_points": [],
                }
            },
        )
        session.add(backtest)
        session.flush()

        prompt_report_slug = f"prompt_{key_prefix}_{cycle_date.strftime('%Y%m%d')}"
        prompt_report = Report(
            name=prompt_report_slug,
            slug=prompt_report_slug,
            source="external",
            content=prompt_report_content,
            metadata_={
                "tags": ["backtest", f"backtest_{backtest.id}", "prompt"],
                "analysis": {
                    "backtestId": backtest.id,
                    "cycleDate": cycle_date.isoformat(),
                    "reviewType": "backtest_prompt",
                },
            },
        )
        session.add(prompt_report)
        session.commit()
        session.refresh(backtest)
        session.expunge(backtest)

    engine = BacktestEngine(
        backtest=backtest,
        session_factory=session_factory,
        settings=SimpleNamespace(market_data_cache_dir=str(tmp_path)),
        quote_provider=StaticQuoteProvider(),
    )
    cycle_ctx = {
        "prompt_report_slug": prompt_report_slug,
        "market_data": {
            "AAPL": {
                "open": Decimal("10.00"),
                "high": Decimal("12.00"),
                "low": Decimal("9.50"),
                "close": Decimal("11.00"),
                "volume": Decimal("1000"),
            }
        },
        "authored_entry_prompt_body": "",
        "compiled_entry_prompt_body": f"# compiled {key_prefix}",
        "execution_context_body": f"# context {key_prefix}",
        "full_user_prompt": f"# context {key_prefix}\n\n# compiled {key_prefix}",
    }
    return BacktestRuntimeFixture(
        backtest_id=backtest.id,
        workflow_key=workflow_key,
        cycle_date=cycle_date,
        schedule=schedule,
        prompt_report_slug=prompt_report_slug,
        prompt_report_content=prompt_report_content,
        cycle_ctx=cycle_ctx,
        engine=engine,
    )


def _build_runtime_run(
    *,
    backtest_id: int,
    workflow_key: str,
    cycle_date: date,
    attempt_number: int,
    status: str,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type="backtest",
        caller_id=backtest_id,
        execution_kind="workflow",
        workflow_spec_key=workflow_key,
        workflow_spec_version=1,
        agent_spec_key=None,
        agent_spec_version=None,
        caller_scope_key=cycle_date.isoformat(),
        caller_identity_key=None,
        attempt_number=attempt_number,
        status=status,
        input_hash="z" * 64,
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


def _adapter_with_runner(
    session: Session,
    session_factory: sessionmaker[Session],
    runner: RecordingRunner,
) -> BacktestRuntimeAdapter:
    return BacktestRuntimeAdapter(
        session,
        session_factory,
        execution_adapter_factory=lambda current_session: BacktestLangGraphExecutionAdapter(
            current_session,
            runner_factory=lambda _: cast(Any, runner),
        ),
    )


def test_execute_cycle_first_pass_success_finalizes_backtest_and_persists_runtime_artifacts(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="first_pass",
        workflow_key="runtime_backtest_first_pass",
        execution_mode="structured_output",
        schedule=(date(2024, 1, 2),),
    )
    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Analysis\n\nBuy AAPL.",
            decisions=[
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=1,
                    reasoning="Frozen conviction.",
                )
            ],
            tool_call_trace=[],
            approval_trace="not_required",
        )
    )

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        result = adapter.execute_cycle(
            backtest_id=fixture.backtest_id,
            cycle_date=fixture.cycle_date,
            cycle_ctx=fixture.cycle_ctx,
            engine=fixture.engine,
        )

    assert result.run.status == "SUCCEEDED"
    assert result.completion is not None
    assert result.completion.finished is True
    assert result.artifact.prompt_report_slug == fixture.prompt_report_slug
    assert (
        result.artifact.compiled_entry_prompt_body
        == fixture.cycle_ctx["compiled_entry_prompt_body"]
    )
    assert result.artifact.report_markdown == "# Analysis\n\nBuy AAPL."
    assert runner.requests[0].prompt_report == fixture.prompt_report_content

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.status == "COMPLETED"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id == result.run.run_id
        assert backtest.completed_cycles == 1
        assert backtest.results is not None
        assert len(backtest.results["trades"]) == 1

        report = session.scalar(
            select(Report).where(Report.slug == f"backtest_{fixture.backtest_id}_20240102")
        )
        assert report is not None
        assert report.content == "# Analysis\n\nBuy AAPL."

        operations = list(
            session.scalars(
                select(TradingOperation).where(TradingOperation.backtest_id == fixture.backtest_id)
            )
        )
        assert len(operations) == 1
        assert operations[0].backtest_id == fixture.backtest_id


def test_execute_cycle_uses_public_store_cycle_report_helper(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="public_report_helper",
        workflow_key="runtime_backtest_public_report_helper",
        execution_mode="structured_output",
        schedule=(date(2024, 1, 2),),
    )
    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Public Helper Analysis\n\nUse the public helper.",
            decisions=[],
            tool_call_trace=[],
            approval_trace="not_required",
        )
    )
    original_private_store = fixture.engine._store_cycle_report
    public_store_calls: list[tuple[date, str]] = []

    def fail_private_store(cycle_date: date, analysis: str) -> str:
        _ = (cycle_date, analysis)
        raise AssertionError("private cycle report helper should not be called")

    def public_store(cycle_date: date, analysis: str) -> str:
        public_store_calls.append((cycle_date, analysis))
        return original_private_store(cycle_date, analysis)

    fixture.engine._store_cycle_report = fail_private_store
    fixture.engine.store_cycle_report = public_store

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        result = adapter.execute_cycle(
            backtest_id=fixture.backtest_id,
            cycle_date=fixture.cycle_date,
            cycle_ctx=fixture.cycle_ctx,
            engine=fixture.engine,
        )

    assert result.run.status == "SUCCEEDED"
    assert public_store_calls == [
        (fixture.cycle_date, "# Public Helper Analysis\n\nUse the public helper.")
    ]

    with session_factory() as session:
        report = session.scalar(
            select(Report).where(Report.slug == f"backtest_{fixture.backtest_id}_20240102")
        )
        assert report is not None
        assert report.content == "# Public Helper Analysis\n\nUse the public helper."


def test_resume_success_reuses_frozen_inputs_and_dispatches_next_cycle(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    schedule = (date(2024, 1, 2), date(2024, 1, 3))
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="resume",
        workflow_key="runtime_backtest_resume",
        execution_mode="tool_enabled",
        schedule=schedule,
        default_tool_ids=["ledger.report_lookup"],
        connector_ids=["ledger.mcp.market_data"],
    )
    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Resume Analysis\n\nFrozen prompt still applies.",
            decisions=[
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=1,
                    reasoning="Approved after pause.",
                )
            ],
            tool_call_trace=[],
            approval_trace="approved",
        )
    )
    dispatches: list[tuple[int, date]] = []

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        initial = adapter.execute_cycle(
            backtest_id=fixture.backtest_id,
            cycle_date=fixture.cycle_date,
            cycle_ctx=fixture.cycle_ctx,
            engine=fixture.engine,
        )
        assert initial.run.status == "WAITING_APPROVAL"
        assert initial.completion is None
        assert runner.requests == []

        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.current_run_id == initial.run.run_id
        assert backtest.last_completed_run_id is None

        approval = session.scalar(
            select(RuntimeApproval).where(RuntimeApproval.run_id == initial.run.run_id)
        )
        assert approval is not None
        approval.status = "APPROVED"
        approval.actor = "tester"
        approval.reason = "approved"
        approval.resolved_at = utcnow()
        session.commit()

    with session_factory() as session:
        prompt_report = session.scalar(
            select(Report).where(Report.slug == fixture.prompt_report_slug)
        )
        assert prompt_report is not None
        prompt_report.content = "# MUTATED\n\nThis should not be used."
        session.commit()

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        resumed = adapter.resume_run(
            initial.run.run_id,
            engine=fixture.engine,
            dispatch_next_cycle=lambda backtest_id, cycle_date: dispatches.append(
                (backtest_id, cycle_date)
            ),
        )

    assert resumed.run.status == "SUCCEEDED"
    assert resumed.completion is not None
    assert resumed.completion.finished is False
    assert resumed.completion.next_cycle_date == schedule[1]
    assert dispatches == [(fixture.backtest_id, schedule[1])]
    assert runner.requests[0].prompt_report == fixture.prompt_report_content

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.status == "RUNNING"
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id == initial.run.run_id
        assert backtest.completed_cycles == 1
        assert backtest.results is not None
        run_state = backtest.results["_run_state"]
        assert len(run_state["trade_log"]) == 1
        assert len(run_state["equity_points"]) == 1


def test_retry_success_reuses_frozen_inputs_and_artifacts(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="retry",
        workflow_key="runtime_backtest_retry",
        execution_mode="structured_output",
        schedule=(date(2024, 1, 2),),
    )

    class RaisingRunner:
        def run_cycle(self, request: Any) -> BacktestLangGraphResult:
            _ = request
            raise RuntimeError("retry me")

    with session_factory() as session:
        adapter = BacktestRuntimeAdapter(
            session,
            session_factory,
            execution_adapter_factory=lambda current_session: BacktestLangGraphExecutionAdapter(
                current_session,
                runner_factory=lambda _: cast(Any, RaisingRunner()),
            ),
        )
        with pytest.raises(RuntimeError, match="retry me"):
            adapter.execute_cycle(
                backtest_id=fixture.backtest_id,
                cycle_date=fixture.cycle_date,
                cycle_ctx=fixture.cycle_ctx,
                engine=fixture.engine,
            )

    with session_factory() as session:
        failed_run = session.scalar(
            select(RuntimeRun)
            .where(RuntimeRun.caller_id == fixture.backtest_id)
            .order_by(RuntimeRun.id.desc())
        )
        assert failed_run is not None

    with session_factory() as session:
        prompt_report = session.scalar(
            select(Report).where(Report.slug == fixture.prompt_report_slug)
        )
        assert prompt_report is not None
        prompt_report.content = "# MUTATED\n\nRetry should still use frozen prompt."
        session.commit()

    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Retry Analysis\n\nRecovered from the first failure.",
            decisions=[
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=1,
                    reasoning="Retry path succeeded.",
                )
            ],
            tool_call_trace=[],
            approval_trace="not_required",
        )
    )
    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        retried = adapter.retry_run(failed_run.id, engine=fixture.engine)

    assert retried.run.status == "SUCCEEDED"
    assert retried.run.attempt_number == 2
    assert retried.completion is not None
    assert retried.completion.finished is True
    assert runner.requests[0].prompt_report == fixture.prompt_report_content

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.current_run_id is None
        assert backtest.last_completed_run_id == retried.run.run_id


def test_replaying_completed_run_rejects_duplicate_completion_without_extra_side_effects(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="duplicate",
        workflow_key="runtime_backtest_duplicate",
        execution_mode="structured_output",
        schedule=(date(2024, 1, 2),),
    )
    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Duplicate Analysis\n\nDo this once.",
            decisions=[
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=1,
                    reasoning="Single execution only.",
                )
            ],
            tool_call_trace=[],
            approval_trace="not_required",
        )
    )

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        result = adapter.execute_cycle(
            backtest_id=fixture.backtest_id,
            cycle_date=fixture.cycle_date,
            cycle_ctx=fixture.cycle_ctx,
            engine=fixture.engine,
        )

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.results is not None
        initial_trade_count = len(backtest.results["trades"])

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        with pytest.raises(ApiError, match="already consumed"):
            adapter._complete_if_succeeded(
                backtest_id=fixture.backtest_id,
                run_id=result.run.run_id,
                engine=fixture.engine,
                dispatch_next_cycle=None,
            )

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.results is not None
        assert len(backtest.results["trades"]) == initial_trade_count
        assert backtest.completed_cycles == 1


def test_stale_runtime_run_rejection_blocks_completion_side_effects(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    schedule = (date(2024, 1, 2), date(2024, 1, 3))
    fixture = _create_runtime_fixture(
        session_factory,
        tmp_path,
        key_prefix="stale",
        workflow_key="runtime_backtest_stale",
        execution_mode="structured_output",
        schedule=schedule,
    )
    runner = RecordingRunner(
        BacktestLangGraphResult(
            report_content="# Stale Analysis\n\nFirst cycle only.",
            decisions=[
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=1,
                    reasoning="Complete once before stale check.",
                )
            ],
            tool_call_trace=[],
            approval_trace="not_required",
        )
    )

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        first = adapter.execute_cycle(
            backtest_id=fixture.backtest_id,
            cycle_date=fixture.cycle_date,
            cycle_ctx=fixture.cycle_ctx,
            engine=fixture.engine,
        )

    with session_factory() as session:
        pending_run = _build_runtime_run(
            backtest_id=fixture.backtest_id,
            workflow_key=fixture.workflow_key,
            cycle_date=schedule[1],
            attempt_number=2,
            status="WAITING_APPROVAL",
        )
        session.add(pending_run)
        session.flush()
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        backtest.current_run_id = pending_run.id
        backtest.last_completed_run_id = None
        session.commit()

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.results is not None
        initial_trade_count = len(backtest.results["_run_state"]["trade_log"])

    with session_factory() as session:
        adapter = _adapter_with_runner(session, session_factory, runner)
        with pytest.raises(ApiError, match="stale"):
            adapter._complete_if_succeeded(
                backtest_id=fixture.backtest_id,
                run_id=first.run.run_id,
                engine=fixture.engine,
                dispatch_next_cycle=None,
            )

    with session_factory() as session:
        backtest = session.get(Backtest, fixture.backtest_id)
        assert backtest is not None
        assert backtest.results is not None
        assert len(backtest.results["_run_state"]["trade_log"]) == initial_trade_count
