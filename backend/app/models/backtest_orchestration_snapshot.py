from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.backtest import Backtest


class BacktestOrchestrationSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "backtest_orchestration_snapshots"
    __table_args__ = (
        Index("ix_backtest_orchestration_snapshots_backtest_id", "backtest_id"),
        Index("ix_backtest_orchestration_snapshots_cycle_date", "cycle_date"),
        UniqueConstraint(
            "backtest_id", "cycle_date", name="uq_backtest_orchestration_snapshots_cycle"
        ),
    )

    backtest_id: Mapped[int] = mapped_column(
        ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False
    )
    cycle_date: Mapped[date] = mapped_column(Date, nullable=False)
    prompt_report_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    orchestration_pattern_key: Mapped[str] = mapped_column(String(120), nullable=False)
    pattern_policy_version: Mapped[int] = mapped_column(nullable=False)
    entry_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    full_user_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_mentions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    mentioned_target_outputs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_builtin_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_role_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_character_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    backtest: Mapped[Backtest] = relationship("Backtest")
