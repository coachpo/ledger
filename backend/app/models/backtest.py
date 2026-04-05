from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio


class Backtest(IdMixin, TimestampMixin, Base):
    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtests_portfolio_id", "portfolio_id"),
        Index("ix_backtests_status", "status"),
    )

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    deposit_balance_id: Mapped[int] = mapped_column(
        ForeignKey("balances.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_cycle_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cycles: Mapped[int] = mapped_column(nullable=False, server_default="0")
    completed_cycles: Mapped[int] = mapped_column(nullable=False, server_default="0")
    template_id: Mapped[int] = mapped_column(
        ForeignKey("text_templates.id", ondelete="RESTRICT"), nullable=False
    )
    webhook_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    webhook_timeout: Mapped[int] = mapped_column(nullable=False, server_default="600")
    current_cycle_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    price_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    commission_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    commission_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default="0"
    )
    benchmark_symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    recent_activity: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="backtests")

    @property
    def portfolio_name(self) -> str | None:
        return self.portfolio.name if self.portfolio is not None else None
