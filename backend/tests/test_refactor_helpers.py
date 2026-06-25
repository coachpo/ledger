from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.core.formatting import format_decimal, format_nullable_decimal, portfolio_cash_total


def test_format_decimal_rounds_half_up_to_requested_places() -> None:
    assert format_decimal(Decimal("1.235"), places=2) == "1.24"
    assert format_decimal(Decimal("15"), places=0) == "15"


def test_format_nullable_decimal_preserves_none() -> None:
    assert format_nullable_decimal(None) is None
    assert format_nullable_decimal(Decimal("12.345"), places=2) == "12.35"


def test_portfolio_cash_total_applies_deposits_and_withdrawals() -> None:
    balances = [
        SimpleNamespace(amount=Decimal("100.00"), operation_type="DEPOSIT"),
        SimpleNamespace(amount=Decimal("25.50"), operation_type="WITHDRAWAL"),
        SimpleNamespace(amount=Decimal("10.00"), operation_type="DEPOSIT"),
    ]

    assert portfolio_cash_total(balances) == Decimal("84.50")
