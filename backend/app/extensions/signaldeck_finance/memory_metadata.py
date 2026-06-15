from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy.orm import Session

from app.models.signaldeck_finance_memory_metadata import SignalDeckFinanceMemoryMetadata

type FinanceMemoryAction = Literal["buy", "hold", "sell"]


@dataclass(frozen=True, slots=True)
class FinanceMemoryMetadata:
    ticker: str
    action: FinanceMemoryAction
    rationale: str | None = None
    risk_summary: str | None = None
    execution_plan: str | None = None
    horizon_days: int | None = None
    benchmark_symbol: str | None = None
    decision_summary: str | None = None


def write_finance_memory_metadata(
    session: Session,
    memory_id: str,
    metadata: FinanceMemoryMetadata,
) -> None:
    _ = session.merge(
        SignalDeckFinanceMemoryMetadata(
            memory_id=memory_id,
            ticker=metadata.ticker,
            action=metadata.action,
            rationale=metadata.rationale,
            risk_summary=metadata.risk_summary,
            execution_plan=metadata.execution_plan,
            horizon_days=metadata.horizon_days,
            benchmark_symbol=metadata.benchmark_symbol,
            decision_summary=metadata.decision_summary,
        )
    )
    session.flush()


def read_finance_memory_metadata(session: Session, memory_id: str) -> FinanceMemoryMetadata | None:
    row = session.get(SignalDeckFinanceMemoryMetadata, memory_id)
    if row is None:
        return None
    return FinanceMemoryMetadata(
        ticker=row.ticker,
        action=cast(FinanceMemoryAction, row.action),
        rationale=row.rationale,
        risk_summary=row.risk_summary,
        execution_plan=row.execution_plan,
        horizon_days=row.horizon_days,
        benchmark_symbol=row.benchmark_symbol,
        decision_summary=row.decision_summary,
    )


__all__ = [
    "FinanceMemoryAction",
    "FinanceMemoryMetadata",
    "read_finance_memory_metadata",
    "write_finance_memory_metadata",
]
