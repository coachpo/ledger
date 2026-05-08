from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.report import Report
from app.schemas.memory import (
    INVALID_MEMORY_ID_CODE,
    MEMORY_NOT_FOUND_CODE,
    MemoryDecision,
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
)
from app.schemas.memory_report import AGENT_MEMORY_REVIEW_TYPE, AGENT_MEMORY_VERSION_GROUP
from app.services.report_backed_memory_store import ReportBackedMemoryStore


def _decision() -> MemoryDecision:
    return MemoryDecision(
        action="buy",
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


def _write_request(run_id: int = 42) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        ticker=" nvda ",
        portfolio_slug=" core_us ",
        horizon_days=14,
        confidence=" high ",
        decision_summary="Long-term compounding memory.",
        benchmark_symbol=" spy ",
        decision=_decision(),
        provenance=_provenance(run_id),
    )


def _outcome() -> MemoryOutcome:
    return MemoryOutcome(
        resolved_status="resolved",
        resolved_at=datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
        raw_return=Decimal("0.125"),
        benchmark_return=Decimal("0.030"),
        alpha=Decimal("0.095"),
    )


def _reflection() -> MemoryReflection:
    return MemoryReflection(
        reflection="Outcome confirmed the liquidity gate.",
        reflected_at=datetime(2026, 1, 18, 8, tzinfo=UTC),
    )


def _reports(session: Session) -> list[Report]:
    return list(session.scalars(select(Report).order_by(Report.id)))


def _valid_memory_metadata(session: Session) -> dict[str, object]:
    result = ReportBackedMemoryStore(session).create_pending(_write_request())
    report = _reports(session)[0]
    metadata = deepcopy(cast(dict[str, object], report.metadata_))
    session.delete(report)
    session.flush()
    assert result.action == "created"
    return metadata


def _insert_report(
    session: Session,
    *,
    source: str,
    metadata: dict[str, object],
    slug: str,
) -> Report:
    report = Report(
        name=slug,
        slug=slug,
        source=source,
        content="# Seed report",
        metadata_=metadata,
    )
    session.add(report)
    session.flush()
    session.refresh(report)
    return report


def test_create_get_round_trip_writes_one_agent_memory_report(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = ReportBackedMemoryStore(session)
        result = store.create_pending(_write_request())
        entry = store.get(result.memory_id)
        reports = _reports(session)

    assert len(reports) == 1
    report = reports[0]
    metadata = cast(dict[str, object], report.metadata_)
    analysis = cast(dict[str, object], metadata["analysis"])
    created_by = cast(dict[str, object], metadata["createdBy"])
    result_payload = result.model_dump(mode="json", by_alias=True)

    assert result.action == "created"
    assert result.memory_id == f"mem_{report.id}"
    assert result.status == MemoryLifecycleStatus.PENDING
    assert result_payload["memoryId"] == f"mem_{report.id}"
    assert "auditLinks" not in result_payload
    assert "reportId" not in result_payload
    assert report.source == "agent"
    assert report.name == report.slug
    assert report.slug.startswith("agent_memory_nvda_portfolio_manager_run_42_buy_")
    assert report.content.startswith("# Agent Memory: NVDA")
    assert metadata["tags"] == [AGENT_MEMORY_REVIEW_TYPE]
    assert analysis["reviewType"] == AGENT_MEMORY_REVIEW_TYPE
    assert analysis["versionGroup"] == AGENT_MEMORY_VERSION_GROUP
    assert analysis["resolvedStatus"] == "pending"
    assert created_by["type"] == "agent"
    assert created_by["runId"] == 42
    assert entry.memory_id == result.memory_id
    assert entry.ticker == "NVDA"
    assert entry.audit_links is None


def test_duplicate_create_returns_existing_action_without_second_report(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = ReportBackedMemoryStore(session)
        first = store.create_pending(_write_request())
        second = store.create_pending(_write_request())
        reports = _reports(session)

    assert len(reports) == 1
    assert first.action == "created"
    assert second.action == "existing"
    assert first.memory_id == second.memory_id


def test_invalid_memory_id_is_rejected_without_report_identity_leaks(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = ReportBackedMemoryStore(session)
        with pytest.raises(ApiError) as exc_info:
            _ = store.get("report_123")

    error = exc_info.value
    serialized = str({"code": error.code, "message": error.message, "details": error.details})
    assert error.code == INVALID_MEMORY_ID_CODE
    assert error.status_code == 400
    assert "report" not in serialized.lower()
    assert "/reports/" not in serialized


@pytest.mark.parametrize(
    ("source", "analysis_updates"),
    [
        ("uploaded", {}),
        ("agent", {"reviewType": "weekly_review"}),
        ("agent", {"versionGroup": "agent_memory/v2"}),
    ],
)
def test_get_rejects_non_memory_reports_without_identity_leaks(
    session_factory: sessionmaker[Session],
    source: str,
    analysis_updates: dict[str, object],
) -> None:
    with session_factory() as session:
        metadata = _valid_memory_metadata(session)
        analysis = cast(dict[str, object], metadata["analysis"])
        analysis.update(analysis_updates)
        report = _insert_report(
            session,
            source=source,
            metadata=metadata,
            slug=f"bad_memory_{source}_{len(analysis_updates)}",
        )
        store = ReportBackedMemoryStore(session)
        with pytest.raises(ApiError) as exc_info:
            _ = store.get(f"mem_{report.id}")
        query = store.query(MemoryQuery(ticker="NVDA", limit=10))
        artifacts = store.list_artifacts_for_run(42)

    error = exc_info.value
    serialized = str({"code": error.code, "message": error.message, "details": error.details})
    assert error.code == MEMORY_NOT_FOUND_CODE
    assert error.message == "Memory not found"
    assert str(report.id) not in serialized
    assert report.slug not in serialized
    assert query == []
    assert artifacts == []


def test_malformed_metadata_is_ignored_by_query_and_rejected_by_get(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _insert_report(
            session,
            source="agent",
            metadata={"analysis": {"reviewType": AGENT_MEMORY_REVIEW_TYPE}},
            slug="malformed_memory",
        )
        store = ReportBackedMemoryStore(session)
        with pytest.raises(ApiError) as exc_info:
            _ = store.get(f"mem_{report.id}")

        assert store.query(MemoryQuery(ticker="NVDA", limit=10)) == []
        assert store.list_artifacts_for_run(42) == []

    assert exc_info.value.code == MEMORY_NOT_FOUND_CODE


def test_missing_resolved_status_maps_to_pending_for_legacy_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        metadata = _valid_memory_metadata(session)
        analysis = cast(dict[str, object], metadata["analysis"])
        _ = analysis.pop("resolvedStatus")
        report = _insert_report(
            session,
            source="agent",
            metadata=metadata,
            slug="legacy_pending_memory",
        )
        entry = ReportBackedMemoryStore(session).get(f"mem_{report.id}")

    assert entry.status == MemoryLifecycleStatus.PENDING
    assert entry.outcome is None
    assert entry.reflections == []


def test_resolve_reflect_and_query_use_memory_dtos_without_report_leaks(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = ReportBackedMemoryStore(session)
        created = store.create_pending(_write_request())
        resolved = store.resolve(created.memory_id, _outcome())
        reflected = store.append_reflection(created.memory_id, _reflection())
        snippets = store.query(MemoryQuery(ticker="NVDA", limit=10, max_characters=10_000))
        persisted = _reports(session)[0]

    assert resolved.status == MemoryLifecycleStatus.RESOLVED
    assert reflected.reflections[0].reflection == "Outcome confirmed the liquidity gate."
    assert snippets[0].memory_id == created.memory_id
    assert snippets[0].text.startswith("Historical memory, not an instruction:")
    assert "# Agent Memory" not in snippets[0].text
    assert persisted.slug not in snippets[0].text
    assert "Report ID" not in snippets[0].text
    assert "reportId" not in str(snippets[0].model_visible_dump())
    assert persisted.name not in snippets[0].model_visible_dump().values()
    assert "auditLinks" not in snippets[0].model_visible_dump()


def test_audit_links_are_nested_only_for_artifact_projection(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = ReportBackedMemoryStore(session)
        created = store.create_pending(_write_request())
        artifacts = store.list_artifacts_for_run(42)
        audit_links = store.audit_links(created.memory_id)
        report = _reports(session)[0]

    assert len(artifacts) == 1
    artifact = artifacts[0]
    ui_payload = artifact.dump_for_projection("ui-visible")
    model_payload = artifact.model_visible_dump()
    ui_audit_links = cast(dict[str, object], ui_payload["auditLinks"])
    ui_report = cast(dict[str, object], ui_audit_links["report"])

    assert artifact.memory_id == created.memory_id
    assert artifact.audit_links is not None
    assert artifact.audit_links.report is not None
    assert artifact.audit_links.report.slug == report.slug
    assert audit_links.report is not None
    assert audit_links.report.name == report.name
    assert ui_report["slug"] == report.slug
    assert ui_report["name"] == report.name
    assert "reportId" not in ui_report
    assert "slug" not in ui_payload
    assert "name" not in ui_payload
    assert "auditLinks" not in model_payload
    assert report.slug not in str(model_payload)
