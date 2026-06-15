from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import override

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
)
from app.extensions.signaldeck_finance.hooks import register_run_lifecycle_hooks
from app.extensions.signaldeck_finance.memory_metadata import (
    FinanceMemoryMetadata,
    read_finance_memory_metadata,
    write_finance_memory_metadata,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.agent_memory import AgentMemoryEntry, RunMemoryEvent
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.signaldeck_finance_memory_metadata import SignalDeckFinanceMemoryMetadata
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import MemoryProvenance, MemoryScope, MemoryScopeType, MemoryWriteRequest
from app.schemas.memory_report import AGENT_MEMORY_REVIEW_TYPE, AGENT_MEMORY_VERSION_GROUP
from app.services.extension_service import ExtensionService
from app.services.memory_follow_up_service import MemoryFollowUpService
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.quote_provider import (
    ProviderFundamentals,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderNewsResult,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
)
from app.services.run_lifecycle import WorkflowPackageStartContext


class _NoopQuoteProvider:
    provider_name: str = "noop_follow_up_test"

    def fetch_symbol_name(self, symbol: str) -> str | None:
        del symbol
        return None

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise AssertionError(f"Unexpected quote lookup for {symbol}")

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        raise AssertionError(f"Unexpected history lookup for {symbol}:{range_value}:{interval}")

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        raise AssertionError(
            f"Unexpected OHLCV lookup for {symbol}:{start_date}:{end_date}:{interval}"
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        raise AssertionError(f"Unexpected fundamentals lookup for {symbol}")

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        raise AssertionError(
            f"Unexpected news lookup for {symbols}:{query}:{start_date}:{end_date}:{limit}"
        )

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        raise AssertionError(
            f"Unexpected insider lookup for {symbol}:{start_date}:{end_date}:{limit}"
        )


class _ResolvingQuoteProvider(_NoopQuoteProvider):
    provider_name: str = "resolving_follow_up_test"

    @override
    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        del interval
        exit_close = Decimal("120") if symbol == "NVDA" else Decimal("110")
        return ProviderOhlcvSeries(
            symbol=symbol,
            currency="USD",
            provider=self.provider_name,
            rows=[
                ProviderOhlcvRow(
                    at=start_date,
                    open=Decimal("100"),
                    high=Decimal("100"),
                    low=Decimal("100"),
                    close=Decimal("100"),
                ),
                ProviderOhlcvRow(
                    at=end_date,
                    open=exit_close,
                    high=exit_close,
                    low=exit_close,
                    close=exit_close,
                ),
            ],
        )


def _agent_memory_metadata(run_id: int = 101) -> dict[str, object]:
    return {
        "createdBy": {
            "type": "agent",
            "runId": run_id,
            "agentKey": "analyst",
            "agentVersion": 1,
        },
        "analysis": {
            "reviewType": AGENT_MEMORY_REVIEW_TYPE,
            "versionGroup": AGENT_MEMORY_VERSION_GROUP,
            "ticker": "NVDA",
            "decision": {
                "action": "buy",
                "rationale": "Historical agent-memory report.",
                "riskSummary": "Report rows must not drive follow-up.",
                "executionPlan": "Use core memory events instead.",
            },
            "runId": run_id,
            "agentKey": "analyst",
            "agentVersion": 1,
            "resolvedStatus": "pending",
        },
        "tags": [AGENT_MEMORY_REVIEW_TYPE],
    }


def _insert_legacy_agent_memory_report(session: Session) -> Report:
    report = Report(
        name="legacy_agent_memory_follow_up",
        slug="legacy_agent_memory_follow_up",
        source="agent",
        content="# Historical pending memory\n",
        metadata_=_agent_memory_metadata(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _seed_run(session: Session) -> Run:
    package_key = "memory_follow_up_workflow_package"
    workflow_key = "memory_follow_up_workflow"
    run = Run(
        target_kind="workflowPackage",
        target_id=1,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key=workflow_key,
        input={"ticker": "NVDA"},
        status="succeeded",
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=1,
        workflow_package_key=package_key,
        workflow_package_name="Memory Follow Up Workflow Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key=workflow_key,
        workflow_name="Memory Follow Up Workflow",
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=("apiVersion: signaldeck.workflowPackage/v1\n" f"key: {package_key}\n"),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": workflow_key}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": [workflow_key]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def _provenance(run_id: int) -> MemoryProvenance:
    return MemoryProvenance(
        run_id=run_id,
        agent_key="analyst",
        agent_version=1,
        agent_name="Analyst",
        workflow_key="memory_follow_up_workflow",
        workflow_version=1,
        step_id="decision",
        slot="thesis",
        trace_id="trace-follow-up",
    )


def _neutral_memory_request(run_id: int) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary="Core follow-up note.",
        content="Core follow-up scheduling should not require finance metadata.",
        scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run_id)),
        provenance=_provenance(run_id),
    )


def _finance_metadata() -> FinanceMemoryMetadata:
    return FinanceMemoryMetadata(
        ticker="NVDA",
        action="buy",
        rationale="Demand supports a long position.",
        risk_summary="Watch valuation.",
        execution_plan="Review after the horizon elapses.",
        horizon_days=2,
        benchmark_symbol="SPY",
        decision_summary="Finance evaluator should resolve this decision.",
    )


def _finance_memory_request(run_id: int) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary="Finance evaluator should resolve this decision.",
        content="Demand supports a long position. Watch valuation.",
        scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key="pkg-finance"),
        provenance=_provenance(run_id),
    )


def _set_memory_created_at(session: Session, memory_id: str, created_at: datetime) -> None:
    entry = session.scalar(select(AgentMemoryEntry).where(AgentMemoryEntry.memory_id == memory_id))
    assert entry is not None
    entry.created_at = created_at
    session.flush()


def _disable_finance_workspace(session: Session) -> None:
    _ = ExtensionService(session).set_extension_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        ExtensionToggleRequest(enabled=False),
    )


def _memory_events(session: Session, run_id: int) -> list[RunMemoryEvent]:
    return list(
        session.scalars(
            select(RunMemoryEvent)
            .where(RunMemoryEvent.run_id == run_id)
            .order_by(RunMemoryEvent.id)
        )
    )


def test_finance_extension_registers_optional_memory_follow_up_evaluator() -> None:
    hooks = register_run_lifecycle_hooks()

    assert len(hooks) == 1
    assert hooks[0].extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert hooks[0].on_workflow_package_start is None
    assert hooks[0].memory_follow_up_evaluators is not None


def test_core_follow_up_records_review_event_with_finance_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    reviewed_at = datetime(2026, 1, 6, tzinfo=UTC)
    with session_factory() as session:
        _disable_finance_workspace(session)
        run = _seed_run(session)
        created = MemoryService(session).write_memory(
            capability_references=[],
            payload=_neutral_memory_request(run.id),
        )
        result = MemoryFollowUpService(session).run_due(reviewed_at)
        events = _memory_events(session, run.id)
        reports = list(session.scalars(select(Report)))

    assert reports == []
    assert result.checked == 1
    assert result.made_workflow_visible == 0
    assert result.kept_workflow_hidden == 1
    assert result.reflected == 0
    assert result.items[0].memory_id == created.memory_id
    assert result.items[0].reason == "no_evaluator"
    assert [event.event_type for event in events] == ["written", "reviewed"]
    reviewed = events[-1]
    assert reviewed.memory_id == created.memory_id
    assert reviewed.filters["source"] == "scheduler"
    assert reviewed.filters["actor"] == "core.memory_follow_up"
    assert reviewed.filters["channel"] == "memory_follow_up"
    assert reviewed.result_snapshot == {
        "memoryId": created.memory_id,
        "revisionId": created.revision_id,
        "reviewAction": "follow_up_reviewed",
        "outcomeSummary": "no_evaluator",
    }
    assert reviewed.status_snapshot == {"visibleToWorkflow": False}


def test_finance_evaluator_contribution_resolves_and_reflects_when_enabled(
    session_factory: sessionmaker[Session],
) -> None:
    created_at = datetime(2026, 1, 1, 9, tzinfo=UTC)
    reviewed_at = datetime(2026, 1, 6, tzinfo=UTC)
    with session_factory() as session:
        run = _seed_run(session)
        memory_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key="pkg-finance",
                workflow_key="memory_follow_up_workflow",
                agent_key="analyst",
            ),
        )
        created = memory_service.write_memory(
            capability_references=[],
            payload=_finance_memory_request(run.id),
        )
        write_finance_memory_metadata(session, created.memory_id, _finance_metadata())
        persisted_metadata = read_finance_memory_metadata(session, created.memory_id)
        metadata_row = session.get(SignalDeckFinanceMemoryMetadata, created.memory_id)
        _set_memory_created_at(session, created.memory_id, created_at)
        hooks = register_run_lifecycle_hooks()
        evaluator_factory = hooks[0].memory_follow_up_evaluators
        assert evaluator_factory is not None
        evaluators = evaluator_factory(
            WorkflowPackageStartContext(
                session=session,
                provider_bundle=finance_execution_provider_bundle_from_parts(
                    quote_provider=_ResolvingQuoteProvider()
                ),
                now=reviewed_at,
            )
        )
        result = MemoryFollowUpService(session, evaluators=evaluators).run_due(reviewed_at)
        memory = memory_service.get_memory(created.memory_id)
        events = _memory_events(session, run.id)
        reports = list(session.scalars(select(Report)))

    assert reports == []
    assert persisted_metadata == _finance_metadata()
    assert metadata_row is not None
    assert metadata_row.memory_id == created.memory_id
    assert metadata_row.ticker == "NVDA"
    assert result.checked == 1
    assert result.made_workflow_visible == 1
    assert result.kept_workflow_hidden == 0
    assert result.reflected == 1
    assert result.items[0].memory_id == created.memory_id
    assert result.items[0].reason is None
    assert memory.visible_to_workflow is True
    assert [event.event_type for event in events] == ["written", "reviewed", "reviewed"]
    assert events[1].status_snapshot == {"visibleToWorkflow": True}
    assert events[1].result_snapshot["outcomeSummary"] == (
        "Finance return resolved: raw return 0.2, alpha 0.1, benchmark return 0.1."
    )
    assert events[2].result_snapshot["reviewAction"] == "reflected"
    assert events[2].result_snapshot["reflectionSource"] == "signaldeck.finance.return_resolution"


def test_finance_evaluator_keeps_memory_hidden_when_finance_metadata_missing(
    session_factory: sessionmaker[Session],
) -> None:
    created_at = datetime(2026, 1, 1, 9, tzinfo=UTC)
    reviewed_at = datetime(2026, 1, 6, tzinfo=UTC)
    with session_factory() as session:
        run = _seed_run(session)
        memory_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key="pkg-finance",
                workflow_key="memory_follow_up_workflow",
                agent_key="analyst",
            ),
        )
        created = memory_service.write_memory(
            capability_references=[],
            payload=_finance_memory_request(run.id),
        )
        _set_memory_created_at(session, created.memory_id, created_at)
        hooks = register_run_lifecycle_hooks()
        evaluator_factory = hooks[0].memory_follow_up_evaluators
        assert evaluator_factory is not None
        evaluators = evaluator_factory(
            WorkflowPackageStartContext(
                session=session,
                provider_bundle=finance_execution_provider_bundle_from_parts(
                    quote_provider=_ResolvingQuoteProvider()
                ),
                now=reviewed_at,
            )
        )
        result = MemoryFollowUpService(session, evaluators=evaluators).run_due(reviewed_at)
        memory = memory_service.get_memory(created.memory_id)
        events = _memory_events(session, run.id)

    assert result.checked == 1
    assert result.made_workflow_visible == 0
    assert result.kept_workflow_hidden == 1
    assert result.items[0].memory_id == created.memory_id
    assert result.items[0].reason == "finance_metadata_missing"
    assert memory.visible_to_workflow is False
    assert [event.event_type for event in events] == ["written", "reviewed"]
    assert events[-1].result_snapshot == {
        "memoryId": created.memory_id,
        "revisionId": created.revision_id,
        "reviewAction": "follow_up_reviewed",
        "outcomeSummary": "finance_metadata_missing",
    }
    assert events[-1].status_snapshot == {"visibleToWorkflow": False}


def test_follow_up_service_ignores_legacy_agent_memory_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _insert_legacy_agent_memory_report(session)
        result = MemoryFollowUpService(session).run_due(datetime(2026, 1, 6, tzinfo=UTC))
        persisted = session.scalar(select(Report).where(Report.id == report.id))
        assert persisted is not None

    assert result.checked == 0
    assert result.made_workflow_visible == 0
    assert result.kept_workflow_hidden == 0
    assert result.reflected == 0
    assert result.items == ()
    assert persisted.content == "# Historical pending memory\n"
    assert persisted.metadata_ == _agent_memory_metadata()
