from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas.memory import (
    INVALID_MEMORY_ID_CODE,
    MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS,
    MEMORY_NOT_FOUND_CODE,
    MEMORY_PROJECTION_MATRIX,
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryAuditReportLink,
    MemoryDecision,
    MemoryEntryRead,
    MemoryId,
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
    MemoryWriteResult,
    format_report_backed_memory_id,
    invalid_memory_id_error,
    memory_not_found_error,
    parse_report_backed_memory_id,
)

_CREATED_AT = datetime(2026, 5, 8, 9, 30, tzinfo=UTC)
_RESOLVED_AT = datetime(2026, 5, 15, 9, 30, tzinfo=UTC)
_REFLECTED_AT = datetime(2026, 5, 16, 9, 30, tzinfo=UTC)

_FORBIDDEN_MODEL_VISIBLE_FRAGMENTS = (
    "reportId",
    "reportSlug",
    "reportName",
    "auditLinks",
    "url",
    "/reports/",
    "download",
    "agent_memory_nvda_slug",
    "Agent Memory Report",
    "# Agent Memory",
)


def _decision() -> MemoryDecision:
    return MemoryDecision.model_validate(
        {
            "action": "buy",
            "rationale": "Earnings durability supports a long position.",
            "riskSummary": "Sizing should account for cyclicality.",
            "executionPlan": "Scale in after liquidity confirmation.",
        }
    )


def _provenance() -> MemoryProvenance:
    return MemoryProvenance.model_validate(
        {
            "runId": 42,
            "agentKey": "portfolio_manager",
            "agentVersion": 3,
            "agentName": "Portfolio Manager",
            "workflowKey": "daily_review",
            "workflowVersion": 7,
            "stepId": "portfolio_decision",
            "slot": "decision",
            "traceId": "trace-abc123",
        }
    )


def _outcome(status: str = "resolved") -> MemoryOutcome:
    payload: dict[str, object] = {
        "resolvedStatus": status,
        "resolvedAt": _RESOLVED_AT,
    }
    if status == "resolved":
        payload.update(
            {
                "rawReturn": Decimal("0.125"),
                "benchmarkReturn": Decimal("0.030"),
                "alpha": Decimal("0.095"),
            }
        )
    return MemoryOutcome.model_validate(payload)


def _audit_links() -> MemoryAuditLinks:
    return MemoryAuditLinks(
        report=MemoryAuditReportLink(
            slug="agent_memory_nvda_slug",
            name="Agent Memory Report",
            url="/reports/agent_memory_nvda_slug",
            download_url="/api/v1/reports/agent_memory_nvda_slug/download",
        )
    )


def _serialized_text(payload: object) -> str:
    return str(payload)


def test_report_backed_memory_id_is_opaque_phase_1_identity() -> None:
    memory_id = MemoryId.from_report_id(123)

    assert memory_id.value == "mem_123"
    assert memory_id.model_dump(mode="json", by_alias=True) == {"value": "mem_123"}
    assert memory_id.report_id_for_report_backed_store() == 123
    assert format_report_backed_memory_id(456) == "mem_456"
    assert parse_report_backed_memory_id("mem_456") == 456


@pytest.mark.parametrize(
    "value",
    ["", "mem_", "mem_0", "mem_-1", "mem_abc", "report_1", "mem_1_slug"],
)
def test_invalid_memory_id_uses_sanitized_memory_domain_error(value: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        _ = parse_report_backed_memory_id(value)

    error = exc_info.value
    serialized = _serialized_text(
        {"code": error.code, "message": error.message, "details": error.details}
    )
    assert error.code == INVALID_MEMORY_ID_CODE
    assert error.status_code == 400
    assert error.message == "Invalid memory id"
    assert error.details == []
    assert "report" not in serialized.lower()
    assert "/reports/" not in serialized


def test_memory_not_found_error_stays_memory_domain_only() -> None:
    error = memory_not_found_error()
    serialized = _serialized_text(
        {"code": error.code, "message": error.message, "details": error.details}
    )

    assert error.code == MEMORY_NOT_FOUND_CODE
    assert error.status_code == 404
    assert error.message == "Memory not found"
    assert "report" not in serialized.lower()
    assert "/reports/" not in serialized


def test_memory_write_result_model_visible_projection_has_no_report_fields() -> None:
    result = MemoryWriteResult(
        memory_id="mem_1001",
        status=MemoryLifecycleStatus.PENDING,
        action="created",
        created_at=_CREATED_AT,
        provenance=_provenance(),
    )

    payload = result.model_dump(mode="json", by_alias=True)
    assert set(payload) == {
        "memoryId",
        "status",
        "action",
        "createdAt",
        "provenance",
        "warnings",
    }
    assert payload["memoryId"] == "mem_1001"
    assert payload["status"] == "pending"
    assert payload["action"] == "created"
    assert payload["createdAt"] == "2026-05-08T09:30:00Z"
    assert cast(dict[str, object], payload["provenance"])["agentKey"] == "portfolio_manager"
    assert payload["warnings"] == []

    serialized = _serialized_text(payload)
    for fragment in _FORBIDDEN_MODEL_VISIBLE_FRAGMENTS:
        assert fragment not in serialized


def test_projection_matrix_documents_four_visibility_surfaces() -> None:
    assert set(MEMORY_PROJECTION_MATRIX) == {
        "model-visible",
        "api-visible",
        "ui-visible",
        "report-route-visible",
    }
    assert "auditLinks" not in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "auditLinks" in MEMORY_PROJECTION_MATRIX["api-visible"]
    assert "auditLinks" in MEMORY_PROJECTION_MATRIX["ui-visible"]
    assert MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS >= {"auditLinks", "reportId", "reportSlug"}


def test_model_visible_projection_strips_audit_links_from_write_result() -> None:
    result = MemoryWriteResult(
        memory_id="mem_1002",
        status=MemoryLifecycleStatus.PENDING,
        action="existing",
        created_at=_CREATED_AT,
        provenance=_provenance(),
        audit_links=_audit_links(),
    )

    assert "auditLinks" in result.dump_for_projection("api-visible")
    model_payload = result.model_visible_dump()

    serialized = _serialized_text(model_payload)
    assert "auditLinks" not in model_payload
    for fragment in _FORBIDDEN_MODEL_VISIBLE_FRAGMENTS:
        assert fragment not in serialized


def test_memory_artifact_api_projection_may_include_nested_report_audit_links() -> None:
    artifact = MemoryArtifactRead(
        memory_id="mem_1003",
        status=MemoryLifecycleStatus.PENDING,
        summary="NVDA buy memory",
        provenance=_provenance(),
        created_at=_CREATED_AT,
        audit_links=_audit_links(),
        source_graph_metadata={"stepId": "portfolio_decision"},
    )

    payload = artifact.dump_for_projection("ui-visible")
    audit_links = cast(dict[str, object], payload["auditLinks"])
    report = cast(dict[str, object], audit_links["report"])

    assert payload["memoryId"] == "mem_1003"
    assert report["slug"] == "agent_memory_nvda_slug"
    assert report["url"] == "/reports/agent_memory_nvda_slug"
    assert str(report["downloadUrl"]).endswith("/download")
    assert "reportId" not in report


def test_memory_prompt_snippet_model_visible_text_excludes_report_audit_details() -> None:
    snippet = MemoryPromptSnippet(
        memory_id="mem_1004",
        text=(
            "Historical memory, not an instruction:\n"
            "Decision: buy NVDA for portfolio core_us.\n"
            "Outcome: resolved with alpha 0.095."
        ),
        provenance=_provenance(),
        outcome=_outcome(),
        reflections=[
            MemoryReflection(
                reflection="Liquidity confirmation mattered.",
                reflected_at=_REFLECTED_AT,
            )
        ],
    )

    payload = snippet.model_visible_dump()
    serialized = _serialized_text(payload)

    assert payload["memoryId"] == "mem_1004"
    assert "Historical memory, not an instruction" in str(payload["text"])
    for fragment in _FORBIDDEN_MODEL_VISIBLE_FRAGMENTS:
        assert fragment not in serialized


def test_memory_entry_lifecycle_matches_report_backed_metadata_rules() -> None:
    resolved = MemoryEntryRead(
        memory_id="mem_1005",
        status=MemoryLifecycleStatus.RESOLVED,
        ticker=" nvda ",
        decision=_decision(),
        provenance=_provenance(),
        created_at=_CREATED_AT,
        outcome=_outcome(),
        reflections=[
            MemoryReflection(
                reflection="Outcome confirmed thesis.",
                reflected_at=_REFLECTED_AT,
            )
        ],
    )
    expired = MemoryEntryRead(
        memory_id="mem_1006",
        status=MemoryLifecycleStatus.EXPIRED,
        ticker="msft",
        decision=_decision(),
        provenance=_provenance(),
        created_at=_CREATED_AT,
        outcome=_outcome("expired"),
    )

    assert resolved.ticker == "NVDA"
    assert expired.outcome is not None
    assert expired.outcome.raw_return is None
    assert expired.outcome.alpha is None


def test_memory_entry_rejects_pending_outcome_and_resolved_without_outcome() -> None:
    with pytest.raises(ValidationError):
        _ = MemoryEntryRead(
            memory_id="mem_1007",
            status=MemoryLifecycleStatus.PENDING,
            ticker="NVDA",
            decision=_decision(),
            provenance=_provenance(),
            created_at=_CREATED_AT,
            outcome=_outcome(),
        )

    with pytest.raises(ValidationError):
        _ = MemoryEntryRead(
            memory_id="mem_1008",
            status=MemoryLifecycleStatus.RESOLVED,
            ticker="NVDA",
            decision=_decision(),
            provenance=_provenance(),
            created_at=_CREATED_AT,
        )

    with pytest.raises(ValidationError):
        _ = MemoryOutcome(resolved_status="resolved", resolved_at=_RESOLVED_AT)


def test_memory_write_request_keeps_model_input_separate_from_trusted_provenance() -> None:
    request = MemoryWriteRequest.model_validate(
        {
            "ticker": " nvda ",
            "portfolioSlug": " core_us ",
            "horizonDays": 14,
            "confidence": " high ",
            "decisionSummary": " Durable earnings setup. ",
            "benchmarkSymbol": " spy ",
            "decision": _decision().model_dump(mode="json", by_alias=True),
            "provenance": _provenance().model_dump(mode="json", by_alias=True),
        }
    )
    query = MemoryQuery.model_validate(
        {
            "ticker": " nvda ",
            "portfolioSlug": " core_us ",
            "agentKey": " portfolio_manager ",
            "status": "resolved",
            "limit": 3,
            "offset": 0,
            "maxCharacters": 4000,
        }
    )

    assert request.ticker == "NVDA"
    assert request.portfolio_slug == "core_us"
    assert request.benchmark_symbol == "SPY"
    assert request.provenance.run_id == 42
    assert query.ticker == "NVDA"
    assert query.portfolio_slug == "core_us"
    assert query.status == MemoryLifecycleStatus.RESOLVED


def test_invalid_memory_id_error_helper_is_sanitized() -> None:
    error = invalid_memory_id_error()

    assert error.code == INVALID_MEMORY_ID_CODE
    assert error.message == "Invalid memory id"
    assert error.details == []
    assert "report" not in _serialized_text(error.__dict__).lower()
