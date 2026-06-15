from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.execution_dependencies import resolve_finance_quote_provider
from app.extensions.signaldeck_finance.memory_metadata import read_finance_memory_metadata
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.schemas.memory import MemoryEntryRead
from app.services.market_data_service import MarketDataService
from app.services.memory_follow_up_service import MemoryFollowUpEvaluation, MemoryFollowUpEvaluator
from app.services.reflection_service import ReflectionService
from app.services.return_resolution_service import ReturnResolutionService
from app.services.run_lifecycle import ExtensionRunLifecycleHooks, WorkflowPackageStartContext

_FINANCE_EVALUATOR_KEY = "signaldeck.finance.return_resolution"
_FINANCE_MEMORY_KINDS = frozenset({"memory", "research.note"})


class FinanceMemoryFollowUpEvaluator:
    evaluator_key: str = _FINANCE_EVALUATOR_KEY
    memory_kinds: frozenset[str] = _FINANCE_MEMORY_KINDS

    def __init__(self, session: Session, market_data_service: MarketDataService) -> None:
        self.session: Session = session
        self.return_resolution_service: ReturnResolutionService = ReturnResolutionService(
            session,
            market_data_service,
        )
        self.reflection_service: ReflectionService = ReflectionService(session)

    def evaluate(
        self,
        memory: MemoryEntryRead,
        *,
        reviewed_at: datetime,
    ) -> MemoryFollowUpEvaluation:
        metadata = read_finance_memory_metadata(self.session, memory.memory_id)
        if metadata is None:
            return MemoryFollowUpEvaluation(
                visible_to_workflow=False,
                reason="finance_metadata_missing",
                outcome_summary="finance_metadata_missing",
            )
        resolution = self.return_resolution_service.resolve_memory(
            memory.memory_id,
            end_date=reviewed_at,
            symbol=metadata.ticker,
            action=metadata.action,
            horizon_days=metadata.horizon_days,
            benchmark_symbol=metadata.benchmark_symbol,
            commit=False,
        )
        reflected = False
        reflection_summary: str | None = None
        if resolution.review_recorded:
            reflected_memory = self.reflection_service.generate_and_append_reflection(
                memory.memory_id,
                ticker=metadata.ticker,
                action=metadata.action,
                decision_summary=metadata.decision_summary or metadata.rationale,
                reflected_at=reviewed_at,
                commit=False,
            )
            reflected = True
            reflection_summary = reflected_memory.summary
        return MemoryFollowUpEvaluation(
            visible_to_workflow=resolution.visible_to_workflow,
            reason=resolution.reason,
            reflected=reflected,
            event_recorded=resolution.review_recorded,
            outcome_summary=resolution.outcome_summary,
            reflection_summary=reflection_summary,
            reflection_source="signaldeck.finance.return_resolution",
        )


def _memory_follow_up_evaluators(
    context: WorkflowPackageStartContext,
) -> tuple[MemoryFollowUpEvaluator, ...]:
    quote_provider = resolve_finance_quote_provider(context.provider_bundle)
    if quote_provider is None:
        return ()
    return (
        FinanceMemoryFollowUpEvaluator(
            context.session,
            MarketDataService(session=context.session, quote_provider=quote_provider),
        ),
    )


def register_run_lifecycle_hooks() -> tuple[ExtensionRunLifecycleHooks, ...]:
    return (
        ExtensionRunLifecycleHooks(
            extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
            memory_follow_up_evaluators=_memory_follow_up_evaluators,
        ),
    )


__all__ = ["FinanceMemoryFollowUpEvaluator", "register_run_lifecycle_hooks"]
