from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.core.formatting import normalize_symbol, to_utc
from app.schemas.memory_report import AgentMemoryReportAnalysis, AgentMemoryResolutionUpdate
from app.schemas.report import ReportRead
from app.services.market_data_service import MarketClosePoint, MarketDataService
from app.services.memory_report_service import MemoryReportService
from app.services.quote_provider import QuoteProviderError

type ReturnResolutionStatus = Literal["pending", "resolved", "expired"]


@dataclass(frozen=True, slots=True)
class ReturnResolutionResult:
    status: ReturnResolutionStatus
    report: ReportRead
    reason: str | None = None


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
        self.memory_report_service: MemoryReportService = MemoryReportService(session)

    def resolve_memory_report(
        self,
        report_id: int,
        *,
        end_date: datetime,
        benchmark_symbol: str | None = None,
    ) -> ReturnResolutionResult:
        report, metadata = self.memory_report_service.get_memory_report_with_metadata(report_id)
        analysis = metadata.analysis
        start_boundary = self._start_boundary(report.created_at)
        requested_end_boundary = self._end_boundary(end_date)
        resolution_end = self._resolution_end_boundary(
            analysis=analysis,
            start_boundary=start_boundary,
            requested_end_boundary=requested_end_boundary,
        )
        if requested_end_boundary < resolution_end:
            return ReturnResolutionResult(
                status="pending",
                report=ReportRead.model_validate(report),
                reason="exit_condition_pending",
            )

        resolution, reason = self._build_resolution(
            analysis=analysis,
            start_boundary=start_boundary,
            end_boundary=resolution_end,
            benchmark_symbol=benchmark_symbol,
        )
        updated_report = self.memory_report_service.resolve_memory_report(report.id, resolution)
        return ReturnResolutionResult(
            status=resolution.resolved_status,
            report=updated_report,
            reason=reason,
        )

    def _build_resolution(
        self,
        *,
        analysis: AgentMemoryReportAnalysis,
        start_boundary: datetime,
        end_boundary: datetime,
        benchmark_symbol: str | None,
    ) -> tuple[AgentMemoryResolutionUpdate, str | None]:
        raw_return = self._resolve_directional_return(
            action=analysis.decision.action,
            symbol=analysis.ticker,
            start_boundary=start_boundary,
            end_boundary=end_boundary,
        )
        if raw_return is None:
            return self._expired_resolution(end_boundary), "symbol_history_unavailable"

        benchmark_return: Decimal | None = None
        normalized_benchmark = self._normalize_benchmark_symbol(benchmark_symbol)
        if normalized_benchmark is not None:
            benchmark_result = self._resolve_price_return(
                normalized_benchmark,
                start_boundary=start_boundary,
                end_boundary=end_boundary,
            )
            if benchmark_result is None:
                return self._expired_resolution(end_boundary), "benchmark_history_unavailable"
            benchmark_return = benchmark_result.value

        benchmark_baseline = benchmark_return if benchmark_return is not None else Decimal("0")
        resolution = AgentMemoryResolutionUpdate(
            resolved_status="resolved",
            resolved_at=self._resolved_at(end_boundary),
            raw_return=raw_return,
            benchmark_return=benchmark_return,
            alpha=raw_return - benchmark_baseline,
        )
        return resolution, None

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
        analysis: AgentMemoryReportAnalysis,
        start_boundary: datetime,
        requested_end_boundary: datetime,
    ) -> datetime:
        if analysis.horizon_days is None:
            return requested_end_boundary
        horizon_end = start_boundary + timedelta(days=analysis.horizon_days)
        return ReturnResolutionService._end_boundary(horizon_end)

    @staticmethod
    def _expired_resolution(end_boundary: datetime) -> AgentMemoryResolutionUpdate:
        return AgentMemoryResolutionUpdate(
            resolved_status="expired",
            resolved_at=ReturnResolutionService._resolved_at(end_boundary),
        )

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
