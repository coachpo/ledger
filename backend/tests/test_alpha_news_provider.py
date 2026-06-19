from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.services.news_provider import (
    AlphaVantageNewsProvider,
    NewsProviderMalformedResponseError,
    NewsProviderMissingKeyError,
    NewsProviderRateLimitError,
    NewsProviderTimeoutError,
    NewsProviderUnsupportedQueryError,
)

_FAKE_API_KEY = "".join(("alpha", "-", "test", "-", "key"))


class _FakeAlphaClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, str | int]] = []

    def fetch_news(self, *, params: dict[str, str | int]) -> object:
        self.calls.append(dict(params))
        return self.payload


class _TimeoutAlphaClient:
    def fetch_news(self, *, params: dict[str, str | int]) -> object:
        del params
        raise httpx.TimeoutException(f"timed out with apikey={_FAKE_API_KEY}")


def _payload(*, label: str = "Bullish") -> dict[str, object]:
    return {
        "feed": [
            {
                "title": "Nvidia expands AI platform",
                "source": "Alpha Wire",
                "url": "https://example.com/nvda-ai",
                "summary": "Chipmaker updates its AI stack.",
                "time_published": "20250508T143000",
                "overall_sentiment_label": label,
                "ticker_sentiment": [
                    {"ticker": "NVDA", "ticker_sentiment_label": "Bullish"},
                    {"ticker": " MSFT "},
                    {"ticker": ""},
                ],
            }
        ]
    }


def test_alpha_news_provider_parses_symbol_feed_and_params() -> None:
    client = _FakeAlphaClient(_payload())
    provider = AlphaVantageNewsProvider(api_key=_FAKE_API_KEY, client=client, timeout=2.5)

    result = provider.fetch_news(
        symbols=[" nvda ", "MSFT", "nvda"],
        query=None,
        scope="symbol",
        start_date=datetime(2025, 5, 1, tzinfo=UTC),
        end_date=datetime(2025, 5, 9, 12, 30, tzinfo=UTC),
        limit=5,
    )

    assert result.provider == "alpha_vantage"
    assert client.calls == [
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": _FAKE_API_KEY,
            "limit": 5,
            "tickers": "NVDA,MSFT",
            "time_from": "20250501T0000",
            "time_to": "20250509T1230",
        }
    ]
    assert len(result.items) == 1
    assert result.items[0].title == "Nvidia expands AI platform"
    assert result.items[0].source == "Alpha Wire"
    assert result.items[0].url == "https://example.com/nvda-ai"
    assert result.items[0].summary == "Chipmaker updates its AI stack."
    assert result.items[0].published_at == datetime(2025, 5, 8, 14, 30, tzinfo=UTC)
    assert result.items[0].symbols == ["NVDA", "MSFT"]
    assert result.items[0].sentiment == "positive"


def test_alpha_global_and_market_scopes_use_default_topics_without_symbols() -> None:
    client = _FakeAlphaClient(_payload(label="Neutral"))
    provider = AlphaVantageNewsProvider(api_key=_FAKE_API_KEY, client=client)

    provider.fetch_news(
        symbols=[], query=None, scope="global", start_date=None, end_date=None, limit=3
    )
    provider.fetch_news(
        symbols=[], query=None, scope="market", start_date=None, end_date=None, limit=4
    )
    provider.fetch_news(
        symbols=["aapl"], query=None, scope="market", start_date=None, end_date=None, limit=5
    )

    assert client.calls == [
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": _FAKE_API_KEY,
            "limit": 3,
            "topics": "financial_markets,economy_macro,economy_monetary",
        },
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": _FAKE_API_KEY,
            "limit": 4,
            "topics": "financial_markets,economy_macro,economy_monetary",
        },
        {
            "function": "NEWS_SENTIMENT",
            "source": "signaldeck",
            "apikey": _FAKE_API_KEY,
            "limit": 5,
            "tickers": "AAPL",
        },
    ]


@pytest.mark.parametrize(
    ("provider_label", "expected"),
    [
        ("Positive", "positive"),
        ("Somewhat-Bullish", "positive"),
        ("Negative", "negative"),
        ("Bearish", "negative"),
        ("Neutral", "neutral"),
        ("Mixed", "mixed"),
        ("Unclear", "mixed"),
    ],
)
def test_alpha_sentiment_labels_map_to_provider_sentiment(
    provider_label: str,
    expected: str,
) -> None:
    provider = AlphaVantageNewsProvider(
        api_key=_FAKE_API_KEY,
        client=_FakeAlphaClient(_payload(label=provider_label)),
    )

    result = provider.fetch_news(
        symbols=["nvda"], query=None, scope="symbol", start_date=None, end_date=None, limit=1
    )

    assert result.items[0].sentiment == expected


def test_alpha_unsupported_query_without_symbols_raises_degradable_error() -> None:
    client = _FakeAlphaClient(_payload())
    provider = AlphaVantageNewsProvider(api_key=_FAKE_API_KEY, client=client)

    with pytest.raises(NewsProviderUnsupportedQueryError) as exc_info:
        provider.fetch_news(
            symbols=[],
            query="Federal Reserve meeting",
            scope="market",
            start_date=None,
            end_date=None,
            limit=5,
        )

    assert exc_info.value.code == "provider_unsupported_query"
    assert client.calls == []


def test_alpha_missing_key_raises_without_secret_name() -> None:
    provider = AlphaVantageNewsProvider(api_key=None, client=_FakeAlphaClient(_payload()))

    with pytest.raises(NewsProviderMissingKeyError) as exc_info:
        provider.fetch_news(
            symbols=["nvda"], query=None, scope="symbol", start_date=None, end_date=None, limit=5
        )

    assert "FINANCE_ALPHA_VANTAGE_API_KEY" not in str(exc_info.value)
    assert exc_info.value.details == {"provider": "alpha_vantage"}


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        (
            {"Note": f"Thank you for using Alpha Vantage. api_key={_FAKE_API_KEY}"},
            NewsProviderRateLimitError,
        ),
        ({"Information": f"Invalid API key. {_FAKE_API_KEY}"}, NewsProviderMissingKeyError),
        ({"feed": "not-a-list"}, NewsProviderMalformedResponseError),
        ([{"feed": []}], NewsProviderMalformedResponseError),
    ],
)
def test_alpha_failure_payloads_raise_structured_redacted_errors(
    payload: object,
    error_type: type[Exception],
) -> None:
    provider = AlphaVantageNewsProvider(api_key=_FAKE_API_KEY, client=_FakeAlphaClient(payload))

    with pytest.raises(error_type) as exc_info:
        provider.fetch_news(
            symbols=["nvda"], query=None, scope="symbol", start_date=None, end_date=None, limit=5
        )

    assert _FAKE_API_KEY not in str(exc_info.value)


def test_alpha_timeout_raises_redacted_timeout_error() -> None:
    provider = AlphaVantageNewsProvider(api_key=_FAKE_API_KEY, client=_TimeoutAlphaClient())

    with pytest.raises(NewsProviderTimeoutError) as exc_info:
        provider.fetch_news(
            symbols=["nvda"], query=None, scope="symbol", start_date=None, end_date=None, limit=5
        )

    assert exc_info.value.code == "provider_timeout"
    assert _FAKE_API_KEY not in str(exc_info.value)
