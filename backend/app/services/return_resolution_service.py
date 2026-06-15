from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.core.formatting import decimal_to_string, normalize_symbol, to_utc
from app.extensions.signaldeck_finance.service_gate import (
    RETURN_RESOLUTION_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.schemas.memory import MemoryEntryRead, MemoryOutcome
from app.services.market_data_service import MarketClosePoint, MarketDataService
from app.services.memory_service import MemoryService
from app.services.quote_provider import QuoteProviderError


@dataclass(frozen=True, slots=True)
class ReturnResolutionResult:
    visible_to_workflow: bool
    review_recorded: bool
    memory: MemoryEntryRead
    reason: str | None = None
    outcome_summary: str | None = None


@dataclass(frozen=True, slots=True)
class _BoundedReturn:
    value: Decimal
    entry_point: MarketClosePoint
    exit_point: MarketClosePoint


class ReturnResolutionService:
    """Resolve agent-memory outcomes from bounded close history.

    Date boundaries are closed and look-ahead safe: entry is the first close on or
    after the memory start date, and exit is the last close on or before the
    resolution end date. Hold resolves as a neutral cash stance, so raw return is
    zero while any requested benchmark still contributes to alpha.
    """

    def __init__(self, session: Session, market_data_service: MarketDataService) -> None:
        self.session: Session = session
        self.market_data_service: MarketDataService = market_data_service
        self.memory_service: MemoryService = MemoryService(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(
            self.session,
            surface=RETURN_RESOLUTION_SERVICE_SURFACE,
        )

    def resolve_memory(
        self,
        memory_id: str,
        *,
        end_date: datetime,
        symbol: str,
        action: Literal["buy", "hold", "sell"],
        horizon_days: int | None = None,
        benchmark_symbol: str | None = None,
        commit: bool = True,
    ) -> ReturnResolutionResult:
        self._require_enabled()
        memory = self.memory_service.get_memory(memory_id)
        if memory.visible_to_workflow:
            return ReturnResolutionResult(
                visible_to_workflow=True,
                review_recorded=True,
                memory=memory,
                reason="already_visible",
            )

        start_boundary = self._start_boundary(memory.created_at)
        requested_end_boundary = self._end_boundary(end_date)
        resolution_end = self._resolution_end_boundary(
            horizon_days=horizon_days,
            start_boundary=start_boundary,
            requested_end_boundary=requested_end_boundary,
        )
        if requested_end_boundary < resolution_end:
            return ReturnResolutionResult(
                visible_to_workflow=False,
                review_recorded=False,
                memory=memory,
                reason="exit_condition_unmet",
            )

        outcome, visible_to_workflow, reason = self._build_resolution(
            symbol=symbol,
            action=action,
            start_boundary=start_boundary,
            end_boundary=resolution_end,
            benchmark_symbol=benchmark_symbol,
        )
        if visible_to_workflow:
            updated_memory = self.memory_service.resolve_memory(
                memory_id,
                outcome,
                commit=commit,
            )
        else:
            updated_memory = self.memory_service.record_review_event(
                memory_id,
                filters={
                    "scope": memory.scope.model_dump(mode="json", by_alias=True),
                    "subjectRefs": [
                        subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for subject_ref in memory.subject_refs
                    ],
                    "functionName": "signaldeck.finance.return_resolution.resolve_memory",
                    "source": "scheduler",
                    "actor": "signaldeck.finance.return_resolution",
                    "channel": "memory_follow_up",
                },
                result_snapshot={
                    "memoryId": memory.memory_id,
                    "revisionId": memory.revision_id,
                    "reviewAction": "resolved",
                    "outcomeSummary": outcome.summary,
                },
                status_snapshot={"visibleToWorkflow": False},
                commit=commit,
            )
        return ReturnResolutionResult(
            visible_to_workflow=visible_to_workflow,
            review_recorded=True,
            memory=updated_memory,
            reason=reason,
            outcome_summary=outcome.summary,
        )

    def _build_resolution(
        self,
        *,
        symbol: str,
        action: Literal["buy", "hold", "sell"],
        start_boundary: datetime,
        end_boundary: datetime,
        benchmark_symbol: str | None,
    ) -> tuple[MemoryOutcome, bool, str | None]:
        raw_return = self._resolve_directional_return(
            action=action,
            symbol=symbol,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
        )
        if raw_return is None:
            return self._hidden_resolution(end_boundary), False, "symbol_history_unavailable"

        benchmark_return: Decimal | None = None
        normalized_benchmark = self._normalize_benchmark_symbol(benchmark_symbol)
        if normalized_benchmark is not None:
            benchmark_result = self._resolve_price_return(
                normalized_benchmark,
                start_boundary=start_boundary,
                end_boundary=end_boundary,
            )
            if benchmark_result is None:
                return (
                    self._hidden_resolution(end_boundary),
                    False,
                    "benchmark_history_unavailable",
                )
            benchmark_return = benchmark_result.value

        benchmark_baseline = benchmark_return if benchmark_return is not None else Decimal("0")
        outcome = MemoryOutcome(
            summary=self._resolved_summary(
                raw_return=raw_return,
                alpha=raw_return - benchmark_baseline,
                benchmark_return=benchmark_return,
            ),
            observed_at=self._resolved_at(end_boundary),
        )
        return outcome, True, None

    def _resolve_directional_return(
        self,
        *,
        action: Literal["buy", "hold", "sell"],
        symbol: str,
        start_boundary: datetime,
        end_boundary: datetime,
    ) -> Decimal | None:
        if action == "hold":
            return Decimal("0")

        price_return = self._resolve_price_return(
            symbol,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
        )
        if price_return is None:
            return None
        if action == "buy":
            return price_return.value
        return -price_return.value

    def _resolve_price_return(
        self,
        symbol: str,
        *,
        start_boundary: datetime,
        end_boundary: datetime,
    ) -> _BoundedReturn | None:
        try:
            points = self.market_data_service.get_close_history_snapshot(
                symbol,
                start_date=start_boundary,
                end_date=end_boundary,
            )
        except QuoteProviderError:
            return None

        boundaries = self._select_boundary_points(
            points,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
        )
        if boundaries is None:
            return None

        entry_point, exit_point = boundaries
        if entry_point.close == Decimal("0"):
            return None
        return _BoundedReturn(
            value=(exit_point.close - entry_point.close) / entry_point.close,
            entry_point=entry_point,
            exit_point=exit_point,
        )

    @staticmethod
    def _select_boundary_points(
        points: list[MarketClosePoint],
        *,
        start_boundary: datetime,
        end_boundary: datetime,
    ) -> tuple[MarketClosePoint, MarketClosePoint] | None:
        ordered_points = sorted(points, key=lambda point: point.at)
        entry_point = next(
            (point for point in ordered_points if point.at >= start_boundary),
            None,
        )
        exit_point = next(
            (point for point in reversed(ordered_points) if point.at <= end_boundary),
            None,
        )
        if entry_point is None or exit_point is None:
            return None
        if entry_point.at > exit_point.at:
            return None
        return entry_point, exit_point

    @staticmethod
    def _resolution_end_boundary(
        *,
        horizon_days: int | None,
        start_boundary: datetime,
        requested_end_boundary: datetime,
    ) -> datetime:
        if horizon_days is None:
            return requested_end_boundary
        horizon_end = start_boundary + timedelta(days=horizon_days)
        return ReturnResolutionService._end_boundary(horizon_end)

    @staticmethod
    def _hidden_resolution(end_boundary: datetime) -> MemoryOutcome:
        return MemoryOutcome(
            summary="Finance return kept hidden.",
            observed_at=ReturnResolutionService._resolved_at(end_boundary),
        )

    @staticmethod
    def _resolved_summary(
        *,
        raw_return: Decimal,
        alpha: Decimal,
        benchmark_return: Decimal | None,
    ) -> str:
        parts = [
            f"Finance return resolved: raw return {decimal_to_string(raw_return)}",
            f"alpha {decimal_to_string(alpha)}",
        ]
        if benchmark_return is not None:
            parts.append(f"benchmark return {decimal_to_string(benchmark_return)}")
        return ", ".join(parts) + "."

    @staticmethod
    def _normalize_benchmark_symbol(symbol: str | None) -> str | None:
        if symbol is None:
            return None
        normalized_symbol = normalize_symbol(symbol)
        return normalized_symbol or None

    @staticmethod
    def _start_boundary(value: datetime) -> datetime:
        normalized = to_utc(value)
        return datetime.combine(normalized.date(), time.min, tzinfo=UTC)

    @staticmethod
    def _end_boundary(value: datetime) -> datetime:
        normalized = to_utc(value)
        return datetime.combine(normalized.date(), time.max, tzinfo=UTC)

    @staticmethod
    def _resolved_at(end_boundary: datetime) -> datetime:
        return datetime.combine(to_utc(end_boundary).date(), time.min, tzinfo=UTC)


__all__ = ["ReturnResolutionResult", "ReturnResolutionService"]
