from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.trading_operation import TradingOperation


class Balance(IdMixin, TimestampMixin, Base):
    __tablename__ = "balances"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "label", name="uq_balances_portfolio_label"),
        CheckConstraint("amount >= 0", name="ck_balances_amount_non_negative"),
        Index("ix_balances_portfolio_label", "portfolio_id", "label"),
    )

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    operation_type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="balances")
    trading_operations: Mapped[list[TradingOperation]] = relationship(
        "TradingOperation", back_populates="balance"
    )

    @property
    def has_trading_operations(self) -> bool:
        return bool(self.trading_operations)
