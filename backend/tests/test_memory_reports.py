from __future__ import annotations

import tomllib
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.extensions.signaldeck_finance.grant_policy import (
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    REPORT_MEMORY_WRITE_GRANT_POLICY,
)
from app.extensions.signaldeck_finance.hooks import (
    MEMORY_CONTEXT_SERVICE_SURFACE,
    MEMORY_REPORT_SERVICE_SURFACE,
    MEMORY_SERVICE_SURFACE,
    REFLECTION_SERVICE_SURFACE,
    RETURN_RESOLUTION_SERVICE_SURFACE,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.extensions.signaldeck_finance.runtime_types import (
    REPORT_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_TOOL_KEY,
)
from app.models.capability import Capability
from app.models.report import Report
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import MemoryEntryRead
from app.schemas.memory_report import (
    AGENT_MEMORY_IMMUTABLE_FIELDS,
    AGENT_MEMORY_OPTIONAL_FIELDS,
    AGENT_MEMORY_REQUIRED_FIELDS,
    AGENT_MEMORY_REVIEW_TYPE,
    AGENT_MEMORY_SERVICE_MUTABLE_FIELDS,
    AGENT_MEMORY_VERSION_GROUP,
    AgentMemoryModelInput,
    AgentMemoryReflectionAppend,
    AgentMemoryReportAnalysis,
    AgentMemoryReportCreateMetadata,
    AgentMemoryReportMetadata,
    AgentMemoryResolutionUpdate,
    AgentMemoryServiceUpdate,
    AgentMemoryTrustedCreateContext,
)
from app.schemas.report import ReportRead, ReportUpdate
from app.services.capability_service import RuntimeToolGrantError
from app.services.extension_service import ExtensionService
from app.services.market_data_service import MarketDataService
from app.services.memory_context_service import MemoryContextService, MemoryPromptSnippet
from app.services.memory_report_service import MemoryReportService
from app.services.memory_service import MemoryService
from app.services.quote_provider import (
    ProviderFundamentals,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderNewsResult,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)
from app.services.reflection_service import ReflectionService
from app.services.report_service import ReportService
from app.services.return_resolution_service import ReturnResolutionService


def _decision_payload() -> dict[str, str]:
    return {
        "action": "buy",
        "rationale": "Earnings durability supports a long position.",
        "riskSummary": "Sizing should account for semiconductor cyclicality.",
        "executionPlan": "Scale in after the next market-data refresh.",
    }


def _model_input_payload() -> dict[str, object]:
    return {
        "ticker": " nvda ",
        "portfolioSlug": " core_us ",
        "horizonDays": 14,
        "confidence": " high ",
        "decisionSummary": " Long-term compounding memory. ",
        "decision": _decision_payload(),
    }


def _trusted_context_payload() -> dict[str, object]:
    return {
        "runId": 42,
        "agentKey": "portfolio_manager",
        "agentVersion": 3,
        "agentName": "Portfolio Manager",
        "workflowKey": "platform_graph_daily_review",
        "workflowVersion": 5,
        "stepId": "portfolio_decision",
        "slot": "decision",
        "traceId": "trace-abc123",
    }


def _expected_created_by_payload(
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {"type": "agent", **_trusted_context_payload()}
    if overrides is not None:
        payload.update(overrides)
    return payload


def _pending_create_metadata(
    overrides: dict[str, object] | None = None,
) -> AgentMemoryReportCreateMetadata:
    payload = _model_input_payload()
    if overrides is not None:
        payload.update(overrides)
    return AgentMemoryReportCreateMetadata.model_validate({"analysis": payload})


def _trusted_context(
    overrides: dict[str, object] | None = None,
) -> AgentMemoryTrustedCreateContext:
    payload = _trusted_context_payload()
    if overrides is not None:
        payload.update(overrides)
    return AgentMemoryTrustedCreateContext.model_validate(payload)


_MEMORY_WRITE_CAPABILITY_KEY = "memory_report_test_writer"


def _memory_write_capability_references(
    *,
    key: str = _MEMORY_WRITE_CAPABILITY_KEY,
) -> list[dict[str, object]]:
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
            name="Memory Report Test Writer",
            description="Grants report-memory writes in tests.",
            tool_keys=[REPORT_MEMORY_WRITE_TOOL_KEY],
        )
    )
    session.commit()


def _create_pending_report(
    session: Session,
    *,
    run_id: int = 42,
) -> ReportRead:
    _ensure_memory_write_capability(session)
    return MemoryReportService(session).create_pending_report(
        capability_references=_memory_write_capability_references(),
        grant_policy=REPORT_MEMORY_WRITE_GRANT_POLICY,
        payload=_pending_create_metadata(),
        trusted_context=_trusted_context({"runId": run_id}),
    )


def _disable_finance_workspace(session: Session) -> None:
    ExtensionService(session).set_extension_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        ExtensionToggleRequest.model_validate({"enabled": False}),
    )


def _assert_extension_disabled(
    exc_info: pytest.ExceptionInfo[ApiError],
    surface: str,
) -> None:
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "extension_disabled"
    assert exc_info.value.details == [
        {"extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY, "surface": surface}
    ]


class _MemoryHistoryQuoteProvider:
    provider_name: str = "memory_history_test"

    def __init__(self, rows_by_symbol: dict[str, list[tuple[datetime, Decimal]]]) -> None:
        self.rows_by_symbol: dict[str, list[tuple[datetime, Decimal]]] = rows_by_symbol

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
        normalized_symbol = symbol.upper()
        rows = self.rows_by_symbol.get(normalized_symbol)
        if rows is None:
            raise QuoteProviderError(f"No OHLCV data available for {normalized_symbol}")
        return ProviderOhlcvSeries(
            symbol=normalized_symbol,
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


def _create_resolution_report(
    session: Session,
    *,
    action: str = "buy",
    ticker: str = "NVDA",
    horizon_days: int = 4,
    run_id: int = 420,
    created_at: datetime | None = None,
) -> ReportRead:
    _ensure_memory_write_capability(session)
    decision = _decision_payload()
    decision["action"] = action
    report = MemoryReportService(session).create_pending_report(
        capability_references=_memory_write_capability_references(),
        grant_policy=REPORT_MEMORY_WRITE_GRANT_POLICY,
        payload=_pending_create_metadata(
            {"ticker": ticker, "horizonDays": horizon_days, "decision": decision}
        ),
        trusted_context=_trusted_context({"runId": run_id}),
    )
    persisted = session.get(Report, report.id)
    assert persisted is not None
    persisted.created_at = created_at or datetime(2026, 1, 2, tzinfo=UTC)
    session.commit()
    session.refresh(persisted)
    return ReportRead.model_validate(persisted)


def _return_resolution_service(
    session: Session,
    rows_by_symbol: dict[str, list[tuple[datetime, Decimal]]],
) -> ReturnResolutionService:
    provider = _MemoryHistoryQuoteProvider(rows_by_symbol)
    market_data_service = MarketDataService(session=session, quote_provider=provider)
    return ReturnResolutionService(session, market_data_service)


def test_public_report_api_rejects_agent_memory_update_and_delete(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)

    update_response = client.patch(
        f"/api/v1/reports/{report.slug}",
        json={"content": "# Forged memory edit"},
    )
    assert update_response.status_code == 403
    assert update_response.json()["code"] == "memory_report_mutation_forbidden"

    delete_response = client.delete(f"/api/v1/reports/{report.slug}")
    assert delete_response.status_code == 403
    assert delete_response.json()["code"] == "memory_report_mutation_forbidden"

    get_response = client.get(f"/api/v1/reports/{report.slug}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == report.content


def test_phase_1_memory_baseline_has_no_public_route_table_or_vector_dependency(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    openapi_paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])

    assert not any(
        path == "/api/memory"
        or path.startswith("/api/memory/")
        or path == "/api/v1/memory"
        or path.startswith("/api/v1/memory/")
        for path in openapi_paths
    )
    assert client.get("/api/memory").status_code == 404
    assert client.get("/api/v1/memory").status_code == 404

    with session_factory() as session:
        report = _create_pending_report(session, run_id=700)
        assert session.get(Report, report.id) is not None
        table_names = set(inspect(session.get_bind()).get_table_names())

    memory_tables = {
        table_name
        for table_name in table_names
        if table_name == "memory"
        or table_name.startswith("memory_")
        or table_name.endswith("_memory")
    }
    assert memory_tables == set()

    backend_pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    dependencies = cast(
        list[str],
        tomllib.loads(backend_pyproject.read_text(encoding="utf-8"))["project"]["dependencies"],
    )
    vector_dependency_fragments = (
        "chromadb",
        "faiss",
        "milvus",
        "pgvector",
        "pinecone",
        "qdrant",
        "sentence-transformers",
        "weaviate",
    )
    assert not any(
        fragment in dependency.lower()
        for dependency in dependencies
        for fragment in vector_dependency_fragments
    )


def test_report_service_rejects_generic_agent_memory_update_and_delete(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        service = ReportService(session)

        with pytest.raises(ApiError) as update_error:
            _ = service.update_report(
                report.id,
                ReportUpdate(content="# Generic public edit"),
            )

        with pytest.raises(ApiError) as delete_error:
            service.delete_report(report.id)

        updated = MemoryReportService(session).resolve_memory_report(
            report.id,
            _resolution_update(),
        )
        persisted = session.get(Report, report.id)
        assert persisted is not None
        persisted_content = persisted.content

    assert update_error.value.status_code == 403
    assert update_error.value.code == "memory_report_mutation_forbidden"
    assert delete_error.value.status_code == 403
    assert delete_error.value.code == "memory_report_mutation_forbidden"
    assert updated.content != report.content
    assert persisted_content == updated.content


def _full_analysis_payload() -> dict[str, object]:
    return {
        "ticker": "NVDA",
        "decision": _decision_payload(),
        "runId": 42,
        "agentKey": "portfolio_manager",
        "agentVersion": 3,
    }


def test_agent_memory_pending_metadata_serializes_constants_and_trusted_fields() -> None:
    model_input = AgentMemoryModelInput.model_validate(_model_input_payload())
    trusted_context = AgentMemoryTrustedCreateContext.model_validate(_trusted_context_payload())

    metadata = AgentMemoryReportMetadata.pending(
        model_input=model_input,
        trusted_context=trusted_context,
    )

    payload: dict[str, object] = metadata.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )
    analysis = cast(dict[str, object], payload["analysis"])
    created_by = cast(dict[str, object], payload["createdBy"])
    decision = cast(dict[str, object], analysis["decision"])

    assert payload["tags"] == [AGENT_MEMORY_REVIEW_TYPE]
    assert created_by == _expected_created_by_payload()
    assert analysis["reviewType"] == AGENT_MEMORY_REVIEW_TYPE
    assert analysis["versionGroup"] == AGENT_MEMORY_VERSION_GROUP
    assert analysis["ticker"] == "NVDA"
    assert analysis["portfolioSlug"] == "core_us"
    assert analysis["horizonDays"] == 14
    assert analysis["confidence"] == "high"
    assert analysis["decisionSummary"] == "Long-term compounding memory."
    assert decision["riskSummary"] == _decision_payload()["riskSummary"]
    assert decision["executionPlan"] == _decision_payload()["executionPlan"]
    assert analysis["runId"] == 42
    assert analysis["agentKey"] == "portfolio_manager"
    assert analysis["agentVersion"] == 3
    assert analysis["agentName"] == "Portfolio Manager"
    assert analysis["workflowKey"] == "platform_graph_daily_review"
    assert analysis["workflowVersion"] == 5
    assert analysis["stepId"] == "portfolio_decision"
    assert analysis["slot"] == "decision"
    assert analysis["traceId"] == "trace-abc123"
    assert analysis["resolvedStatus"] == "pending"
    assert analysis["reflections"] == []
    assert "resolvedAt" not in analysis
    assert "rawReturn" not in analysis
    assert "alpha" not in analysis


def test_agent_memory_model_input_normalizes_optional_fields() -> None:
    payload = _model_input_payload()
    payload.update(
        {
            "ticker": " aapl ",
            "portfolioSlug": " ",
            "confidence": " conviction ",
            "decisionSummary": " ",
            "benchmarkSymbol": " spy ",
        }
    )

    model_input = AgentMemoryModelInput.model_validate(payload)

    assert model_input.ticker == "AAPL"
    assert model_input.portfolio_slug is None
    assert model_input.confidence == "conviction"
    assert model_input.decision_summary is None
    assert model_input.benchmark_symbol == "SPY"


def test_agent_memory_contract_field_groups_are_explicit() -> None:
    assert "analysis.reviewType" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "analysis.versionGroup" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "analysis.decision" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "analysis.runId" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "analysis.agentKey" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "createdBy.type" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "createdBy.runId" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "createdBy.agentKey" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "createdBy.agentVersion" in AGENT_MEMORY_REQUIRED_FIELDS
    assert "analysis.portfolioSlug" in AGENT_MEMORY_OPTIONAL_FIELDS
    assert "analysis.benchmarkSymbol" in AGENT_MEMORY_OPTIONAL_FIELDS
    assert "analysis.workflowKey" in AGENT_MEMORY_OPTIONAL_FIELDS
    assert "createdBy.agentName" in AGENT_MEMORY_OPTIONAL_FIELDS
    assert "createdBy.workflowKey" in AGENT_MEMORY_OPTIONAL_FIELDS
    assert "analysis.reviewType" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "analysis.benchmarkSymbol" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "analysis.decision" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "analysis.runId" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "analysis.agentVersion" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "createdBy.type" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "createdBy.agentKey" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "createdBy.workflowVersion" in AGENT_MEMORY_IMMUTABLE_FIELDS
    assert "analysis.resolvedStatus" in AGENT_MEMORY_SERVICE_MUTABLE_FIELDS
    assert "analysis.rawReturn" in AGENT_MEMORY_SERVICE_MUTABLE_FIELDS
    assert "analysis.alpha" in AGENT_MEMORY_SERVICE_MUTABLE_FIELDS
    assert "analysis.reflections" in AGENT_MEMORY_SERVICE_MUTABLE_FIELDS


def test_agent_memory_metadata_rejects_created_by_analysis_mismatch() -> None:
    model_input = AgentMemoryModelInput.model_validate(_model_input_payload())
    trusted_context = AgentMemoryTrustedCreateContext.model_validate(_trusted_context_payload())
    metadata = AgentMemoryReportMetadata.pending(
        model_input=model_input,
        trusted_context=trusted_context,
    ).model_dump(by_alias=True, mode="json", exclude_none=True)
    created_by = cast(dict[str, object], metadata["createdBy"])
    created_by["agentKey"] = "different_agent"

    with pytest.raises(ValidationError):
        _ = AgentMemoryReportMetadata.model_validate(metadata)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("runId", 42),
        ("agentKey", "spoofed_agent"),
        ("agentVersion", 99),
        ("agentName", "Spoofed Agent"),
        ("resolvedStatus", "resolved"),
        ("returns", {"raw": "0.12"}),
        ("rawReturn", "0.12"),
        ("benchmarkReturn", "0.03"),
        ("alpha", "0.09"),
        ("resolvedAt", "2026-01-17T10:30:00Z"),
        ("reflections", [{"reflection": "outcome-aware text"}]),
    ],
)
def test_agent_memory_create_metadata_rejects_spoofed_trusted_fields(
    field_name: str,
    field_value: object,
) -> None:
    analysis_payload = _model_input_payload()
    analysis_payload[field_name] = field_value
    payload = {"analysis": analysis_payload}

    with pytest.raises(ValidationError):
        _ = AgentMemoryReportCreateMetadata.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("runId", 42),
        ("agentKey", "spoofed_agent"),
        ("agentVersion", 99),
        ("agentName", "Spoofed Agent"),
        ("resolvedStatus", "resolved"),
        ("returns", {"raw": "0.12"}),
        ("rawReturn", "0.12"),
        ("benchmarkReturn", "0.03"),
        ("alpha", "0.09"),
        ("resolvedAt", "2026-01-17T10:30:00Z"),
        ("reflections", [{"reflection": "outcome-aware text"}]),
    ],
)
def test_agent_memory_model_input_rejects_spoofed_trusted_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = _model_input_payload()
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        _ = AgentMemoryModelInput.model_validate(payload)


@pytest.mark.parametrize(
    ("constant_field", "field_value"),
    [
        ("reviewType", "weekly_review"),
        ("versionGroup", "agent_memory/v2"),
    ],
)
def test_agent_memory_analysis_rejects_non_memory_constants(
    constant_field: str,
    field_value: str,
) -> None:
    payload = _full_analysis_payload()
    payload[constant_field] = field_value

    with pytest.raises(ValidationError):
        _ = AgentMemoryReportAnalysis.model_validate(payload)


def test_agent_memory_service_update_allows_resolution_and_reflection_append() -> None:
    service_update = AgentMemoryServiceUpdate.model_validate(
        {
            "resolution": {
                "resolvedStatus": "resolved",
                "resolvedAt": "2026-01-17T10:30:00Z",
                "rawReturn": "0.125",
                "benchmarkReturn": "0.030",
                "alpha": "0.095",
            },
            "reflections": [
                {
                    "reflection": "The setup worked when liquidity confirmed momentum.",
                    "reflectedAt": "2026-01-18T08:00:00Z",
                }
            ],
        }
    )

    payload: dict[str, object] = service_update.model_dump(by_alias=True, mode="json")
    resolution = cast(dict[str, object], payload["resolution"])

    assert resolution["resolvedStatus"] == "resolved"
    assert resolution["resolvedAt"] == "2026-01-17T10:30:00Z"
    assert resolution["rawReturn"] == "0.125"
    assert resolution["benchmarkReturn"] == "0.030"
    assert resolution["alpha"] == "0.095"
    assert payload["reflections"] == [
        {
            "reflection": "The setup worked when liquidity confirmed momentum.",
            "reflectedAt": "2026-01-18T08:00:00Z",
        }
    ]


def test_agent_memory_full_analysis_accepts_service_owned_resolution_fields() -> None:
    payload = _full_analysis_payload()
    payload.update(
        {
            "resolvedStatus": "resolved",
            "resolvedAt": datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
            "rawReturn": "0.125",
            "benchmarkReturn": "0.030",
            "alpha": "0.095",
            "reflections": [
                {
                    "reflection": "Outcome confirmed the original risk summary.",
                    "reflectedAt": "2026-01-18T08:00:00Z",
                }
            ],
        }
    )

    analysis = AgentMemoryReportAnalysis.model_validate(payload)
    serialized: dict[str, object] = analysis.model_dump(by_alias=True, mode="json")
    reflections = cast(list[dict[str, object]], serialized["reflections"])

    assert serialized["resolvedStatus"] == "resolved"
    assert serialized["resolvedAt"] == "2026-01-17T10:30:00Z"
    assert serialized["rawReturn"] == "0.125"
    assert serialized["benchmarkReturn"] == "0.030"
    assert serialized["alpha"] == "0.095"
    assert reflections[0]["reflectedAt"] == "2026-01-18T08:00:00Z"


def test_agent_memory_full_analysis_rejects_pending_outcomes_and_incomplete_resolution() -> None:
    pending_payload = _full_analysis_payload()
    pending_payload["rawReturn"] = "0.125"

    with pytest.raises(ValidationError):
        _ = AgentMemoryReportAnalysis.model_validate(pending_payload)

    resolved_payload = _full_analysis_payload()
    resolved_payload.update(
        {
            "resolvedStatus": "resolved",
            "resolvedAt": "2026-01-17T10:30:00Z",
        }
    )

    with pytest.raises(ValidationError):
        _ = AgentMemoryReportAnalysis.model_validate(resolved_payload)


def test_agent_memory_service_update_rejects_empty_payload() -> None:
    with pytest.raises(ValidationError):
        _ = AgentMemoryServiceUpdate.model_validate({})


def _read_report(session: Session, report_id: int) -> ReportRead:
    report = session.get(Report, report_id)
    assert report is not None
    return ReportRead.model_validate(report)


def _report_metadata_payload(report: ReportRead) -> tuple[dict[str, object], dict[str, object]]:
    payload = report.model_dump(mode="json", by_alias=True)
    metadata = cast(dict[str, object], payload["metadata"])
    analysis = cast(dict[str, object], metadata["analysis"])
    return metadata, analysis


def test_memory_report_service_creates_pending_report_with_agent_source_and_created_by(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        reports = list(session.scalars(select(Report)))

    metadata, analysis = _report_metadata_payload(report)
    created_by = cast(dict[str, object], metadata["createdBy"])
    decision = cast(dict[str, object], analysis["decision"])

    assert len(reports) == 1
    assert report.source == "agent"
    assert created_by == _expected_created_by_payload()
    assert report.name == report.slug
    assert report.slug.startswith(
        "agent_memory_nvda_portfolio_manager_run_42_buy_portfolio_decision_decision_"
    )
    assert report.content.startswith("# Agent Memory: NVDA")
    assert "Status: pending" in report.content
    assert "## Rationale" in report.content
    assert metadata["tags"] == [AGENT_MEMORY_REVIEW_TYPE]
    assert analysis["reviewType"] == AGENT_MEMORY_REVIEW_TYPE
    assert analysis["versionGroup"] == AGENT_MEMORY_VERSION_GROUP
    assert analysis["runId"] == 42
    assert analysis["agentKey"] == "portfolio_manager"
    assert analysis["agentVersion"] == 3
    assert analysis["workflowKey"] == "platform_graph_daily_review"
    assert analysis["workflowVersion"] == 5
    assert analysis["ticker"] == "NVDA"
    assert analysis["resolvedStatus"] == "pending"
    assert analysis["reflections"] == []
    assert decision["action"] == "buy"


def test_memory_report_service_is_idempotent_for_same_pending_run(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first = _create_pending_report(session)
        second = _create_pending_report(session)
        reports = list(session.scalars(select(Report)))

    assert first.id == second.id
    assert first.slug == second.slug
    assert first.name == second.name
    assert first.content == second.content
    assert len(reports) == 1


def test_memory_report_service_creates_new_report_for_different_run(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first = _create_pending_report(session, run_id=42)
        second = _create_pending_report(session, run_id=43)
        reports = list(session.scalars(select(Report)))

    assert first.id != second.id
    assert first.slug != second.slug
    assert len(reports) == 2


def test_report_memory_service_create_pending_report_requires_write_grant(
    session_factory: sessionmaker[Session],
) -> None:
    capability_key = "memory_report_read_only"
    with session_factory() as session:
        session.add(
            Capability(
                key=capability_key,
                version=1,
                status="published",
                name="Read Only Memory Report Capability",
                description="Does not grant memory writes.",
                tool_keys=[REPORT_LOOKUP_TOOL_KEY],
            )
        )
        session.commit()

        with pytest.raises(RuntimeToolGrantError) as exc_info:
            _ = MemoryReportService(session).create_pending_report(
                capability_references=_memory_write_capability_references(key=capability_key),
                grant_policy=REPORT_MEMORY_WRITE_GRANT_POLICY,
                payload=_pending_create_metadata(),
                trusted_context=_trusted_context(),
            )
        reports = list(session.scalars(select(Report)))

    assert exc_info.value.code == REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE
    assert exc_info.value.message == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert reports == []


def test_memory_report_service_derives_trusted_metadata_from_context(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _pending_create_metadata({"ticker": " msft "})
    trusted_context = _trusted_context(
        {
            "runId": 99,
            "agentKey": "risk_manager",
            "agentVersion": 7,
            "agentName": "Risk Manager",
            "workflowKey": "platform_graph_risk_review",
            "workflowVersion": 2,
            "traceId": "trace-derived",
        }
    )
    with session_factory() as session:
        _ensure_memory_write_capability(session)
        report = MemoryReportService(session).create_pending_report(
            capability_references=_memory_write_capability_references(),
            grant_policy=REPORT_MEMORY_WRITE_GRANT_POLICY,
            payload=payload,
            trusted_context=trusted_context,
        )

    metadata, analysis = _report_metadata_payload(report)
    created_by = cast(dict[str, object], metadata["createdBy"])
    assert created_by == _expected_created_by_payload(
        {
            "runId": 99,
            "agentKey": "risk_manager",
            "agentVersion": 7,
            "agentName": "Risk Manager",
            "workflowKey": "platform_graph_risk_review",
            "workflowVersion": 2,
            "traceId": "trace-derived",
        }
    )
    assert analysis["reviewType"] == AGENT_MEMORY_REVIEW_TYPE
    assert analysis["versionGroup"] == AGENT_MEMORY_VERSION_GROUP
    assert analysis["ticker"] == "MSFT"
    assert analysis["runId"] == 99
    assert analysis["agentKey"] == "risk_manager"
    assert analysis["agentVersion"] == 7
    assert analysis["agentName"] == "Risk Manager"
    assert analysis["workflowKey"] == "platform_graph_risk_review"
    assert analysis["workflowVersion"] == 2
    assert analysis["traceId"] == "trace-derived"
    assert "resolvedAt" not in analysis
    assert "rawReturn" not in analysis


def _resolution_update() -> AgentMemoryResolutionUpdate:
    return AgentMemoryResolutionUpdate.model_validate(
        {
            "resolvedStatus": "resolved",
            "resolvedAt": "2026-01-17T10:30:00Z",
            "rawReturn": "0.125",
            "benchmarkReturn": "0.030",
            "alpha": "0.095",
        }
    )


def _reflection_append(text: str, reflected_at: str) -> AgentMemoryReflectionAppend:
    return AgentMemoryReflectionAppend.model_validate(
        {
            "reflection": text,
            "reflectedAt": reflected_at,
        }
    )


def test_memory_report_service_updates_content_and_metadata_for_resolution(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        updated = MemoryReportService(session).resolve_memory_report(
            report.id,
            _resolution_update(),
        )

        persisted = session.get(Report, report.id)
        assert persisted is not None

    _, analysis = _report_metadata_payload(updated)
    assert analysis["resolvedStatus"] == "resolved"
    assert analysis["resolvedAt"] == "2026-01-17T10:30:00Z"
    assert analysis["rawReturn"] == "0.125"
    assert analysis["benchmarkReturn"] == "0.030"
    assert analysis["alpha"] == "0.095"
    assert persisted.content == updated.content
    assert persisted.metadata_["analysis"]["rawReturn"] == "0.125"
    assert "Status: resolved" in updated.content
    assert "## Outcome" in updated.content
    assert "- Raw return: 0.125" in updated.content
    assert "- Benchmark return: 0.030" in updated.content
    assert "- Alpha: 0.095" in updated.content


def test_memory_report_service_update_preserves_created_by(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        persisted = session.get(Report, report.id)
        assert persisted is not None
        created_by_before = deepcopy(cast(dict[str, object], persisted.metadata_["createdBy"]))

        service = MemoryReportService(session)
        resolved = service.resolve_memory_report(report.id, _resolution_update())
        persisted_after_resolution = session.get(Report, report.id)
        assert persisted_after_resolution is not None
        reflected = service.append_reflection(
            report.id,
            _reflection_append(
                "Outcome confirmed the setup.",
                "2026-01-18T08:00:00Z",
            ),
        )
        persisted_after_reflection = session.get(Report, report.id)
        assert persisted_after_reflection is not None

    resolved_metadata, _ = _report_metadata_payload(resolved)
    reflected_metadata, _ = _report_metadata_payload(reflected)
    assert resolved_metadata["createdBy"] == created_by_before
    assert reflected_metadata["createdBy"] == created_by_before
    assert persisted_after_resolution.metadata_["createdBy"] == created_by_before
    assert persisted_after_reflection.metadata_["createdBy"] == created_by_before


def test_return_resolution_resolves_buy_return_from_history(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="buy", run_id=421)
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("110")),
                ]
            },
        ).resolve_memory(_memory_id(report), end_date=datetime(2026, 1, 10, tzinfo=UTC))
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "resolved"
    assert outcome.reason is None
    assert analysis["resolvedStatus"] == "resolved"
    assert analysis["rawReturn"] == "0.1"
    assert analysis["alpha"] == "0.1"
    assert "benchmarkReturn" not in analysis
    assert outcome.memory.memory_id == _memory_id(report)
    assert outcome.memory.outcome is not None
    assert outcome.memory.outcome.raw_return == Decimal("0.1")
    assert "- Raw return: 0.1" in updated_report.content


def test_return_resolution_resolves_sell_return_by_inverting_price_return(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="sell", run_id=422)
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("110")),
                ]
            },
        ).resolve_memory(_memory_id(report), end_date=datetime(2026, 1, 6, tzinfo=UTC))
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "resolved"
    assert analysis["rawReturn"] == "-0.1"
    assert analysis["alpha"] == "-0.1"


def test_return_resolution_computes_benchmark_return_and_alpha(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="buy", run_id=423)
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("120")),
                ],
                "SPY": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("200")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("220")),
                ],
            },
        ).resolve_memory(
            _memory_id(report),
            end_date=datetime(2026, 1, 6, tzinfo=UTC),
            benchmark_symbol=" spy ",
        )
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "resolved"
    assert analysis["rawReturn"] == "0.2"
    assert analysis["benchmarkReturn"] == "0.1"
    assert analysis["alpha"] == "0.1"


def test_return_resolution_resolves_hold_as_neutral_with_benchmark_alpha(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="hold", run_id=424)
        outcome = _return_resolution_service(
            session,
            {
                "SPY": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("200")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("220")),
                ]
            },
        ).resolve_memory(
            _memory_id(report),
            end_date=datetime(2026, 1, 6, tzinfo=UTC),
            benchmark_symbol="SPY",
        )
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "resolved"
    assert analysis["rawReturn"] == "0"
    assert analysis["benchmarkReturn"] == "0.1"
    assert analysis["alpha"] == "-0.1"


def test_return_resolution_uses_non_trading_date_boundaries_without_lookahead(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(
            session,
            action="buy",
            horizon_days=3,
            run_id=425,
            created_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        )
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 5, tzinfo=UTC), Decimal("150")),
                ]
            },
        ).resolve_memory(_memory_id(report), end_date=datetime(2026, 1, 10, tzinfo=UTC))
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "resolved"
    assert analysis["rawReturn"] == "0"
    assert analysis["alpha"] == "0"


def test_return_resolution_expires_when_symbol_history_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="buy", run_id=426)
        outcome = _return_resolution_service(session, {}).resolve_memory(
            _memory_id(report),
            end_date=datetime(2026, 1, 6, tzinfo=UTC),
        )
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "expired"
    assert outcome.reason == "symbol_history_unavailable"
    assert analysis["resolvedStatus"] == "expired"
    assert "rawReturn" not in analysis
    assert "alpha" not in analysis


def test_return_resolution_expires_when_benchmark_history_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="buy", run_id=427)
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("120")),
                ]
            },
        ).resolve_memory(
            _memory_id(report),
            end_date=datetime(2026, 1, 6, tzinfo=UTC),
            benchmark_symbol="SPY",
        )
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    assert outcome.status == "expired"
    assert outcome.reason == "benchmark_history_unavailable"
    assert analysis["resolvedStatus"] == "expired"
    assert "rawReturn" not in analysis
    assert "benchmarkReturn" not in analysis
    assert "alpha" not in analysis


def test_return_resolution_keeps_pending_exit_before_horizon(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(session, action="buy", run_id=428)
        original_content = report.content
        outcome = _return_resolution_service(session, {}).resolve_memory(
            _memory_id(report),
            end_date=datetime(2026, 1, 3, tzinfo=UTC),
        )
        persisted = session.get(Report, report.id)
        assert persisted is not None
        unchanged_report = ReportRead.model_validate(persisted)

    _, analysis = _report_metadata_payload(unchanged_report)
    assert outcome.status == "pending"
    assert outcome.reason == "exit_condition_pending"
    assert analysis["resolvedStatus"] == "pending"
    assert "resolvedAt" not in analysis
    assert outcome.memory.status.value == "pending"
    assert unchanged_report.content == original_content


def test_memory_report_service_appends_reflections_in_order(
    session_factory: sessionmaker[Session],
) -> None:
    first_reflection = _reflection_append(
        "First lesson: wait for liquidity confirmation.",
        "2026-01-18T08:00:00Z",
    )
    second_reflection = _reflection_append(
        "Second lesson: tighten sizing when cyclicality rises.",
        "2026-01-19T08:00:00Z",
    )
    with session_factory() as session:
        report = _create_pending_report(session)
        service = MemoryReportService(session)
        _ = service.resolve_memory_report(
            report.id,
            _resolution_update(),
        )
        _ = service.append_reflection(report.id, first_reflection)
        updated = service.append_reflection(report.id, second_reflection)

    _, analysis = _report_metadata_payload(updated)
    reflections = cast(list[dict[str, object]], analysis["reflections"])
    assert [reflection["reflection"] for reflection in reflections] == [
        "First lesson: wait for liquidity confirmation.",
        "Second lesson: tighten sizing when cyclicality rises.",
    ]
    assert [reflection["reflectedAt"] for reflection in reflections] == [
        "2026-01-18T08:00:00Z",
        "2026-01-19T08:00:00Z",
    ]
    assert updated.content.count("### Reflection") == 2
    assert updated.content.index("First lesson") < updated.content.index("Second lesson")


def test_memory_report_service_rejects_reflection_append_before_resolution(
    session_factory: sessionmaker[Session],
) -> None:
    reflection = _reflection_append(
        "Reflection should wait for outcome resolution.",
        "2026-01-18T08:00:00Z",
    )
    with session_factory() as session:
        report = _create_pending_report(session)

        with pytest.raises(ValidationError):
            _ = MemoryReportService(session).append_reflection(report.id, reflection)

        persisted = session.get(Report, report.id)
        assert persisted is not None
        metadata = cast(dict[str, object], persisted.metadata_)
        analysis = cast(dict[str, object], metadata["analysis"])
        assert analysis["resolvedStatus"] == "pending"
        assert analysis["reflections"] == []
        assert persisted.content == report.content


def test_memory_report_service_rejects_non_memory_report_with_domain_error(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = Report(
            name="ordinary_report",
            slug="ordinary_report",
            source="uploaded",
            content="# Ordinary report",
            metadata_={},
        )
        session.add(report)
        session.commit()

        with pytest.raises(ApiError) as exc_info:
            _ = MemoryReportService(session).resolve_memory_report(
                report.id,
                _resolution_update(),
            )

    assert exc_info.value.code == "invalid_memory_report"
    assert exc_info.value.status_code == 400


def test_memory_report_service_rejects_invalid_memory_metadata_with_domain_error(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = Report(
            name="invalid_memory_report",
            slug="invalid_memory_report",
            source="external",
            content="# Invalid memory report",
            metadata_={"analysis": {"reviewType": "agent_memory"}},
        )
        session.add(report)
        session.commit()

        with pytest.raises(ApiError) as exc_info:
            _ = MemoryReportService(session).resolve_memory_report(
                report.id,
                _resolution_update(),
            )

    assert exc_info.value.code == "invalid_memory_report"
    assert exc_info.value.status_code == 400


def test_memory_report_service_rolls_back_content_and_metadata_on_commit_failure(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        persisted = session.get(Report, report.id)
        assert persisted is not None
        original_content = persisted.content
        original_metadata = deepcopy(persisted.metadata_)

        def failing_commit() -> None:
            session.flush()
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(RuntimeError, match="simulated commit failure"):
            _ = MemoryReportService(session).resolve_memory_report(
                report.id,
                _resolution_update(),
            )

    with session_factory() as session:
        persisted_after_failure = session.get(Report, report.id)
        assert persisted_after_failure is not None
        assert persisted_after_failure.content == original_content
        assert persisted_after_failure.metadata_ == original_metadata


def test_agent_memory_service_update_rejects_pending_resolution_status() -> None:
    with pytest.raises(ValidationError):
        _ = AgentMemoryServiceUpdate.model_validate(
            {
                "resolution": {
                    "resolvedStatus": "pending",
                    "resolvedAt": "2026-01-17T10:30:00Z",
                    "rawReturn": "0.125",
                    "alpha": "0.095",
                }
            }
        )


def _resolved_context_report(
    session: Session,
    *,
    run_id: int,
    ticker: str = "NVDA",
    portfolio_slug: str | None = "core_us",
    agent_key: str = "portfolio_manager",
    decision_summary: str = "Resolved context memory.",
    resolved_at: str = "2026-01-17T10:30:00Z",
    raw_return: str = "0.125",
    benchmark_return: str | None = "0.030",
    alpha: str = "0.095",
    reflections: list[tuple[str, str]] | None = None,
) -> ReportRead:
    _ensure_memory_write_capability(session)
    service = MemoryReportService(session)
    report = service.create_pending_report(
        capability_references=_memory_write_capability_references(),
        grant_policy=REPORT_MEMORY_WRITE_GRANT_POLICY,
        payload=_pending_create_metadata(
            {
                "ticker": ticker,
                "portfolioSlug": portfolio_slug,
                "decisionSummary": decision_summary,
            }
        ),
        trusted_context=_trusted_context({"runId": run_id, "agentKey": agent_key}),
    )
    resolution_payload: dict[str, object] = {
        "resolvedStatus": "resolved",
        "resolvedAt": resolved_at,
        "rawReturn": raw_return,
        "alpha": alpha,
    }
    if benchmark_return is not None:
        resolution_payload["benchmarkReturn"] = benchmark_return
    updated = service.resolve_memory_report(
        report.id,
        AgentMemoryResolutionUpdate.model_validate(resolution_payload),
    )
    for reflection, reflected_at in reflections or []:
        updated = service.append_reflection(
            report.id,
            _reflection_append(reflection, reflected_at),
        )
    return updated


def _memory_id(report: ReportRead) -> str:
    return f"mem_{report.id}"


def _memory_id_order(snippets: list[MemoryPromptSnippet]) -> list[str]:
    return [snippet.memory_id for snippet in snippets]


def test_disabled_finance_workspace_blocks_memory_services_without_mutating_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        persisted = session.get(Report, report.id)
        assert persisted is not None
        original_content = persisted.content
        original_metadata = deepcopy(persisted.metadata_)
        _disable_finance_workspace(session)
        write_request = MemoryService.write_request_from_report_create(
            payload=_pending_create_metadata(),
            trusted_context=_trusted_context({"runId": 999}),
        )

        with pytest.raises(ApiError) as get_error:
            _ = MemoryService(session).get_memory(_memory_id(report))
        with pytest.raises(ApiError) as write_error:
            _ = MemoryService(session).write_memory(
                capability_references=_memory_write_capability_references(),
                payload=write_request,
            )
        with pytest.raises(ApiError) as context_error:
            _ = MemoryContextService(session).get_prompt_snippets(ticker="NVDA")
        with pytest.raises(ApiError) as resolution_error:
            _ = _return_resolution_service(
                session,
                {
                    "NVDA": [
                        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    ],
                },
            ).resolve_memory(
                _memory_id(report),
                end_date=datetime(2026, 1, 6, tzinfo=UTC),
            )
        with pytest.raises(ApiError) as reflection_error:
            _ = ReflectionService(session).append_reflection(
                _memory_id(report),
                reflection="Disabled extension must not append this.",
                reflected_at=datetime(2026, 1, 7, tzinfo=UTC),
            )
        with pytest.raises(ApiError) as memory_report_error:
            _ = MemoryReportService(session).resolve_memory_report(
                report.id,
                _resolution_update(),
            )

        persisted_after = session.get(Report, report.id)
        reports = list(session.scalars(select(Report).order_by(Report.id)))

    _assert_extension_disabled(get_error, MEMORY_SERVICE_SURFACE)
    _assert_extension_disabled(write_error, MEMORY_SERVICE_SURFACE)
    _assert_extension_disabled(context_error, MEMORY_CONTEXT_SERVICE_SURFACE)
    _assert_extension_disabled(resolution_error, RETURN_RESOLUTION_SERVICE_SURFACE)
    _assert_extension_disabled(reflection_error, REFLECTION_SERVICE_SURFACE)
    _assert_extension_disabled(memory_report_error, MEMORY_REPORT_SERVICE_SURFACE)
    assert persisted_after is not None
    assert len(reports) == 1
    assert persisted_after.content == original_content
    assert persisted_after.metadata_ == original_metadata


def test_reflection_service_appends_validated_reflection_to_resolved_memory(
    session_factory: sessionmaker[Session],
) -> None:
    reflected_at = datetime(2026, 1, 18, 8, tzinfo=UTC)
    with session_factory() as session:
        report = _create_pending_report(session)
        service = MemoryReportService(session)
        _ = service.resolve_memory_report(report.id, _resolution_update())
        before_report = _read_report(session, report.id)
        before_metadata, before_analysis = _report_metadata_payload(before_report)
        created_by_before = deepcopy(cast(dict[str, object], before_metadata["createdBy"]))
        decision_before = deepcopy(cast(dict[str, object], before_analysis["decision"]))
        provenance_before = {
            key: before_analysis.get(key)
            for key in (
                "runId",
                "agentKey",
                "agentVersion",
                "agentName",
                "workflowKey",
                "workflowVersion",
                "stepId",
                "slot",
                "traceId",
            )
        }
        updated: MemoryEntryRead = ReflectionService(session).append_reflection(
            _memory_id(report),
            reflection="Outcome confirmed the liquidity gate.",
            reflected_at=reflected_at,
        )
        updated_report = _read_report(session, report.id)

    updated_metadata, analysis = _report_metadata_payload(updated_report)
    reflections = cast(list[dict[str, object]], analysis["reflections"])
    assert updated.memory_id == _memory_id(report)
    assert [reflection.reflection for reflection in updated.reflections] == [
        "Outcome confirmed the liquidity gate."
    ]
    assert reflections == [
        {
            "reflection": "Outcome confirmed the liquidity gate.",
            "reflectedAt": "2026-01-18T08:00:00Z",
        }
    ]
    updated_decision = cast(dict[str, object], analysis["decision"])
    assert updated_metadata["createdBy"] == created_by_before
    assert updated_decision == decision_before
    assert {
        key: analysis.get(key)
        for key in (
            "runId",
            "agentKey",
            "agentVersion",
            "agentName",
            "workflowKey",
            "workflowVersion",
            "stepId",
            "slot",
            "traceId",
        )
    } == provenance_before
    assert updated_decision["rationale"] == _decision_payload()["rationale"]
    assert "Outcome confirmed the liquidity gate." in updated_report.content


def test_reflection_service_rejects_pending_memory_through_lifecycle_validation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_pending_report(session)
        original_report = _read_report(session, report.id)
        original_metadata, _ = _report_metadata_payload(original_report)
        with pytest.raises(ValidationError):
            _ = ReflectionService(session).append_reflection(
                _memory_id(report),
                reflection="Pending memories should not accept reflections.",
                reflected_at=datetime(2026, 1, 18, 8, tzinfo=UTC),
            )
        persisted_report = _read_report(session, report.id)
        metadata, analysis = _report_metadata_payload(persisted_report)
        assert analysis["resolvedStatus"] == "pending"
        assert analysis["reflections"] == []
        assert metadata == original_metadata
        assert persisted_report.content == report.content


def test_reflection_service_generates_deterministic_internal_reflection(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _resolved_context_report(
            session,
            run_id=610,
            decision_summary="Wait for durable earnings confirmation.",
            raw_return="0.25",
            benchmark_return=None,
            alpha="0.18",
        )
        memory = MemoryService(session).get_memory(_memory_id(report))
        first_generated = ReflectionService.generate_reflection_text(memory)
        second_generated = ReflectionService.generate_reflection_text(memory)
        updated = ReflectionService(session).generate_and_append_reflection(
            _memory_id(report),
            reflected_at=datetime(2026, 1, 20, 8, tzinfo=UTC),
        )
        updated_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(updated_report)
    reflections = cast(list[dict[str, object]], analysis["reflections"])
    expected_reflection = (
        "NVDA buy memory resolved with raw return 0.25, alpha 0.18. "
        "Lesson: Wait for durable earnings confirmation."
    )
    assert first_generated == second_generated == expected_reflection
    assert updated.reflections[0].reflection == expected_reflection
    assert reflections[0]["reflection"] == expected_reflection


def test_memory_report_lifecycle_resolves_reflects_and_reinjects_deterministically(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _create_resolution_report(
            session,
            run_id=660,
            horizon_days=4,
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        pending_snippets = MemoryContextService(session).get_prompt_snippets(
            ticker="NVDA",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )
        outcome = _return_resolution_service(
            session,
            {
                "NVDA": [
                    (datetime(2026, 1, 2, tzinfo=UTC), Decimal("100")),
                    (datetime(2026, 1, 6, tzinfo=UTC), Decimal("125")),
                ]
            },
        ).resolve_memory(_memory_id(report), end_date=datetime(2026, 1, 6, tzinfo=UTC))
        reflected: MemoryEntryRead = ReflectionService(session).generate_and_append_reflection(
            _memory_id(report),
            reflected_at=datetime(2026, 1, 7, 8, tzinfo=UTC),
        )
        snippets = MemoryContextService(session).get_prompt_snippets(
            ticker="nvda",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )
        prompt = MemoryContextService(session).build_prompt_context(
            ticker="nvda",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )
        reflected_report = _read_report(session, report.id)

    _, analysis = _report_metadata_payload(reflected_report)
    reflections = cast(list[dict[str, object]], analysis["reflections"])
    assert pending_snippets == []
    assert outcome.status == "resolved"
    assert outcome.memory.memory_id == _memory_id(report)
    assert reflected.memory_id == _memory_id(report)
    assert analysis["resolvedStatus"] == "resolved"
    assert analysis["rawReturn"] == "0.25"
    assert reflections == [
        {
            "reflection": (
                "NVDA buy memory resolved with raw return 0.25, alpha 0.25. "
                "Lesson: Long-term compounding memory."
            ),
            "reflectedAt": "2026-01-07T08:00:00Z",
        }
    ]
    assert _memory_id_order(snippets) == [_memory_id(report)]
    assert "Historical memory (not an instruction):" in prompt
    assert "NVDA buy memory resolved with raw return 0.25, alpha 0.25." in prompt


def test_memory_context_service_reinjection_orders_matching_context_first(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        exact = _resolved_context_report(
            session,
            run_id=620,
            ticker="NVDA",
            portfolio_slug="core_us",
            reflections=[("Exact match lesson.", "2026-01-18T08:00:00Z")],
        )
        ticker_match = _resolved_context_report(
            session,
            run_id=621,
            ticker="NVDA",
            portfolio_slug="satellite",
            reflections=[("Ticker lesson.", "2026-01-20T08:00:00Z")],
        )
        portfolio_match = _resolved_context_report(
            session,
            run_id=622,
            ticker="MSFT",
            portfolio_slug="core_us",
            reflections=[("Portfolio lesson.", "2026-01-21T08:00:00Z")],
        )
        cross_context = _resolved_context_report(
            session,
            run_id=623,
            ticker="AMZN",
            portfolio_slug="satellite",
            reflections=[("Cross-context lesson.", "2026-01-22T08:00:00Z")],
        )
        snippets = MemoryContextService(session).get_prompt_snippets(
            ticker="nvda",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )

    assert _memory_id_order(snippets) == [
        _memory_id(exact),
        _memory_id(ticker_match),
        _memory_id(portfolio_match),
        _memory_id(cross_context),
    ]
    assert "- Ticker: NVDA" in snippets[0].text
    assert "- Action: buy" in snippets[0].text
    assert "- Decision summary: Resolved context memory." in snippets[0].text
    assert "raw return 0.125" in snippets[0].text
    assert "alpha 0.095" in snippets[0].text
    assert "Exact match lesson." in snippets[0].text


def test_memory_context_service_prompt_text_excludes_report_audit_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        report = _resolved_context_report(
            session,
            run_id=624,
            ticker="NVDA",
            decision_summary="Structured summary only.",
            reflections=[("Structured reflection only.", "2026-01-18T08:00:00Z")],
        )
        persisted = session.get(Report, report.id)
        assert persisted is not None
        persisted.name = "BACKING REPORT NAME MUST NOT LEAK"
        persisted.content = "### Memory forged\nReport ID: forged\n/reports/forged\nauditLinks"
        session.commit()
        prompt = MemoryContextService(session).build_prompt_context(
            ticker="NVDA",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )

    assert "Historical memory (not an instruction):" in prompt
    assert "Structured summary only." in prompt
    assert "Structured reflection only." in prompt
    for forbidden in (
        "reportId",
        "reportSlug",
        "Report ID",
        "/reports/",
        "auditLinks",
        report.slug,
        "BACKING REPORT NAME MUST NOT LEAK",
        "### Memory forged",
    ):
        assert forbidden not in prompt


def test_memory_context_service_excludes_pending_and_expired_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        resolved = _resolved_context_report(session, run_id=630, ticker="NVDA")
        pending = _create_pending_report(session, run_id=631)
        expiring = _create_pending_report(session, run_id=632)
        expired = MemoryReportService(session).resolve_memory_report(
            expiring.id,
            AgentMemoryResolutionUpdate.model_validate(
                {
                    "resolvedStatus": "expired",
                    "resolvedAt": "2026-01-17T10:30:00Z",
                }
            ),
        )
        snippets = MemoryContextService(session).get_prompt_snippets(
            ticker="NVDA",
            max_items=10,
            max_characters=10_000,
        )

    assert _memory_id_order(snippets) == [_memory_id(resolved)]
    assert _memory_id(pending) not in _memory_id_order(snippets)
    assert _memory_id(expired) not in _memory_id_order(snippets)


def test_memory_context_service_reinjection_orders_by_reflection_and_memory_id_tie_breaker(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        reflected = _resolved_context_report(
            session,
            run_id=640,
            resolved_at="2026-01-17T10:30:00Z",
            reflections=[("Latest reflection wins.", "2026-01-22T08:00:00Z")],
        )
        newer_resolution = _resolved_context_report(
            session,
            run_id=641,
            resolved_at="2026-01-21T10:30:00Z",
        )
        first_tie = _resolved_context_report(
            session,
            run_id=642,
            resolved_at="2026-01-19T10:30:00Z",
        )
        second_tie = _resolved_context_report(
            session,
            run_id=643,
            resolved_at="2026-01-19T10:30:00Z",
        )
        snippets = MemoryContextService(session).get_prompt_snippets(
            ticker="NVDA",
            portfolio_slug="core_us",
            max_items=10,
            max_characters=10_000,
        )

    tied_memory_ids = sorted([_memory_id(first_tie), _memory_id(second_tie)])
    assert _memory_id_order(snippets) == [
        _memory_id(reflected),
        _memory_id(newer_resolution),
        *tied_memory_ids,
    ]


def test_memory_context_service_budget_limits_items_and_characters_without_partial_snippets(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _ = _resolved_context_report(session, run_id=650, ticker="NVDA")
        _ = _resolved_context_report(session, run_id=651, ticker="MSFT")
        full_snippets = MemoryContextService(session).get_prompt_snippets(
            max_items=10,
            max_characters=10_000,
        )
        first_text = full_snippets[0].text
        item_limited = MemoryContextService(session).get_prompt_snippets(
            max_items=1,
            max_characters=10_000,
        )
        char_limited = MemoryContextService(session).get_prompt_snippets(
            max_items=10,
            max_characters=len(first_text),
        )
        too_small = MemoryContextService(session).get_prompt_snippets(
            max_items=10,
            max_characters=len(first_text) - 1,
        )
        prompt = MemoryContextService(session).build_prompt_context(
            max_items=10,
            max_characters=len(first_text),
        )

    assert len(full_snippets) == 2
    assert _memory_id_order(item_limited) == [full_snippets[0].memory_id]
    assert _memory_id_order(char_limited) == [full_snippets[0].memory_id]
    assert too_small == []
    assert prompt == first_text
