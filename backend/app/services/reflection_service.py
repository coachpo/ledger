from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.formatting import decimal_to_string
from app.schemas.memory_report import AgentMemoryReflectionAppend, AgentMemoryReportAnalysis
from app.schemas.report import ReportRead
from app.services.memory_report_service import MemoryReportService


class ReflectionService:
    def __init__(self, session: Session) -> None:
        self.memory_report_service: MemoryReportService = MemoryReportService(session)

    def append_reflection(
        self,
        report_id: int,
        *,
        reflection: str,
        reflected_at: datetime,
    ) -> ReportRead:
        payload = AgentMemoryReflectionAppend(
            reflection=reflection,
            reflected_at=reflected_at,
        )
        return self.memory_report_service.append_reflection(report_id, payload)

    def generate_and_append_reflection(
        self,
        report_id: int,
        *,
        reflected_at: datetime,
    ) -> ReportRead:
        _, metadata = self.memory_report_service.get_memory_report_with_metadata(report_id)
        reflection = self.generate_reflection_text(metadata.analysis)
        return self.append_reflection(
            report_id,
            reflection=reflection,
            reflected_at=reflected_at,
        )

    @classmethod
    def generate_reflection_text(cls, analysis: AgentMemoryReportAnalysis) -> str:
        outcome = cls._outcome_summary(analysis)
        decision_summary = analysis.decision_summary or analysis.decision.rationale
        return (
            f"{analysis.ticker} {analysis.decision.action} memory resolved with {outcome}. "
            f"Lesson: {decision_summary}"
        )

    @staticmethod
    def _outcome_summary(analysis: AgentMemoryReportAnalysis) -> str:
        if analysis.raw_return is None or analysis.alpha is None:
            return f"status {analysis.resolved_status}"

        parts = [
            f"raw return {ReflectionService._format_decimal(analysis.raw_return)}",
            f"alpha {ReflectionService._format_decimal(analysis.alpha)}",
        ]
        if analysis.benchmark_return is not None:
            benchmark_return = ReflectionService._format_decimal(analysis.benchmark_return)
            parts.append(f"benchmark return {benchmark_return}")
        return ", ".join(parts)

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return decimal_to_string(value)


__all__ = ["ReflectionService"]
