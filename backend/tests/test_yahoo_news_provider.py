from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.news_provider import NewsProviderMalformedResponseError, YahooFinanceNewsProvider


class _FakeYahooSearchClient:
    def __init__(self, payloads: dict[str, list[dict[str, object]]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, int]] = []

    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        self.calls.append((query, limit))
        return self.payloads.get(query, [])


class _MalformedYahooSearchClient:
    def search_news(self, *, query: str, limit: int) -> list[dict[str, object]]:
        del query, limit
        raise NewsProviderMalformedResponseError("Yahoo Finance news payload was malformed")


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def test_yahoo_news_provider_parses_nested_content_articles() -> None:
    client = _FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "content": {
                        "title": "Nvidia expands AI platform",
                        "summary": "Chipmaker updates its AI stack.",
                        "provider": {"displayName": "Yahoo Finance"},
                        "canonicalUrl": {"url": "https://finance.yahoo.com/nvda-ai"},
                        "pubDate": "2025-05-08T14:30:00Z",
                    }
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)

    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=5,
    )

    assert result.provider == "yahoo"
    assert client.calls == [("NVDA", 5)]
    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia expands AI platform"
    assert result.items[0].summary == "Chipmaker updates its AI stack."
    assert result.items[0].source == "Yahoo Finance"
    assert result.items[0].url == "https://finance.yahoo.com/nvda-ai"
    assert result.items[0].published_at == datetime(2025, 5, 8, 14, 30, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA"]


def test_yahoo_news_provider_parses_flat_provider_publish_time_articles() -> None:
    client = _FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Nvidia flat article",
                    "summary": "Flat payload summary.",
                    "publisher": "Reuters",
                    "link": "https://example.com/nvda-flat",
                    "providerPublishTime": _epoch(2025, 5, 6),
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)

    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=5,
    )

    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia flat article"
    assert result.items[0].source == "Reuters"
    assert result.items[0].url == "https://example.com/nvda-flat"
    assert result.items[0].published_at == datetime(2025, 5, 6, tzinfo=UTC)


def test_yahoo_global_news_defaults_dedupe_by_url_then_normalized_title() -> None:
    client = _FakeYahooSearchClient(
        {
            "markets": [
                {
                    "title": "Markets rally",
                    "publisher": "Wire",
                    "link": "https://example.com/markets-rally",
                    "providerPublishTime": _epoch(2025, 5, 7),
                },
                {
                    "title": "Different title",
                    "publisher": "Wire",
                    "link": "https://example.com/markets-rally",
                    "providerPublishTime": _epoch(2025, 5, 7),
                },
            ],
            "macro": [
                {
                    "title": "  markets   rally ",
                    "publisher": "Wire",
                    "link": "https://example.com/duplicate-title",
                    "providerPublishTime": _epoch(2025, 5, 6),
                },
                {
                    "title": "Central bank holds rates",
                    "publisher": "Wire",
                    "link": "https://example.com/rates",
                    "providerPublishTime": _epoch(2025, 5, 6),
                },
            ],
        }
    )
    provider = YahooFinanceNewsProvider(
        search_client=client,
        global_queries=("markets", "macro"),
        global_lookback_days=7,
    )

    result = provider.fetch_news(
        symbols=[],
        query=None,
        scope="global",
        start_date=None,
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=10,
    )

    assert client.calls == [("markets", 10), ("macro", 10)]
    assert [item.title for item in result.items] == [
        "Markets rally",
        "Central bank holds rates",
    ]


def test_yahoo_news_provider_excludes_future_and_undated_historical_articles() -> None:
    client = _FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Future event",
                    "publisher": "Wire",
                    "link": "https://example.com/future",
                    "providerPublishTime": _epoch(2025, 6, 1),
                },
                {
                    "title": "Undated historical leak",
                    "publisher": "Wire",
                    "link": "https://example.com/undated",
                },
                {
                    "title": "Past event",
                    "publisher": "Wire",
                    "link": "https://example.com/past",
                    "providerPublishTime": _epoch(2025, 5, 5),
                },
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)

    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, tzinfo=UTC),
        limit=10,
    )

    assert [item.title for item in result.items] == ["Past event"]


def test_yahoo_news_provider_keeps_undated_article_when_window_reaches_today() -> None:
    client = _FakeYahooSearchClient(
        {
            "NVDA": [
                {
                    "title": "Live undated article",
                    "publisher": "Wire",
                    "link": "https://example.com/live-undated",
                }
            ]
        }
    )
    provider = YahooFinanceNewsProvider(search_client=client)
    today = datetime.now(UTC)

    result = provider.fetch_news(
        symbols=["nvda"],
        query=None,
        scope="symbol",
        start_date=today - timedelta(days=1),
        end_date=today,
        limit=10,
    )

    assert [item.title for item in result.items] == ["Live undated article"]
    assert result.items[0].published_at == today


def test_yahoo_news_provider_malformed_payload_uses_typed_error() -> None:
    provider = YahooFinanceNewsProvider(search_client=_MalformedYahooSearchClient())

    with pytest.raises(NewsProviderMalformedResponseError, match="Yahoo Finance news payload"):
        provider.fetch_news(
            symbols=["nvda"],
            query=None,
            scope="symbol",
            start_date=datetime(2025, 5, 1, tzinfo=UTC),
            end_date=datetime(2025, 5, 9, tzinfo=UTC),
            limit=5,
        )
