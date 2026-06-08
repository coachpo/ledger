from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_memory import AgentMemoryEntry, AgentMemoryRevision
from app.schemas.memory import JsonScalar, MemoryAttributes

FINANCE_MEMORY_ATTRIBUTES_KEY: Final = "_signaldeckFinance"

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


def finance_memory_attributes_payload(metadata: FinanceMemoryMetadata) -> MemoryAttributes:
    payload: dict[str, JsonScalar] = {
        "ticker": metadata.ticker,
        "action": metadata.action,
    }
    for key, value in (
        ("rationale", metadata.rationale),
        ("riskSummary", metadata.risk_summary),
        ("executionPlan", metadata.execution_plan),
        ("benchmarkSymbol", metadata.benchmark_symbol),
        ("decisionSummary", metadata.decision_summary),
    ):
        if value not in (None, ""):
            payload[key] = value
    if metadata.horizon_days is not None:
        payload["horizonDays"] = metadata.horizon_days
    return {FINANCE_MEMORY_ATTRIBUTES_KEY: payload}


def read_finance_memory_metadata(session: Session, memory_id: str) -> FinanceMemoryMetadata | None:
    latest_version = (
        select(
            AgentMemoryRevision.memory_entry_id,
            AgentMemoryRevision.attributes,
        )
        .join(AgentMemoryEntry, AgentMemoryEntry.id == AgentMemoryRevision.memory_entry_id)
        .where(AgentMemoryEntry.memory_id == memory_id)
        .order_by(AgentMemoryRevision.version.desc(), AgentMemoryRevision.id.desc())
        .limit(1)
    )
    row = session.execute(latest_version).one_or_none()
    if row is None:
        return None
    attributes = cast(object, row[1])
    if not isinstance(attributes, dict):
        return None
    typed_attributes = cast(dict[object, object], attributes)
    raw_metadata = typed_attributes.get(FINANCE_MEMORY_ATTRIBUTES_KEY)
    if not isinstance(raw_metadata, dict):
        return None
    return _metadata_from_payload(cast(dict[object, object], raw_metadata))


def _metadata_from_payload(payload: dict[object, object]) -> FinanceMemoryMetadata | None:
    ticker = _optional_text(payload.get("ticker"))
    if ticker is None:
        return None
    action = _optional_text(payload.get("action")) or "hold"
    if action not in {"buy", "hold", "sell"}:
        return None
    return FinanceMemoryMetadata(
        ticker=ticker,
        action=cast(FinanceMemoryAction, action),
        rationale=_optional_text(payload.get("rationale")),
        risk_summary=_optional_text(payload.get("riskSummary")),
        execution_plan=_optional_text(payload.get("executionPlan")),
        horizon_days=_optional_int(payload.get("horizonDays")),
        benchmark_symbol=_optional_text(payload.get("benchmarkSymbol")),
        decision_summary=_optional_text(payload.get("decisionSummary")),
    )


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


__all__ = [
    "FINANCE_MEMORY_ATTRIBUTES_KEY",
    "FinanceMemoryAction",
    "FinanceMemoryMetadata",
    "finance_memory_attributes_payload",
    "read_finance_memory_metadata",
]
