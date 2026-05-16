from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import cast

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error
from app.core.formatting import decimal_to_string, to_utc
from app.extensions.signaldeck_finance.hooks import (
    MEMORY_REPORT_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.models.report import Report
from app.repositories.report import ReportRepository
from app.schemas.memory_report import (
    AgentMemoryModelInput,
    AgentMemoryReflection,
    AgentMemoryReflectionAppend,
    AgentMemoryReportAnalysis,
    AgentMemoryReportCreateMetadata,
    AgentMemoryReportMetadata,
    AgentMemoryResolutionUpdate,
    AgentMemoryServiceUpdate,
    AgentMemoryTrustedCreateContext,
)
from app.schemas.report import ReportRead
from app.services.memory_service import MemoryService

_MAX_NAME_LENGTH = 200
_MEMORY_REPORT_SOURCE = "agent"
_MEMORY_SLUG_FINGERPRINT_LENGTH = 12


class MemoryReportService:
    """Compatibility adapter that delegates command writes through MemoryService."""

    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: ReportRepository = ReportRepository(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=MEMORY_REPORT_SERVICE_SURFACE)

    def create_pending_report(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        payload: AgentMemoryReportCreateMetadata,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> ReportRead:
        self._require_enabled()
        memory_service = MemoryService(self.session)
        slug = self._pending_slug(model_input=payload.analysis, trusted_context=trusted_context)
        _ = memory_service.write_memory(
            capability_references=capability_references,
            payload=memory_service.write_request_from_report_create(
                payload=payload,
                trusted_context=trusted_context,
            ),
        )
        report = self.repository.get_by_slug(slug)
        if report is None:
            raise not_found_error("Report")
        return self._read_existing_memory_report(
            report,
            metadata=AgentMemoryReportMetadata.model_validate(report.metadata_),
        )

    def update_memory_report(
        self,
        report_id: int,
        payload: AgentMemoryServiceUpdate,
    ) -> ReportRead:
        self._require_enabled()
        report = self._get_memory_report_model(report_id)
        return self._apply_service_update(report=report, payload=payload)

    def resolve_memory_report(
        self,
        report_id: int,
        resolution: AgentMemoryResolutionUpdate,
    ) -> ReportRead:
        return self.update_memory_report(
            report_id,
            AgentMemoryServiceUpdate(resolution=resolution),
        )

    def append_reflection(
        self,
        report_id: int,
        reflection: AgentMemoryReflectionAppend,
    ) -> ReportRead:
        return self.update_memory_report(
            report_id,
            AgentMemoryServiceUpdate(reflections=[reflection]),
        )

    def get_memory_report_with_metadata(
        self,
        report_id: int,
    ) -> tuple[Report, AgentMemoryReportMetadata]:
        self._require_enabled()
        report = self._get_memory_report_model(report_id)
        return report, self._validate_existing_memory_metadata(report)

    def _get_memory_report_model(self, report_id: int) -> Report:
        report = self.repository.get(report_id)
        if report is None:
            raise not_found_error("Report")
        return report

    def _apply_service_update(
        self,
        *,
        report: Report,
        payload: AgentMemoryServiceUpdate,
    ) -> ReportRead:
        _ = self._validate_existing_memory_metadata(report)
        _ = MemoryService(self.session).update_memory_report(report.id, payload)
        return self._read_memory_report(report.id)

    def _read_memory_report(self, report_id: int) -> ReportRead:
        report = self._get_memory_report_model(report_id)
        return ReportRead.model_validate(report)

    def _read_existing_memory_report(
        self,
        report: Report,
        *,
        metadata: AgentMemoryReportMetadata,
    ) -> ReportRead:
        self._ensure_matching_memory_identity(report, metadata=metadata)
        return ReportRead.model_validate(report)

    def _ensure_matching_memory_identity(
        self,
        report: Report,
        *,
        metadata: AgentMemoryReportMetadata,
    ) -> None:
        if report.source != _MEMORY_REPORT_SOURCE:
            raise self._conflict(report.slug)

        try:
            existing_metadata = AgentMemoryReportMetadata.model_validate(report.metadata_)
        except ValueError as exc:
            raise self._conflict(report.slug) from exc

        if self._identity(existing_metadata.analysis) != self._identity(metadata.analysis):
            raise self._conflict(report.slug)

    def _validate_existing_memory_metadata(self, report: Report) -> AgentMemoryReportMetadata:
        if report.source != _MEMORY_REPORT_SOURCE:
            raise self._invalid_memory_report(report.slug)

        try:
            return AgentMemoryReportMetadata.model_validate(report.metadata_)
        except ValueError as exc:
            raise self._invalid_memory_report(report.slug) from exc

    def _apply_update_to_metadata(
        self,
        metadata: AgentMemoryReportMetadata,
        *,
        payload: AgentMemoryServiceUpdate,
    ) -> AgentMemoryReportMetadata:
        analysis_payload = metadata.analysis.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )

        if payload.resolution is not None:
            analysis_payload.update(
                payload.resolution.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude_none=True,
                )
            )

        if payload.reflections:
            reflections = [
                reflection.model_dump(by_alias=True, mode="json")
                for reflection in metadata.analysis.reflections
            ]
            reflections.extend(
                AgentMemoryReflection.model_validate(reflection).model_dump(
                    by_alias=True,
                    mode="json",
                )
                for reflection in payload.reflections
            )
            analysis_payload["reflections"] = reflections

        return AgentMemoryReportMetadata(
            analysis=AgentMemoryReportAnalysis.model_validate(analysis_payload),
            created_by=metadata.created_by,
            tags=list(metadata.tags),
        )

    def _pending_slug(
        self,
        *,
        model_input: AgentMemoryModelInput,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> str:
        identity_payload = self._identity_payload(
            model_input=model_input,
            trusted_context=trusted_context,
        )
        identity_json = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()[
            :_MEMORY_SLUG_FINGERPRINT_LENGTH
        ]
        slug_parts = [
            "agent_memory",
            model_input.ticker,
            trusted_context.agent_key,
            f"run_{trusted_context.run_id}",
            model_input.decision.action,
        ]
        if trusted_context.step_id is not None:
            slug_parts.append(trusted_context.step_id)
        if trusted_context.slot is not None:
            slug_parts.append(trusted_context.slot)

        base_slug = self._normalize_name("_".join(slug_parts)) or "agent_memory"
        suffix = f"_{fingerprint}"
        max_base_length = _MAX_NAME_LENGTH - len(suffix)
        trimmed_base = base_slug[:max_base_length].rstrip("_") or "agent_memory"
        return f"{trimmed_base}{suffix}"

    @staticmethod
    def _identity_payload(
        *,
        model_input: AgentMemoryModelInput,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> dict[str, object]:
        return {
            "action": model_input.decision.action,
            "agentKey": trusted_context.agent_key,
            "agentVersion": trusted_context.agent_version,
            "benchmarkSymbol": model_input.benchmark_symbol,
            "horizonDays": model_input.horizon_days,
            "portfolioSlug": model_input.portfolio_slug,
            "runId": trusted_context.run_id,
            "slot": trusted_context.slot,
            "stepId": trusted_context.step_id,
            "ticker": model_input.ticker,
            "workflowKey": trusted_context.workflow_key,
            "workflowVersion": trusted_context.workflow_version,
        }

    @staticmethod
    def _identity(analysis: AgentMemoryReportAnalysis) -> dict[str, object]:
        return {
            "action": analysis.decision.action,
            "agentKey": analysis.agent_key,
            "agentVersion": analysis.agent_version,
            "benchmarkSymbol": analysis.benchmark_symbol,
            "horizonDays": analysis.horizon_days,
            "portfolioSlug": analysis.portfolio_slug,
            "runId": analysis.run_id,
            "slot": analysis.slot,
            "stepId": analysis.step_id,
            "ticker": analysis.ticker,
            "workflowKey": analysis.workflow_key,
            "workflowVersion": analysis.workflow_version,
        }

    def _resolve_unique_name(self, base_name: str) -> str:
        if self.repository.get_by_name(base_name) is None:
            return base_name

        counter = 2
        while True:
            suffix = f"_{counter}"
            max_base_length = _MAX_NAME_LENGTH - len(suffix)
            trimmed_base = base_name[:max_base_length].rstrip("_") or "agent_memory"
            candidate = f"{trimmed_base}{suffix}"
            if self.repository.get_by_name(candidate) is None:
                return candidate
            counter += 1

    @classmethod
    def _render_content(cls, analysis: AgentMemoryReportAnalysis) -> str:
        lines = [
            f"# Agent Memory: {analysis.ticker}",
            "",
            f"Status: {analysis.resolved_status}",
            "",
            "## Context",
            f"- Run ID: {analysis.run_id}",
            f"- Agent: {analysis.agent_key}@{analysis.agent_version}",
            f"- Ticker: {analysis.ticker}",
            f"- Decision: {analysis.decision.action}",
        ]
        if analysis.portfolio_slug is not None:
            lines.append(f"- Portfolio: {analysis.portfolio_slug}")
        if analysis.horizon_days is not None:
            lines.append(f"- Horizon days: {analysis.horizon_days}")
        if analysis.confidence is not None:
            lines.append(f"- Confidence: {analysis.confidence}")
        if analysis.benchmark_symbol is not None:
            lines.append(f"- Benchmark symbol: {analysis.benchmark_symbol}")
        if analysis.workflow_key is not None:
            workflow = analysis.workflow_key
            if analysis.workflow_version is not None:
                workflow = f"{workflow}@{analysis.workflow_version}"
            lines.append(f"- Workflow: {workflow}")
        if analysis.step_id is not None:
            lines.append(f"- Step ID: {analysis.step_id}")
        if analysis.slot is not None:
            lines.append(f"- Slot: {analysis.slot}")
        if analysis.trace_id is not None:
            lines.append(f"- Trace ID: {analysis.trace_id}")

        lines.extend(
            [
                "",
                "## Decision Summary",
                analysis.decision_summary or "Pending decision memory awaiting outcome resolution.",
                "",
                "## Rationale",
                analysis.decision.rationale,
                "",
                "## Risk Summary",
                analysis.decision.risk_summary,
                "",
                "## Execution Plan",
                analysis.decision.execution_plan,
            ]
        )
        cls._append_outcome_section(lines, analysis)
        cls._append_reflection_section(lines, analysis.reflections)
        return "\n".join(lines).strip() + "\n"

    @classmethod
    def _pending_content(cls, analysis: AgentMemoryReportAnalysis) -> str:
        return cls._render_content(analysis)

    @staticmethod
    def _append_outcome_section(
        lines: list[str],
        analysis: AgentMemoryReportAnalysis,
    ) -> None:
        if analysis.resolved_status == "pending":
            return

        lines.extend(
            [
                "",
                "## Outcome",
                f"- Status: {analysis.resolved_status}",
                f"- Resolved at: {MemoryReportService._format_datetime(analysis.resolved_at)}",
            ]
        )
        if analysis.raw_return is not None:
            raw_return = MemoryReportService._format_decimal(analysis.raw_return)
            lines.append(f"- Raw return: {raw_return}")
        if analysis.benchmark_return is not None:
            benchmark_return = MemoryReportService._format_decimal(analysis.benchmark_return)
            lines.append(f"- Benchmark return: {benchmark_return}")
        if analysis.alpha is not None:
            alpha = MemoryReportService._format_decimal(analysis.alpha)
            lines.append(f"- Alpha: {alpha}")

    @staticmethod
    def _append_reflection_section(
        lines: list[str],
        reflections: list[AgentMemoryReflection],
    ) -> None:
        if not reflections:
            return

        lines.extend(["", "## Reflections"])
        for index, reflection in enumerate(reflections, start=1):
            reflected_at = MemoryReportService._format_datetime(reflection.reflected_at)
            lines.extend(
                [
                    f"### Reflection {index}",
                    f"- Reflected at: {reflected_at}",
                    "",
                    reflection.reflection,
                ]
            )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            raise ValueError("Timestamp is required")
        return to_utc(value).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return decimal_to_string(value)

    @staticmethod
    def _serialize_metadata(metadata: AgentMemoryReportMetadata) -> dict[str, object]:
        payload = metadata.model_dump(by_alias=True, mode="json", exclude_none=True)
        return cast(dict[str, object], payload)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        lowered = normalized.lower()
        replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
        collapsed = re.sub(r"_+", "_", replaced)
        return collapsed.strip("_")

    @staticmethod
    def _conflict(slug: str) -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="memory_report_conflict",
            message=f'Report slug "{slug}" is not available for agent memory',
        )

    @staticmethod
    def _invalid_memory_report(slug: str) -> ApiError:
        return ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_memory_report",
            message=f'Report slug "{slug}" is not an agent-memory report',
        )


__all__ = ["MemoryReportService"]
