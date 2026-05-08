from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability import Capability
from app.models.report import Report
from app.schemas.memory import MemoryDecision, MemoryProvenance, MemoryWriteRequest
from app.services.capability_service import (
    REPORT_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    REPORT_MEMORY_WRITE_TOOL_KEY,
    RuntimeToolGrantError,
)
from app.services.memory_service import MemoryService

_MEMORY_WRITE_CAPABILITY_KEY = "memory_service_test_writer"


def _capability_references(key: str = _MEMORY_WRITE_CAPABILITY_KEY) -> list[dict[str, object]]:
    return [{"capabilityKey": key, "capabilityVersion": 1}]


def _ensure_memory_write_capability(session: Session) -> None:
    existing = session.scalar(
        select(Capability).where(
            Capability.key == _MEMORY_WRITE_CAPABILITY_KEY,
            Capability.version == 1,
        )
    )
    if existing is not None:
        return
    session.add(
        Capability(
            key=_MEMORY_WRITE_CAPABILITY_KEY,
            version=1,
            status="published",
            name="Memory Service Test Writer",
            description="Grants report-memory writes in memory service tests.",
            tool_keys=[REPORT_MEMORY_WRITE_TOOL_KEY],
        )
    )
    session.commit()


def _write_request(run_id: int = 42) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        ticker=" nvda ",
        portfolio_slug=" core_us ",
        horizon_days=14,
        confidence=" high ",
        decision_summary="Long-term compounding memory.",
        benchmark_symbol=" spy ",
        decision=MemoryDecision(
            action="buy",
            rationale="Earnings durability supports a long position.",
            risk_summary="Sizing should account for semiconductor cyclicality.",
            execution_plan="Scale in after the next market-data refresh.",
        ),
        provenance=MemoryProvenance(
            run_id=run_id,
            agent_key="portfolio_manager",
            agent_version=3,
            agent_name="Portfolio Manager",
            workflow_key="platform_graph_daily_review",
            workflow_version=5,
            step_id="portfolio_decision",
            slot="decision",
            trace_id="trace-abc123",
        ),
    )


def _reports(session: Session) -> list[Report]:
    return list(session.scalars(select(Report).order_by(Report.id)))


def test_memory_report_service_boundary_write_memory_requires_grant_and_creates_no_report(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "memory_service_read_only"
    with session_factory() as session:
        session.add(
            Capability(
                key=capability_key,
                version=1,
                status="published",
                name="Read Only Memory Service Capability",
                description="Does not grant memory writes.",
                tool_keys=[REPORT_LOOKUP_TOOL_KEY],
            )
        )
        session.commit()

        with pytest.raises(RuntimeToolGrantError) as exc_info:
            _ = MemoryService(session).write_memory(
                capability_references=_capability_references(capability_key),
                payload=_write_request(),
            )
        reports = _reports(session)

    assert exc_info.value.code == REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE
    assert exc_info.value.message == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert reports == []


def test_memory_report_service_boundary_write_memory_returns_memory_projections(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _ensure_memory_write_capability(session)
        service = MemoryService(session)
        result = service.write_memory(
            capability_references=_capability_references(),
            payload=_write_request(),
        )
        entry = service.get_memory(result.memory_id)
        artifacts = service.list_run_artifacts(42)
        reports = _reports(session)

    assert len(reports) == 1
    assert entry.memory_id == result.memory_id
    assert entry.audit_links is None
    model_payload = result.model_visible_dump()
    assert model_payload["memoryId"] == result.memory_id
    assert "auditLinks" not in model_payload
    assert "reportId" not in model_payload
    assert "reportSlug" not in model_payload
    assert "reportName" not in model_payload

    assert len(artifacts) == 1
    artifact = artifacts[0]
    ui_payload = artifact.dump_for_projection("ui-visible")
    artifact_model_payload = artifact.model_visible_dump()
    audit_links = cast(dict[str, object], ui_payload["auditLinks"])
    report_link = cast(dict[str, object], audit_links["report"])
    assert artifact.memory_id == result.memory_id
    assert report_link["slug"] == reports[0].slug
    assert report_link["name"] == reports[0].name
    assert "reportId" not in report_link
    assert "auditLinks" not in artifact_model_payload
    assert reports[0].slug not in str(artifact_model_payload)


def test_memory_report_service_boundary_rolls_back_write_when_commit_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        _ensure_memory_write_capability(session)

        def failing_commit() -> None:
            session.flush()
            raise RuntimeError("simulated memory service commit failure")

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(RuntimeError, match="simulated memory service commit failure"):
            _ = MemoryService(session).write_memory(
                capability_references=_capability_references(),
                payload=_write_request(run_id=43),
            )

    with session_factory() as session:
        assert _reports(session) == []


def test_memory_report_service_boundary_has_no_new_direct_production_create_call_sites() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    allowed = {Path("app/services/run_service.py")}
    direct_call_re = re.compile(
        r"MemoryReportService\([^)]*\)\.create_pending_report\(",
        re.MULTILINE,
    )
    direct_call_sites: set[Path] = set()

    for path in (backend_root / "app").rglob("*.py"):
        relative = path.relative_to(backend_root)
        if direct_call_re.search(path.read_text(encoding="utf-8")):
            direct_call_sites.add(relative)

    assert direct_call_sites == allowed
