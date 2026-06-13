from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.agent_memory import AgentMemoryEntry, AgentMemoryRevision, RunMemoryEvent
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.schemas.memory import (
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.schemas.memory_report import (
    AGENT_MEMORY_REVIEW_TYPE,
    AGENT_MEMORY_VERSION_GROUP,
    AgentMemoryModelInput,
    AgentMemoryReportMetadata,
    AgentMemoryTrustedCreateContext,
)
from app.services.memory_report_service import MemoryReportService
from app.services.memory_service import MemoryLookupContext, MemoryService


def _decision_payload() -> dict[str, str]:
    return {
        "action": "buy",
        "rationale": "Earnings durability supports a long position.",
        "riskSummary": "Sizing should account for semiconductor cyclicality.",
        "executionPlan": "Scale in after the next market-data refresh.",
    }


def _agent_memory_metadata(*, run_id: int = 101) -> dict[str, object]:
    return {
        "createdBy": {
            "type": "agent",
            "runId": run_id,
            "agentKey": "analyst",
            "agentVersion": 1,
            "agentName": "Analyst",
        },
        "analysis": {
            "reviewType": AGENT_MEMORY_REVIEW_TYPE,
            "versionGroup": AGENT_MEMORY_VERSION_GROUP,
            "ticker": "NVDA",
            "decision": _decision_payload(),
            "runId": run_id,
            "agentKey": "analyst",
            "agentVersion": 1,
            "agentName": "Analyst",
            "resolvedStatus": "resolved",
            "resolvedAt": "2026-01-17T10:30:00Z",
            "rawReturn": "0.125",
            "alpha": "0.095",
        },
        "tags": [AGENT_MEMORY_REVIEW_TYPE],
    }


def _insert_legacy_agent_memory_report(
    session: Session,
    *,
    slug: str = "legacy_agent_memory_report",
    content: str = "# Historical agent memory\n",
    run_id: int = 101,
) -> Report:
    report = Report(
        name=slug,
        slug=slug,
        source="agent",
        content=content,
        metadata_=_agent_memory_metadata(run_id=run_id),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _seed_run(session: Session, *, run_id: int | None = None) -> Run:
    package_id = run_id if run_id is not None else session.query(Run).count() + 1
    package_key = f"platform_graph_daily_review_package_{package_id}"
    run = Run(
        id=run_id,
        target_kind="workflowPackage",
        target_id=package_id,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key="platform_graph_daily_review",
        input={"ticker": "NVDA"},
        status="running",
        trace_id="trace-memory-report-retirement",
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package_id,
        workflow_package_key=package_key,
        workflow_package_name="Platform Graph Daily Review Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key="platform_graph_daily_review",
        workflow_name="Platform Graph Daily Review",
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=("apiVersion: signaldeck.workflowPackage/v1\n" f"key: {package_key}\n"),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": "platform_graph_daily_review"}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": ["platform_graph_daily_review"]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def _core_memory_write_request(run_id: int) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary="Core memory survives report retirement.",
        content="Core memory is table backed; report rows must not participate.",
        subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
        attributes={"confidence": "high"},
        scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run_id)),
        provenance=MemoryProvenance(
            run_id=run_id,
            agent_key="analyst",
            agent_version=1,
            agent_name="Analyst",
            workflow_key="platform_graph_daily_review",
            workflow_version=5,
            step_id="portfolio_decision",
            slot="decision",
            trace_id="trace-memory-report-retirement",
        ),
    )


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_legacy_agent_memory_reports_are_historical_report_domain_artifacts(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _insert_legacy_agent_memory_report(session)
        report_id = report.id
        slug = report.slug

    list_response = client.get("/api/v1/reports", params={"source": "agent"})
    list_payload = cast(list[dict[str, object]], list_response.json())
    get_response = client.get(f"/api/v1/reports/{slug}")
    download_response = client.get(f"/api/v1/reports/{slug}/download")
    patch_response = client.patch(
        f"/api/v1/reports/{slug}",
        json={"content": "# Edited historical artifact"},
    )
    delete_response = client.delete(f"/api/v1/reports/{slug}")
    missing_response = client.get(f"/api/v1/reports/{slug}")

    assert list_response.status_code == 200, list_response.json()
    assert [item["id"] for item in list_payload] == [report_id]
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["metadata"]["analysis"]["reviewType"] == "agent_memory"
    assert download_response.status_code == 200
    assert download_response.text == "# Historical agent memory\n"
    assert patch_response.status_code == 200, patch_response.json()
    assert patch_response.json()["content"] == "# Edited historical artifact"
    assert delete_response.status_code == 204, delete_response.text
    assert delete_response.content == b""
    assert missing_response.status_code == 404, missing_response.json()


def test_memory_report_service_is_read_only_historical_adapter(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _insert_legacy_agent_memory_report(session)
        service = MemoryReportService(session)
        read_report, metadata = service.get_memory_report_with_metadata(report.id)
        read_payload = service.read_historical_memory_report(report.id)

        reports = list(session.scalars(select(Report).order_by(Report.id)))

    assert read_report.id == report.id
    assert metadata.analysis.review_type == AGENT_MEMORY_REVIEW_TYPE
    assert read_payload.slug == report.slug
    for removed_write_method in (
        "create_pending_report",
        "update_memory_report",
        "resolve_memory_report",
        "append_reflection",
    ):
        assert not hasattr(service, removed_write_method)
    assert [item.id for item in reports] == [report.id]


def test_core_memory_ignores_legacy_agent_memory_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        legacy_report = _insert_legacy_agent_memory_report(session)
        run = _seed_run(session)
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                agent_key="analyst",
                workflow_key="platform_graph_daily_review",
            ),
        )

        before = service.query_memory(
            MemoryQuery(
                subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
                agent_key="analyst",
            ),
            record_event=False,
        )
        with pytest.raises(ApiError) as missing_error:
            _ = service.get_memory(f"mem_{legacy_report.id}")

        created = service.write_memory(
            capability_references=[],
            payload=_core_memory_write_request(run.id),
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(
                status=MemoryLifecycleStatus.APPROVED,
                summary="Core memory resolved.",
                observed_at=datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
                attributes={"rawReturn": "0.125", "alpha": "0.095"},
            ),
        )
        after = service.query_memory(
            MemoryQuery(
                subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
                agent_key="analyst",
            ),
            record_event=False,
        )
        reports = list(session.scalars(select(Report).order_by(Report.id)))
        entry_count = _count(session, AgentMemoryEntry)
        revision_count = _count(session, AgentMemoryRevision)
        event_count = _count(session, RunMemoryEvent)

    assert before == []
    assert missing_error.value.code == "memory_not_found"
    assert [snippet.memory_id for snippet in after] == [created.memory_id]
    assert not created.memory_id.startswith("mem_")
    assert [report.id for report in reports] == [legacy_report.id]
    assert entry_count == 1
    assert revision_count == 2
    assert event_count == 2


def test_agent_memory_report_metadata_remains_valid_for_historical_audit() -> None:
    model_input = AgentMemoryModelInput.model_validate(
        {
            "ticker": " nvda ",
            "portfolioSlug": " core_us ",
            "horizonDays": 14,
            "confidence": " high ",
            "decisionSummary": " Historical report metadata. ",
            "decision": _decision_payload(),
        }
    )
    trusted_context = AgentMemoryTrustedCreateContext.model_validate(
        {
            "runId": 101,
            "agentKey": "analyst",
            "agentVersion": 1,
            "agentName": "Analyst",
            "workflowKey": "platform_graph_daily_review",
            "workflowVersion": 5,
            "stepId": "portfolio_decision",
            "slot": "decision",
            "traceId": "trace-memory-report-retirement",
        }
    )

    metadata = AgentMemoryReportMetadata.pending(
        model_input=model_input,
        trusted_context=trusted_context,
    )
    payload = cast(dict[str, object], metadata.model_dump(by_alias=True, mode="json"))
    analysis = cast(dict[str, object], payload["analysis"])
    created_by = cast(dict[str, object], payload["createdBy"])

    assert payload["tags"] == [AGENT_MEMORY_REVIEW_TYPE]
    assert analysis["reviewType"] == AGENT_MEMORY_REVIEW_TYPE
    assert analysis["versionGroup"] == AGENT_MEMORY_VERSION_GROUP
    assert analysis["ticker"] == "NVDA"
    assert analysis["resolvedStatus"] == "pending"
    assert created_by["type"] == "agent"
    assert created_by["runId"] == 101


def test_core_memory_route_surface_is_platform_core_not_finance_owned(
    app: FastAPI,
    client: TestClient,
) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    openapi_paths = set(cast(dict[str, object], app.openapi()["paths"]))

    assert "/api/memory" in route_paths
    assert "/api/memory" in openapi_paths
    assert not any(path.startswith("/api/v1/memory") for path in route_paths)
    assert not any(path.startswith("/api/v1/memory") for path in openapi_paths)
    assert client.get("/api/memory").status_code == 405
    assert client.post("/api/memory", json={}).status_code == 422
    assert client.post("/api/v1/memory", json={}).status_code == 404
