from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.formatting import to_utc
from app.models.agent_memory import AgentMemoryEntry
from app.schemas.memory import MemoryEntryRead
from app.services.memory_service import MemoryService


@dataclass(frozen=True, slots=True)
class MemoryFollowUpEvaluation:
    visible_to_workflow: bool
    reason: str | None = None
    reflected: bool = False
    event_recorded: bool = False
    result_snapshot: dict[str, object] = field(default_factory=dict)
    status_snapshot: dict[str, object] = field(default_factory=dict)


class MemoryFollowUpEvaluator(Protocol):
    evaluator_key: str
    memory_kinds: frozenset[str]

    def evaluate(
        self,
        memory: MemoryEntryRead,
        *,
        reviewed_at: datetime,
    ) -> MemoryFollowUpEvaluation: ...


@dataclass(frozen=True, slots=True)
class MemoryFollowUpItem:
    memory_id: str
    visible_to_workflow: bool
    reason: str | None
    reflected: bool


@dataclass(frozen=True, slots=True)
class MemoryFollowUpRunResult:
    checked: int
    made_workflow_visible: int
    kept_workflow_hidden: int
    reflected: int
    items: tuple[MemoryFollowUpItem, ...]


class MemoryFollowUpService:
    def __init__(
        self,
        session: Session,
        *,
        evaluators: Sequence[MemoryFollowUpEvaluator] = (),
    ) -> None:
        self.session: Session = session
        self.memory_service: MemoryService = MemoryService(session)
        self.evaluators: tuple[MemoryFollowUpEvaluator, ...] = tuple(evaluators)

    def run_due(self, now: datetime) -> MemoryFollowUpRunResult:
        reviewed_at = to_utc(now)
        items: list[MemoryFollowUpItem] = []

        try:
            for memory in self._hidden_memories():
                evaluator = self._evaluator_for(memory)
                evaluation = self._evaluate(
                    memory,
                    evaluator=evaluator,
                    reviewed_at=reviewed_at,
                )
                if not evaluation.event_recorded:
                    self._record_review_event(
                        memory,
                        evaluator_key=None if evaluator is None else evaluator.evaluator_key,
                        evaluation=evaluation,
                        reviewed_at=reviewed_at,
                    )
                items.append(
                    MemoryFollowUpItem(
                        memory_id=memory.memory_id,
                        visible_to_workflow=evaluation.visible_to_workflow,
                        reason=evaluation.reason,
                        reflected=evaluation.reflected,
                    )
                )
            if items:
                self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return self._result(items)

    def _evaluate(
        self,
        memory: MemoryEntryRead,
        *,
        evaluator: MemoryFollowUpEvaluator | None,
        reviewed_at: datetime,
    ) -> MemoryFollowUpEvaluation:
        if evaluator is None:
            return MemoryFollowUpEvaluation(
                visible_to_workflow=False,
                reason="no_evaluator",
                result_snapshot={"scheduler": "core.memory_follow_up"},
            )
        return evaluator.evaluate(memory, reviewed_at=reviewed_at)

    def _evaluator_for(self, memory: MemoryEntryRead) -> MemoryFollowUpEvaluator | None:
        return next(
            (
                evaluator
                for evaluator in self.evaluators
                if not evaluator.memory_kinds or memory.kind in evaluator.memory_kinds
            ),
            None,
        )

    def _record_review_event(
        self,
        memory: MemoryEntryRead,
        *,
        evaluator_key: str | None,
        evaluation: MemoryFollowUpEvaluation,
        reviewed_at: datetime,
    ) -> None:
        result_snapshot: dict[str, object] = {
            "memoryId": memory.memory_id,
            "memoryKind": memory.kind,
            "scheduler": "core.memory_follow_up",
            "visibleToWorkflow": evaluation.visible_to_workflow,
            "reviewedAt": reviewed_at.isoformat().replace("+00:00", "Z"),
        }
        if evaluator_key is not None:
            result_snapshot["evaluator"] = evaluator_key
        if evaluation.reason is not None:
            result_snapshot["reason"] = evaluation.reason
        result_snapshot.update(evaluation.result_snapshot)

        status_snapshot: dict[str, object] = {"visibleToWorkflow": evaluation.visible_to_workflow}
        if evaluation.reason is not None:
            status_snapshot["reason"] = evaluation.reason
        status_snapshot.update(evaluation.status_snapshot)

        _ = self.memory_service.record_review_event(
            memory.memory_id,
            filters={
                "scheduler": "core.memory_follow_up",
                "memoryKind": memory.kind,
                "evaluator": evaluator_key,
            },
            result_snapshot=result_snapshot,
            status_snapshot=status_snapshot,
            commit=False,
        )

    def _hidden_memories(self) -> list[MemoryEntryRead]:
        statement = (
            select(AgentMemoryEntry.memory_id)
            .where(AgentMemoryEntry.visible_to_workflow.is_(False))
            .order_by(AgentMemoryEntry.created_at.asc(), AgentMemoryEntry.id.asc())
        )
        hidden: list[MemoryEntryRead] = []
        for memory_id in self.session.scalars(statement):
            try:
                memory = self.memory_service.get_memory(memory_id)
            except ApiError:
                continue
            if not memory.visible_to_workflow:
                hidden.append(memory)
        return hidden

    @staticmethod
    def _result(items: list[MemoryFollowUpItem]) -> MemoryFollowUpRunResult:
        return MemoryFollowUpRunResult(
            checked=len(items),
            made_workflow_visible=sum(item.visible_to_workflow for item in items),
            kept_workflow_hidden=sum(not item.visible_to_workflow for item in items),
            reflected=sum(item.reflected for item in items),
            items=tuple(items),
        )


__all__ = [
    "MemoryFollowUpEvaluation",
    "MemoryFollowUpEvaluator",
    "MemoryFollowUpItem",
    "MemoryFollowUpRunResult",
    "MemoryFollowUpService",
]
