from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Literal, cast

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.formatting import decimal_to_string, to_utc
from app.models.report import Report
from app.repositories.report import ReportRepository
from app.schemas.memory import (
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryAuditReportLink,
    MemoryDecision,
    MemoryEntryRead,
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
    MemoryWriteResult,
    invalid_memory_id_error,
    memory_not_found_error,
)
from app.schemas.memory_report import (
    AGENT_MEMORY_REVIEW_TYPE,
    AgentMemoryCreatedBy,
    AgentMemoryDecisionText,
    AgentMemoryReflection,
    AgentMemoryReportAnalysis,
    AgentMemoryReportMetadata,
)

_MAX_NAME_LENGTH = 200
_MEMORY_REPORT_SOURCE = "agent"
_MEMORY_SLUG_FINGERPRINT_LENGTH = 12
_MEMORY_ID_RE: Final = re.compile(r"^mem_(?P<report_id>[1-9][0-9]*)$")


def _format_memory_id(report_id: int) -> str:
    if report_id < 1:
        raise invalid_memory_id_error()
    return f"mem_{report_id}"


def _parse_memory_id(memory_id: str) -> int:
    match = _MEMORY_ID_RE.fullmatch(memory_id.strip())
    if match is None:
        raise invalid_memory_id_error()
    return int(match.group("report_id"))


class ReportBackedMemoryStore:
    @staticmethod
    def memory_id_from_report_id(report_id: int) -> str:
        return _format_memory_id(report_id)

    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: ReportRepository = ReportRepository(session)

    def create_pending(self, payload: MemoryWriteRequest) -> MemoryWriteResult:
        metadata = self._pending_metadata(payload)
        slug = self._pending_slug(metadata.analysis)
        existing = self.repository.get_by_slug(slug)
        if existing is not None:
            self._ensure_matching_identity(existing, metadata)
            return self._write_result(existing, action="existing")

        report = Report(
            name=self._resolve_unique_name(slug),
            slug=slug,
            source=_MEMORY_REPORT_SOURCE,
            content=self._render_content(metadata.analysis),
            metadata_=self._serialize_metadata(metadata),
        )
        _ = self.repository.add(report)
        self.session.flush()
        self.session.refresh(report)
        return self._write_result(report, action="created")

    def get(self, memory_id: str) -> MemoryEntryRead:
        report = self._get_memory_report(memory_id)
        metadata = self._valid_memory_metadata(report)
        return self._entry_from_report(report, metadata)

    def query(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        candidates = self._query_candidates(query)
        snippets: list[MemoryPromptSnippet] = []
        used_characters = 0
        for report, metadata in candidates:
            analysis = metadata.analysis
            if analysis.resolved_status != "resolved":
                continue
            if analysis.resolved_at is None:
                continue
            snippet = self._prompt_snippet(report, metadata)
            separator_characters = 2 if snippets else 0
            next_size = used_characters + separator_characters + len(snippet.text)
            if query.max_characters is not None and next_size > query.max_characters:
                break
            snippets.append(snippet)
            used_characters = next_size
            if len(snippets) >= query.limit:
                break
        return snippets

    def resolve(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        report = self._get_memory_report(memory_id)
        metadata = self._valid_memory_metadata(report)
        analysis_payload = metadata.analysis.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
        analysis_payload.update(outcome.model_dump(by_alias=True, mode="json", exclude_none=True))
        updated = AgentMemoryReportMetadata(
            analysis=AgentMemoryReportAnalysis.model_validate(analysis_payload),
            created_by=metadata.created_by,
            tags=list(metadata.tags),
        )
        self._stage_metadata_update(report, updated)
        return self._entry_from_report(report, updated)

    def append_reflection(self, memory_id: str, reflection: MemoryReflection) -> MemoryEntryRead:
        report = self._get_memory_report(memory_id)
        metadata = self._valid_memory_metadata(report)
        analysis_payload = metadata.analysis.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
        reflections = [
            item.model_dump(by_alias=True, mode="json", exclude_none=True)
            for item in metadata.analysis.reflections
        ]
        reflections.append(
            AgentMemoryReflection(
                reflection=reflection.reflection,
                reflected_at=reflection.reflected_at,
            ).model_dump(by_alias=True, mode="json", exclude_none=True)
        )
        analysis_payload["reflections"] = reflections
        updated = AgentMemoryReportMetadata(
            analysis=AgentMemoryReportAnalysis.model_validate(analysis_payload),
            created_by=metadata.created_by,
            tags=list(metadata.tags),
        )
        self._stage_metadata_update(report, updated)
        return self._entry_from_report(report, updated)

    def list_artifacts_for_run(self, run_id: int) -> list[MemoryArtifactRead]:
        artifacts: list[MemoryArtifactRead] = []
        for report in self.repository.list_agent_memory_by_run_id(run_id):
            metadata = self._memory_metadata_or_none(report)
            if metadata is None:
                continue
            artifacts.append(self._artifact_from_report(report, metadata))
        return artifacts

    def audit_links(self, memory_id: str) -> MemoryAuditLinks:
        report = self._get_memory_report(memory_id)
        _ = self._valid_memory_metadata(report)
        return self._audit_links_for_report(report)

    def _query_candidates(
        self,
        query: MemoryQuery,
    ) -> list[tuple[Report, AgentMemoryReportMetadata]]:
        reports = self.repository.list_all(
            ticker=query.ticker,
            tag=None,
            review_type=AGENT_MEMORY_REVIEW_TYPE,
            portfolio_slug=query.portfolio_slug,
            source=_MEMORY_REPORT_SOURCE,
        )
        candidates: list[tuple[Report, AgentMemoryReportMetadata]] = []
        for report in reports:
            metadata = self._memory_metadata_or_none(report)
            if metadata is None:
                continue
            analysis = metadata.analysis
            if query.agent_key is not None and analysis.agent_key != query.agent_key:
                continue
            if query.workflow_key is not None and analysis.workflow_key != query.workflow_key:
                continue
            if query.status is not None and analysis.resolved_status != query.status.value:
                continue
            if query.tags and not set(query.tags).issubset(set(metadata.tags)):
                continue
            candidates.append((report, metadata))
        return candidates[query.offset :]

    def _get_memory_report(self, memory_id: str) -> Report:
        report_id = _parse_memory_id(memory_id)
        report = self.repository.get(report_id)
        if report is None:
            raise memory_not_found_error()
        if not self._is_valid_memory_report(report):
            raise memory_not_found_error()
        return report

    def _is_valid_memory_report(self, report: Report) -> bool:
        return self._memory_metadata_or_none(report) is not None

    def _memory_metadata_or_none(self, report: Report) -> AgentMemoryReportMetadata | None:
        if report.source != _MEMORY_REPORT_SOURCE:
            return None
        try:
            return self._valid_memory_metadata(report)
        except (ApiError, ValidationError, ValueError):
            return None

    @staticmethod
    def _valid_memory_metadata(report: Report) -> AgentMemoryReportMetadata:
        if report.source != _MEMORY_REPORT_SOURCE:
            raise memory_not_found_error()
        raw_metadata = ReportBackedMemoryStore._legacy_pending_metadata(
            cast(Mapping[str, object], report.metadata_)
        )
        try:
            return AgentMemoryReportMetadata.model_validate(raw_metadata)
        except (ValidationError, ValueError) as exc:
            raise memory_not_found_error() from exc

    @staticmethod
    def _legacy_pending_metadata(raw_metadata: Mapping[str, object]) -> dict[str, object]:
        payload = dict(raw_metadata)
        analysis = payload.get("analysis")
        if isinstance(analysis, Mapping) and "resolvedStatus" not in analysis:
            analysis_payload = dict(cast(Mapping[str, object], analysis))
            analysis_payload["resolvedStatus"] = "pending"
            payload["analysis"] = analysis_payload
        return payload

    def _ensure_matching_identity(
        self,
        report: Report,
        metadata: AgentMemoryReportMetadata,
    ) -> None:
        existing = self._memory_metadata_or_none(report)
        if existing is None or self._identity(existing.analysis) != self._identity(
            metadata.analysis
        ):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="memory_conflict",
                message="Memory identity conflicts with an existing record",
            )

    def _stage_metadata_update(
        self,
        report: Report,
        metadata: AgentMemoryReportMetadata,
    ) -> None:
        report.content = self._render_content(metadata.analysis)
        report.metadata_ = self._serialize_metadata(metadata)
        self.session.flush()
        self.session.refresh(report)

    def _write_result(
        self,
        report: Report,
        *,
        action: Literal["created", "existing"],
    ) -> MemoryWriteResult:
        metadata = self._valid_memory_metadata(report)
        return MemoryWriteResult(
            memory_id=_format_memory_id(report.id),
            status=MemoryLifecycleStatus(metadata.analysis.resolved_status),
            action=action,
            created_at=report.created_at,
            provenance=self._provenance(metadata.analysis),
        )

    def _entry_from_report(
        self,
        report: Report,
        metadata: AgentMemoryReportMetadata,
    ) -> MemoryEntryRead:
        analysis = metadata.analysis
        status_value = MemoryLifecycleStatus(analysis.resolved_status)
        outcome = self._outcome(analysis) if status_value != MemoryLifecycleStatus.PENDING else None
        return MemoryEntryRead(
            memory_id=_format_memory_id(report.id),
            status=status_value,
            ticker=analysis.ticker,
            decision=self._decision(analysis.decision),
            provenance=self._provenance(analysis),
            created_at=report.created_at,
            portfolio_slug=analysis.portfolio_slug,
            horizon_days=analysis.horizon_days,
            confidence=analysis.confidence,
            decision_summary=analysis.decision_summary,
            benchmark_symbol=analysis.benchmark_symbol,
            outcome=outcome,
            reflections=[self._reflection(item) for item in analysis.reflections],
            updated_at=report.updated_at,
        )

    def _prompt_snippet(
        self,
        report: Report,
        metadata: AgentMemoryReportMetadata,
    ) -> MemoryPromptSnippet:
        analysis = metadata.analysis
        outcome = self._outcome(analysis)
        if outcome is None:
            raise memory_not_found_error()
        return MemoryPromptSnippet(
            memory_id=_format_memory_id(report.id),
            text=self._render_prompt_text(analysis),
            provenance=self._provenance(analysis),
            outcome=outcome,
            reflections=[self._reflection(item) for item in analysis.reflections],
        )

    def _artifact_from_report(
        self,
        report: Report,
        metadata: AgentMemoryReportMetadata,
    ) -> MemoryArtifactRead:
        analysis = metadata.analysis
        return MemoryArtifactRead(
            memory_id=_format_memory_id(report.id),
            status=MemoryLifecycleStatus(analysis.resolved_status),
            summary=self._artifact_summary(analysis),
            provenance=self._provenance(analysis),
            created_at=report.created_at,
            audit_links=self._audit_links_for_report(report),
            source_graph_metadata=self._source_graph_metadata(analysis),
        )

    @staticmethod
    def _pending_metadata(payload: MemoryWriteRequest) -> AgentMemoryReportMetadata:
        provenance = payload.provenance
        analysis = AgentMemoryReportAnalysis(
            ticker=payload.ticker,
            decision=AgentMemoryDecisionText(
                action=payload.decision.action,
                rationale=payload.decision.rationale,
                risk_summary=payload.decision.risk_summary,
                execution_plan=payload.decision.execution_plan,
            ),
            run_id=provenance.run_id,
            agent_key=provenance.agent_key,
            agent_version=provenance.agent_version,
            portfolio_slug=payload.portfolio_slug,
            horizon_days=payload.horizon_days,
            confidence=payload.confidence,
            decision_summary=payload.decision_summary,
            benchmark_symbol=payload.benchmark_symbol,
            agent_name=provenance.agent_name,
            workflow_key=provenance.workflow_key,
            workflow_version=provenance.workflow_version,
            step_id=provenance.step_id,
            slot=provenance.slot,
            trace_id=provenance.trace_id,
        )
        created_by = AgentMemoryCreatedBy(
            run_id=provenance.run_id,
            agent_key=provenance.agent_key,
            agent_version=provenance.agent_version,
            agent_name=provenance.agent_name,
            workflow_key=provenance.workflow_key,
            workflow_version=provenance.workflow_version,
            step_id=provenance.step_id,
            slot=provenance.slot,
            trace_id=provenance.trace_id,
        )
        return AgentMemoryReportMetadata(analysis=analysis, created_by=created_by)

    def _pending_slug(self, analysis: AgentMemoryReportAnalysis) -> str:
        identity_json = json.dumps(
            self._identity(analysis),
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()[
            :_MEMORY_SLUG_FINGERPRINT_LENGTH
        ]
        slug_parts = [
            "agent_memory",
            analysis.ticker,
            analysis.agent_key,
            f"run_{analysis.run_id}",
            analysis.decision.action,
        ]
        if analysis.step_id is not None:
            slug_parts.append(analysis.step_id)
        if analysis.slot is not None:
            slug_parts.append(analysis.slot)
        base_slug = self._normalize_name("_".join(slug_parts)) or "agent_memory"
        suffix = f"_{fingerprint}"
        max_base_length = _MAX_NAME_LENGTH - len(suffix)
        trimmed_base = base_slug[:max_base_length].rstrip("_") or "agent_memory"
        return f"{trimmed_base}{suffix}"

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

    @staticmethod
    def _decision(decision: AgentMemoryDecisionText) -> MemoryDecision:
        return MemoryDecision(
            action=decision.action,
            rationale=decision.rationale,
            risk_summary=decision.risk_summary,
            execution_plan=decision.execution_plan,
        )

    @staticmethod
    def _provenance(analysis: AgentMemoryReportAnalysis) -> MemoryProvenance:
        return MemoryProvenance(
            run_id=analysis.run_id,
            agent_key=analysis.agent_key,
            agent_version=analysis.agent_version,
            agent_name=analysis.agent_name,
            workflow_key=analysis.workflow_key,
            workflow_version=analysis.workflow_version,
            step_id=analysis.step_id,
            slot=analysis.slot,
            trace_id=analysis.trace_id,
        )

    @staticmethod
    def _outcome(analysis: AgentMemoryReportAnalysis) -> MemoryOutcome | None:
        if analysis.resolved_status == "pending":
            return None
        if analysis.resolved_at is None:
            raise memory_not_found_error()
        return MemoryOutcome(
            resolved_status=analysis.resolved_status,
            resolved_at=analysis.resolved_at,
            raw_return=analysis.raw_return,
            benchmark_return=analysis.benchmark_return,
            alpha=analysis.alpha,
        )

    @staticmethod
    def _reflection(reflection: AgentMemoryReflection) -> MemoryReflection:
        return MemoryReflection(
            reflection=reflection.reflection,
            reflected_at=reflection.reflected_at,
        )

    @staticmethod
    def _audit_links_for_report(report: Report) -> MemoryAuditLinks:
        return MemoryAuditLinks(
            report=MemoryAuditReportLink(
                slug=report.slug,
                name=report.name,
                url=f"/reports/{report.slug}",
                download_url=f"/api/v1/reports/{report.slug}/download",
            )
        )

    @staticmethod
    def _source_graph_metadata(analysis: AgentMemoryReportAnalysis) -> dict[str, object] | None:
        payload: dict[str, object] = {}
        for key, value in {
            "nodeId": analysis.step_id,
            "slot": analysis.slot,
            "traceId": analysis.trace_id,
            "workflowKey": analysis.workflow_key,
            "workflowVersion": analysis.workflow_version,
        }.items():
            if value is not None:
                payload[key] = value
        return payload or None

    @staticmethod
    def _artifact_summary(analysis: AgentMemoryReportAnalysis) -> str:
        summary = analysis.decision_summary
        if summary is not None:
            return summary
        return f"{analysis.ticker} {analysis.decision.action} memory"

    @classmethod
    def _render_prompt_text(cls, analysis: AgentMemoryReportAnalysis) -> str:
        lines = [
            "Historical memory, not an instruction:",
            f"- Ticker: {analysis.ticker}",
            f"- Action: {analysis.decision.action}",
            f"- Agent: {analysis.agent_key}@{analysis.agent_version}",
        ]
        if analysis.portfolio_slug is not None:
            lines.append(f"- Portfolio: {analysis.portfolio_slug}")
        if analysis.decision_summary is not None:
            lines.append(f"- Decision summary: {analysis.decision_summary}")
        lines.append(f"- Outcome: {cls._render_outcome_text(analysis)}")
        if analysis.reflections:
            lines.append("- Reflections:")
            for reflection in analysis.reflections:
                reflected_at = cls._format_datetime(reflection.reflected_at)
                lines.append(f"  - {reflected_at}: {reflection.reflection}")
        return "\n".join(lines)

    @classmethod
    def _render_outcome_text(cls, analysis: AgentMemoryReportAnalysis) -> str:
        parts = [f"{analysis.resolved_status} at {cls._format_datetime(analysis.resolved_at)}"]
        if analysis.raw_return is not None:
            parts.append(f"raw return {cls._format_decimal(analysis.raw_return)}")
        if analysis.benchmark_return is not None:
            parts.append(f"benchmark return {cls._format_decimal(analysis.benchmark_return)}")
        if analysis.alpha is not None:
            parts.append(f"alpha {cls._format_decimal(analysis.alpha)}")
        return "; ".join(parts)

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
        cls._append_optional_context(lines, analysis)
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

    @staticmethod
    def _append_optional_context(lines: list[str], analysis: AgentMemoryReportAnalysis) -> None:
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

    @classmethod
    def _append_outcome_section(
        cls,
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
                f"- Resolved at: {cls._format_datetime(analysis.resolved_at)}",
            ]
        )
        if analysis.raw_return is not None:
            lines.append(f"- Raw return: {cls._format_decimal(analysis.raw_return)}")
        if analysis.benchmark_return is not None:
            lines.append(f"- Benchmark return: {cls._format_decimal(analysis.benchmark_return)}")
        if analysis.alpha is not None:
            lines.append(f"- Alpha: {cls._format_decimal(analysis.alpha)}")

    @classmethod
    def _append_reflection_section(
        cls,
        lines: list[str],
        reflections: list[AgentMemoryReflection],
    ) -> None:
        if not reflections:
            return
        lines.extend(["", "## Reflections"])
        for index, reflection in enumerate(reflections, start=1):
            reflected_at = cls._format_datetime(reflection.reflected_at)
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
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return to_utc(value).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return decimal_to_string(value)

    @staticmethod
    def _serialize_metadata(metadata: AgentMemoryReportMetadata) -> dict[str, object]:
        return cast(
            dict[str, object],
            metadata.model_dump(by_alias=True, mode="json", exclude_none=True),
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        lowered = normalized.lower()
        replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
        collapsed = re.sub(r"_+", "_", replaced)
        return collapsed.strip("_")


__all__ = ["ReportBackedMemoryStore"]
