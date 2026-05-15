from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.formatting import decimal_to_string
from app.schemas.memory import MemoryEntryRead, MemoryReflection
from app.services.memory_service import MemoryService


class ReflectionService:
    def __init__(self, session: Session) -> None:
        self.memory_service: MemoryService = MemoryService(session)

    def append_reflection(
        self,
        memory_id: str,
        *,
        reflection: str,
        reflected_at: datetime,
        commit: bool = True,
    ) -> MemoryEntryRead:
        payload = MemoryReflection(
            reflection=reflection,
            reflected_at=reflected_at,
        )
        return self.memory_service.append_reflection(
            memory_id,
            payload,
            commit=commit,
        )

    def generate_and_append_reflection(
        self,
        memory_id: str,
        *,
        reflected_at: datetime,
        commit: bool = True,
    ) -> MemoryEntryRead:
        memory = self.memory_service.get_memory(memory_id)
        reflection = self.generate_reflection_text(memory)
        return self.append_reflection(
            memory_id,
            reflection=reflection,
            reflected_at=reflected_at,
            commit=commit,
        )

    @classmethod
    def generate_reflection_text(cls, memory: MemoryEntryRead) -> str:
        outcome = cls._outcome_summary(memory)
        decision_summary = memory.decision_summary or memory.decision.rationale
        return (
            f"{memory.ticker} {memory.decision.action} memory resolved with {outcome}. "
            f"Lesson: {decision_summary}"
        )

    @staticmethod
    def _outcome_summary(memory: MemoryEntryRead) -> str:
        outcome = memory.outcome
        if outcome is None or outcome.raw_return is None or outcome.alpha is None:
            return f"status {memory.status.value}"

        parts = [
            f"raw return {ReflectionService._format_decimal(outcome.raw_return)}",
            f"alpha {ReflectionService._format_decimal(outcome.alpha)}",
        ]
        if outcome.benchmark_return is not None:
            benchmark_return = ReflectionService._format_decimal(outcome.benchmark_return)
            parts.append(f"benchmark return {benchmark_return}")
        return ", ".join(parts)

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return decimal_to_string(value)


__all__ = ["ReflectionService"]
