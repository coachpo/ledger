from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
    review_action: str = "follow_up_reviewed"
    outcome_summary: str | None = None
    reflection_summary: str | None = None
    reflection_source: str | None = None


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
                outcome_summary="no_evaluator",
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
    ) -> None:
        result_snapshot: dict[str, object] = {
            "memoryId": memory.memory_id,
            "revisionId": memory.revision_id,
            "reviewAction": evaluation.review_action,
        }
        outcome_summary = evaluation.outcome_summary or evaluation.reason
        if outcome_summary is not None:
            result_snapshot["outcomeSummary"] = outcome_summary
        if evaluation.reflection_summary is not None:
            result_snapshot["reflectionSummary"] = evaluation.reflection_summary
        if evaluation.reflection_source is not None:
            result_snapshot["reflectionSource"] = evaluation.reflection_source

        status_snapshot: dict[str, object] = {"visibleToWorkflow": evaluation.visible_to_workflow}

        _ = self.memory_service.record_review_event(
            memory.memory_id,
            filters={
                "scope": memory.scope.model_dump(mode="json", by_alias=True),
                "subjectRefs": [
                    subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for subject_ref in memory.subject_refs
                ],
                "functionName": evaluator_key or "core.memory_follow_up.run_due",
                "source": "scheduler",
                "actor": evaluator_key or "core.memory_follow_up",
                "channel": "memory_follow_up",
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
