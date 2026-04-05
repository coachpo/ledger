from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.core.formatting import format_decimal, format_nullable_decimal, portfolio_cash_total
from app.db.upgrades import build_unique_legacy_portfolio_slug, normalize_legacy_portfolio_slug


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


def test_normalize_legacy_portfolio_slug_rewrites_invalid_values() -> None:
    assert (
        normalize_legacy_portfolio_slug("  123 Growth & Income!! ") == "portfolio_123_growth_income"
    )
    assert normalize_legacy_portfolio_slug("***") == "portfolio"


def test_build_unique_legacy_portfolio_slug_trims_and_appends_suffixes() -> None:
    used_slugs = {"growth"}

    assert build_unique_legacy_portfolio_slug("growth", used_slugs) == "growth_2"
    assert build_unique_legacy_portfolio_slug("x" * 100, set()) == "x" * 100
    assert len(build_unique_legacy_portfolio_slug("y" * 100, {"y" * 100})) == 100
