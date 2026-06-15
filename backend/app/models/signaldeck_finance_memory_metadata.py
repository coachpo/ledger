from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SignalDeckFinanceMemoryMetadata(Base):
    __tablename__: str = "signaldeck_finance_memory_metadata"
    __table_args__: tuple[CheckConstraint, CheckConstraint] = (
        CheckConstraint(
            "action IN ('buy', 'hold', 'sell')",
            name="ck_signaldeck_finance_memory_metadata_action",
        ),
        CheckConstraint(
            "horizon_days IS NULL OR horizon_days > 0",
            name="ck_signaldeck_finance_memory_metadata_horizon_days_positive",
        ),
    )

    memory_id: Mapped[str] = mapped_column(
        String(160),
        ForeignKey("agent_memory_entries.memory_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ticker: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    horizon_days: Mapped[int | None] = mapped_column(nullable=True)
    benchmark_symbol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["SignalDeckFinanceMemoryMetadata"]
