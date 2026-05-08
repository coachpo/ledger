from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.schemas.memory import (
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryDecision,
    MemoryEntryRead,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
    MemoryWriteResult,
    format_report_backed_memory_id,
    parse_report_backed_memory_id,
)
from app.schemas.memory_report import (
    AgentMemoryReflectionAppend,
    AgentMemoryReportCreateMetadata,
    AgentMemoryResolutionUpdate,
    AgentMemoryServiceUpdate,
    AgentMemoryTrustedCreateContext,
)
from app.services.capability_service import CapabilityService
from app.services.memory_store import MemoryStore
from app.services.report_backed_memory_store import ReportBackedMemoryStore


class MemoryService:
    def __init__(self, session: Session, store: MemoryStore | None = None) -> None:
        self.session: Session = session
        self.store: MemoryStore = store if store is not None else ReportBackedMemoryStore(session)
        self.capability_service: CapabilityService = CapabilityService(
            session,
            get_default_tool_catalog(),
        )

    def write_memory(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        payload: MemoryWriteRequest,
    ) -> MemoryWriteResult:
        self.capability_service.require_report_memory_write_grant(
            capability_references=capability_references
        )
        try:
            result = self.store.create_pending(payload)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return result

    def get_memory(self, memory_id: str) -> MemoryEntryRead:
        return self.store.get(memory_id)

    def resolve_memory(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        try:
            entry = self.store.resolve(memory_id, outcome)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return entry

    def append_reflection(
        self,
        memory_id: str,
        reflection: MemoryReflection,
    ) -> MemoryEntryRead:
        try:
            entry = self.store.append_reflection(memory_id, reflection)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return entry

    def resolve_memory_report(
        self,
        report_id: int,
        resolution: AgentMemoryResolutionUpdate,
    ) -> MemoryEntryRead:
        return self.resolve_memory(
            self.memory_id_from_report_id(report_id),
            self.outcome_from_report_resolution(resolution),
        )

    def update_memory_report(
        self,
        report_id: int,
        payload: AgentMemoryServiceUpdate,
    ) -> MemoryEntryRead:
        memory_id = self.memory_id_from_report_id(report_id)
        try:
            if payload.resolution is not None:
                entry = self.store.resolve(
                    memory_id,
                    self.outcome_from_report_resolution(payload.resolution),
                )
            else:
                entry = self.store.get(memory_id)
            for reflection in payload.reflections:
                entry = self.store.append_reflection(
                    memory_id,
                    self.reflection_from_report_append(reflection),
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return entry

    def list_run_artifacts(self, run_id: int) -> list[MemoryArtifactRead]:
        return self.store.list_artifacts_for_run(run_id)

    def query_memory(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        return self.store.query(query)

    def get_audit_links(self, memory_id: str) -> MemoryAuditLinks:
        return self.store.audit_links(memory_id)

    @staticmethod
    def memory_id_from_report_id(report_id: int) -> str:
        return format_report_backed_memory_id(report_id)

    @staticmethod
    def report_id_from_memory_id(memory_id: str) -> int:
        return parse_report_backed_memory_id(memory_id)

    @staticmethod
    def write_request_from_report_create(
        *,
        payload: AgentMemoryReportCreateMetadata,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> MemoryWriteRequest:
        analysis = payload.analysis
        return MemoryWriteRequest(
            ticker=analysis.ticker,
            portfolio_slug=analysis.portfolio_slug,
            horizon_days=analysis.horizon_days,
            confidence=analysis.confidence,
            decision_summary=analysis.decision_summary,
            benchmark_symbol=analysis.benchmark_symbol,
            decision=MemoryDecision(
                action=analysis.decision.action,
                rationale=analysis.decision.rationale,
                risk_summary=analysis.decision.risk_summary,
                execution_plan=analysis.decision.execution_plan,
            ),
            provenance=MemoryProvenance(
                run_id=trusted_context.run_id,
                agent_key=trusted_context.agent_key,
                agent_version=trusted_context.agent_version,
                agent_name=trusted_context.agent_name,
                workflow_key=trusted_context.workflow_key,
                workflow_version=trusted_context.workflow_version,
                step_id=trusted_context.step_id,
                slot=trusted_context.slot,
                trace_id=trusted_context.trace_id,
            ),
        )

    @staticmethod
    def outcome_from_report_resolution(resolution: AgentMemoryResolutionUpdate) -> MemoryOutcome:
        return MemoryOutcome(
            resolved_status=resolution.resolved_status,
            resolved_at=resolution.resolved_at,
            raw_return=resolution.raw_return,
            benchmark_return=resolution.benchmark_return,
            alpha=resolution.alpha,
        )

    @staticmethod
    def reflection_from_report_append(reflection: AgentMemoryReflectionAppend) -> MemoryReflection:
        return MemoryReflection(
            reflection=reflection.reflection,
            reflected_at=reflection.reflected_at,
        )


__all__ = ["MemoryService"]
