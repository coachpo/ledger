from __future__ import annotations

from collections.abc import Sequence

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error
from app.models.report import Report
from app.repositories.report import ReportRepository
from app.schemas.memory_report import (
    AgentMemoryReflectionAppend,
    AgentMemoryReportCreateMetadata,
    AgentMemoryReportMetadata,
    AgentMemoryResolutionUpdate,
    AgentMemoryServiceUpdate,
    AgentMemoryTrustedCreateContext,
)
from app.schemas.report import ReportRead
from app.services.capability_service import RuntimeToolGrantPolicy
from app.services.extension_gate import (
    MEMORY_REPORT_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)

_MEMORY_REPORT_SOURCE = "agent"
_RETIRED_MESSAGE = (
    "Report-backed memory lifecycle writes are retired. Legacy agent_memory "
    "reports remain readable as historical report-domain artifacts only."
)


class MemoryReportService:
    """Historical report metadata adapter; not a canonical memory writer."""

    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: ReportRepository = ReportRepository(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=MEMORY_REPORT_SERVICE_SURFACE)

    def create_pending_report(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
        payload: AgentMemoryReportCreateMetadata,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> ReportRead:
        del capability_references, grant_policy, payload, trusted_context
        self._require_enabled()
        raise self._retired_error()

    def update_memory_report(
        self,
        report_id: int,
        payload: AgentMemoryServiceUpdate,
    ) -> ReportRead:
        del report_id, payload
        self._require_enabled()
        raise self._retired_error()

    def resolve_memory_report(
        self,
        report_id: int,
        resolution: AgentMemoryResolutionUpdate,
    ) -> ReportRead:
        del report_id, resolution
        self._require_enabled()
        raise self._retired_error()

    def append_reflection(
        self,
        report_id: int,
        reflection: AgentMemoryReflectionAppend,
    ) -> ReportRead:
        del report_id, reflection
        self._require_enabled()
        raise self._retired_error()

    def get_memory_report_with_metadata(
        self,
        report_id: int,
    ) -> tuple[Report, AgentMemoryReportMetadata]:
        self._require_enabled()
        report = self._get_memory_report_model(report_id)
        return report, self._validate_existing_memory_metadata(report)

    def read_historical_memory_report(self, report_id: int) -> ReportRead:
        report, _ = self.get_memory_report_with_metadata(report_id)
        return ReportRead.model_validate(report)

    def _get_memory_report_model(self, report_id: int) -> Report:
        report = self.repository.get(report_id)
        if report is None:
            raise not_found_error("Report")
        return report

    def _validate_existing_memory_metadata(self, report: Report) -> AgentMemoryReportMetadata:
        if report.source != _MEMORY_REPORT_SOURCE:
            raise self._invalid_memory_report(report.slug)
        try:
            return AgentMemoryReportMetadata.model_validate(report.metadata_)
        except (ValidationError, ValueError) as exc:
            raise self._invalid_memory_report(report.slug) from exc

    @staticmethod
    def _retired_error() -> ApiError:
        return ApiError(
            status_code=status.HTTP_410_GONE,
            code="memory_report_lifecycle_retired",
            message=_RETIRED_MESSAGE,
        )

    @staticmethod
    def _invalid_memory_report(slug: str) -> ApiError:
        return ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_memory_report",
            message=f'Report slug "{slug}" is not an agent-memory report',
        )


__all__ = ["MemoryReportService"]
