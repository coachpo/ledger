from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin

if TYPE_CHECKING:
    from app.models.balance import Balance
    from app.models.portfolio import Portfolio


class TradingOperation(IdMixin, Base):
    __tablename__ = "trading_operations"
    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY', 'SELL', 'DIVIDEND', 'SPLIT')",
            name="ck_trading_operations_side",
        ),
        CheckConstraint("quantity > 0", name="ck_trading_operations_quantity_positive"),
        CheckConstraint("price >= 0", name="ck_trading_operations_price_non_negative"),
        CheckConstraint("commission >= 0", name="ck_trading_operations_commission_non_negative"),
        Index("ix_trading_operations_portfolio_executed_at", "portfolio_id", "executed_at"),
        Index("ix_trading_operations_portfolio_symbol", "portfolio_id", "symbol"),
    )

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    balance_id: Mapped[int | None] = mapped_column(
        ForeignKey("balances.id", ondelete="SET NULL"), nullable=True
    )
    balance_label: Mapped[str] = mapped_column(String(60), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    commission: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    dividend_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    split_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="trading_operations")
    balance: Mapped[Balance | None] = relationship("Balance", back_populates="trading_operations")
