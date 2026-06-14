from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.service_gate import (
    REFLECTION_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.schemas.memory import MemoryEntryRead, MemoryReflection
from app.services.memory_service import MemoryService


class ReflectionService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.memory_service: MemoryService = MemoryService(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=REFLECTION_SERVICE_SURFACE)

    def append_reflection(
        self,
        memory_id: str,
        *,
        reflection: str,
        reflected_at: datetime,
        commit: bool = True,
    ) -> MemoryEntryRead:
        self._require_enabled()
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
        ticker: str,
        action: str,
        decision_summary: str | None,
        reflected_at: datetime,
        commit: bool = True,
    ) -> MemoryEntryRead:
        self._require_enabled()
        memory = self.memory_service.get_memory(memory_id)
        reflection = self.generate_reflection_text(
            memory,
            ticker=ticker,
            action=action,
            decision_summary=decision_summary,
        )
        return self.append_reflection(
            memory_id,
            reflection=reflection,
            reflected_at=reflected_at,
            commit=commit,
        )

    @classmethod
    def generate_reflection_text(
        cls,
        memory: MemoryEntryRead,
        *,
        ticker: str,
        action: str,
        decision_summary: str | None,
    ) -> str:
        outcome = cls._outcome_summary(memory)
        lesson = decision_summary or "No decision summary provided."
        return f"{ticker} {action} memory resolved with {outcome}. Lesson: {lesson}"

    @staticmethod
    def _outcome_summary(memory: MemoryEntryRead) -> str:
        outcome = memory.outcome
        if outcome is None:
            return "visible to workflow" if memory.visible_to_workflow else "hidden from workflow"
        raw_return = outcome.attributes.get("rawReturn")
        alpha = outcome.attributes.get("alpha")
        if raw_return is None or alpha is None:
            return outcome.summary

        parts = [f"raw return {raw_return}", f"alpha {alpha}"]
        benchmark_return = outcome.attributes.get("benchmarkReturn")
        if benchmark_return is not None:
            parts.append(f"benchmark return {benchmark_return}")
        return ", ".join(parts)


__all__ = ["ReflectionService"]
