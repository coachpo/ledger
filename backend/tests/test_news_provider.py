from __future__ import annotations

from datetime import UTC, datetime

from app.services.news_provider import DeterministicNewsProvider
from app.services.quote_provider import QuoteProvider


def test_deterministic_news_provider_preserves_existing_shape() -> None:
    provider = DeterministicNewsProvider()

    result = provider.fetch_news(
        symbols=[" nvda ", "NVDA"],
        query=" earnings ",
        scope="symbol",
        start_date=datetime(2024, 3, 1, tzinfo=UTC),
        end_date=datetime(2024, 4, 1, tzinfo=UTC),
        limit=5,
    )

    assert result.provider == "deterministic_test"
    assert len(result.items) == 1
    assert result.items[0].title == "NVDA deterministic market update"
    assert result.items[0].source == "deterministic_test"
    assert result.items[0].published_at == datetime(2024, 3, 29, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA"]
    assert result.items[0].sentiment == "neutral"


def test_quote_provider_protocol_has_no_news_method() -> None:
    assert "fetch_news" not in QuoteProvider.__dict__
