from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import RuntimeToolContext, RuntimeToolRegistry
from app.extensions.registry import INSTALLED_EXTENSIONS
from app.extensions.signaldeck_finance.execution_dependencies import (
    finance_execution_provider_bundle_from_parts,
)
from app.extensions.signaldeck_finance.provider_factories import create_social_sentiment_adapters
from app.extensions.signaldeck_finance.runtime_market_data import (
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
)
from app.extensions.signaldeck_finance.runtime_types import (
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeSocialSentimentLookupResult,
)
from app.services.social_sentiment_provider import (
    ProviderSocialSentimentMetric,
    ProviderSocialSentimentSourceBlock,
    ProviderSocialSentimentSourceResult,
    ProviderSocialSentimentWarning,
    RedditSocialSentimentAdapter,
    SocialSentimentProviderError,
    SocialSentimentProviderRateLimitError,
    SocialSentimentProviderTimeoutError,
    SocialSentimentSource,
    StockTwitsSocialSentimentAdapter,
    _RedditRequestConfig,
    _RedditTransport,
    _StockTwitsTransport,
)
from app.services.social_sentiment_service import SocialSentimentService
from app.services.social_sentiment_snapshots import SocialSentimentLookupResult


class _SocialAdapter:
    def __init__(
        self,
        *,
        source: SocialSentimentSource,
        provider_name: str,
        blocks: list[ProviderSocialSentimentSourceBlock] | None = None,
        metrics: list[ProviderSocialSentimentMetric] | None = None,
        warnings: list[ProviderSocialSentimentWarning] | None = None,
        failure: SocialSentimentProviderError | None = None,
    ) -> None:
        self.source: SocialSentimentSource = source
        self.provider_name: str = provider_name
        self.blocks: list[ProviderSocialSentimentSourceBlock] = list(blocks or [])
        self.metrics: list[ProviderSocialSentimentMetric] = list(metrics or [])
        self.warnings: list[ProviderSocialSentimentWarning] = list(warnings or [])
        self.failure: SocialSentimentProviderError | None = failure
        self.calls: list[tuple[str, datetime | None, datetime | None, int]] = []

    def fetch_source_blocks(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderSocialSentimentSourceResult:
        self.calls.append((symbol, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderSocialSentimentSourceResult(
            source=self.source,
            provider=self.provider_name,
            source_blocks=self.blocks[:limit],
            metrics=self.metrics,
            warnings=self.warnings,
        )


class _FakeJsonFetcher:
    def __init__(self, payloads: list[dict[str, object]] | None = None) -> None:
        self.payloads: list[dict[str, object]] = list(payloads or [])
        self.calls: list[tuple[str, dict[str, str | int]]] = []
        self.failures: list[SocialSentimentProviderError] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> dict[str, object]:
        self.calls.append((url, params))
        if self.failures:
            raise self.failures.pop(0)
        return self.payloads.pop(0)


class _FakeTextFetcher:
    def __init__(self, payloads: list[str] | None = None) -> None:
        self.payloads: list[str] = list(payloads or [])
        self.calls: list[tuple[str, dict[str, str | int]]] = []
        self.failures: list[SocialSentimentProviderError] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        timeout: float,
        provider: str,
        source: SocialSentimentSource,
    ) -> str:
        self.calls.append((url, params))
        if self.failures:
            raise self.failures.pop(0)
        return self.payloads.pop(0)


class _SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, delay_seconds: float) -> None:
        self.calls.append(delay_seconds)


def _reddit_config(
    *,
    subreddits: tuple[str, ...] = ("stocks",),
    retry_after_max_seconds: float = 2.0,
) -> _RedditRequestConfig:
    return _RedditRequestConfig(
        subreddits=subreddits,
        retry_after_max_seconds=retry_after_max_seconds,
    )


def _failing_session_factory() -> object:
    raise AssertionError("social sentiment lookup should not open a database session")


def _payload(
    result: RuntimeSocialSentimentLookupResult | SocialSentimentLookupResult,
) -> dict[str, object]:
    return cast(dict[str, object], result.model_dump(mode="json", by_alias=True))


def _reddit_rss_fixture() -> str:
    return """
    <rss version="2.0">
      <channel>
        <item>
          <title>NVDA retail thread</title>
          <description>Discussion volume increased.</description>
          <link>https://www.reddit.com/r/stocks/comments/1/nvda</link>
          <pubDate>Fri, 02 Jan 2026 10:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """


def _reddit_atom_fixture() -> str:
    return """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>NVDA Atom thread</title>
        <content type="html">
          &lt;div&gt;&lt;p&gt;Retail &lt;b&gt;interest&lt;/b&gt; rose for NVDA.&lt;/p&gt;
          &lt;/div&gt;
        </content>
        <link href="https://www.reddit.com/r/stocks/comments/3/nvda_atom/" />
        <published>2026-01-02T10:30:00+00:00</published>
      </entry>
    </feed>
    """


def _reddit_empty_atom_fixture() -> str:
    return '<feed xmlns="http://www.w3.org/2005/Atom"><title>empty</title></feed>'


def _reddit_json_fixture() -> dict[str, object]:
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "NVDA JSON thread",
                        "selftext": "JSON fallback discussion.",
                        "permalink": "/r/stocks/comments/2/nvda_json/",
                        "created_utc": 1767351600,
                        "score": 42,
                        "num_comments": 7,
                    }
                }
            ]
        }
    }


def _stocktwits_json_fixture() -> dict[str, object]:
    return {
        "messages": [
            {
                "id": 123,
                "body": "Bullish into earnings.",
                "created_at": "2026-01-02T12:00:00Z",
                "user": {"username": "trader"},
                "entities": {"sentiment": {"basic": "Bullish"}},
            }
        ]
    }


def _stocktwits_message(
    *,
    message_id: int,
    body: str,
    created_at: str,
    sentiment: str | None,
) -> dict[str, object]:
    entities: dict[str, object] = {}
    if sentiment is not None:
        entities = {"sentiment": {"basic": sentiment}}
    return {
        "id": message_id,
        "body": body,
        "created_at": created_at,
        "user": {"username": "trader"},
        "entities": entities,
    }


def test_reddit_adapter_parses_rss_items_before_json_fetch() -> None:
    text_fetcher = _FakeTextFetcher([_reddit_rss_fixture()])
    json_fetcher = _FakeJsonFetcher([_reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks(
        " nvda ",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 3, tzinfo=UTC),
        limit=5,
    )

    assert json_fetcher.calls == []
    assert len(text_fetcher.calls) == 1
    assert text_fetcher.calls[0][0].endswith("/r/stocks/search.rss")
    assert result.warnings == []
    assert result.metrics == []
    block = result.source_blocks[0]
    assert block.title == "NVDA retail thread"
    assert block.summary == "Discussion volume increased."
    assert block.url == "https://www.reddit.com/r/stocks/comments/1/nvda"
    assert block.as_of == datetime(2026, 1, 2, 10, tzinfo=UTC)
    assert block.symbols == ["NVDA"]
    assert block.metrics == []


def test_reddit_adapter_uses_rss_default_params_and_parses_atom_without_fake_metrics() -> None:
    text_fetcher = _FakeTextFetcher([_reddit_atom_fixture()])
    json_fetcher = _FakeJsonFetcher([_reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert json_fetcher.calls == []
    assert text_fetcher.calls == [
        (
            "https://www.reddit.com/r/stocks/search.rss",
            {"q": "NVDA", "restrict_sr": "on", "sort": "new", "t": "week", "limit": 5},
        )
    ]
    assert result.metrics == []
    block = result.source_blocks[0]
    assert block.title == "NVDA Atom thread"
    assert block.summary == "Retail interest rose for NVDA."
    assert block.url == "https://www.reddit.com/r/stocks/comments/3/nvda_atom/"
    assert block.as_of == datetime(2026, 1, 2, 10, 30, tzinfo=UTC)
    assert block.metrics == []


def test_reddit_adapter_retries_rss_429_once_with_injected_backoff() -> None:
    text_fetcher = _FakeTextFetcher([_reddit_rss_fixture()])
    text_fetcher.failures.append(SocialSentimentProviderRateLimitError("reddit rss rate limited"))
    sleep = _SleepRecorder()
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=_FakeJsonFetcher(),
            text_fetcher=text_fetcher,
            sleep=sleep,
        ),
    )

    result = adapter.fetch_source_blocks(
        "NVDA",
        start_date=None,
        end_date=None,
        limit=5,
    )

    assert len(text_fetcher.calls) == 2
    assert sleep.calls == [1.0]
    assert result.warnings == []
    assert [block.title for block in result.source_blocks] == ["NVDA retail thread"]


def test_reddit_adapter_caps_retry_after_and_warns_when_rss_stays_rate_limited() -> None:
    text_fetcher = _FakeTextFetcher()
    text_fetcher.failures.extend(
        [
            SocialSentimentProviderRateLimitError(
                "reddit rss rate limited",
                details={"status": "429", "retryAfterSeconds": "30"},
            ),
            SocialSentimentProviderRateLimitError(
                "reddit rss still rate limited",
                details={"status": "429", "retryAfterSeconds": "30"},
            ),
        ]
    )
    sleep = _SleepRecorder()
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(retry_after_max_seconds=2.0),
        transport=_RedditTransport(
            json_fetcher=_FakeJsonFetcher([_reddit_json_fixture()]),
            text_fetcher=text_fetcher,
            sleep=sleep,
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert len(text_fetcher.calls) == 2
    assert sleep.calls == [2.0]
    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_rate_limited"]
    assert result.warnings[0].details == {
        "provider": "reddit_public_search",
        "source": "reddit",
        "status": "429",
        "retryAfterSeconds": "30",
        "subreddit": "stocks",
    }


def test_reddit_adapter_falls_back_to_json_when_rss_is_unavailable() -> None:
    text_fetcher = _FakeTextFetcher()
    text_fetcher.failures.append(
        SocialSentimentProviderError(
            "reddit rss unavailable",
            code="provider_unavailable",
        )
    )
    json_fetcher = _FakeJsonFetcher([_reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.warnings == []
    assert result.metrics[0].name == "mention_count"
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.source_blocks[0].metrics[0].name == "score"


def test_reddit_adapter_falls_back_to_json_when_rss_is_malformed() -> None:
    text_fetcher = _FakeTextFetcher(["<feed>"])
    json_fetcher = _FakeJsonFetcher([_reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.source_blocks[0].metrics[0].name == "score"
    assert result.warnings == []


def test_reddit_adapter_falls_back_to_json_when_rss_is_empty() -> None:
    text_fetcher = _FakeTextFetcher([_reddit_empty_atom_fixture()])
    json_fetcher = _FakeJsonFetcher([_reddit_json_fixture()])
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert len(text_fetcher.calls) == 1
    assert len(json_fetcher.calls) == 1
    assert result.source_blocks[0].title == "NVDA JSON thread"
    assert result.metrics[0].name == "mention_count"


def test_reddit_adapter_preserves_useful_rss_when_later_json_fallback_fails() -> None:
    text_fetcher = _FakeTextFetcher([_reddit_atom_fixture(), _reddit_empty_atom_fixture()])
    json_fetcher = _FakeJsonFetcher()
    json_fetcher.failures.append(SocialSentimentProviderTimeoutError("reddit json timed out"))
    adapter = RedditSocialSentimentAdapter(
        timeout=1,
        config=_reddit_config(subreddits=("stocks", "investing")),
        transport=_RedditTransport(
            json_fetcher=json_fetcher,
            text_fetcher=text_fetcher,
            sleep=_SleepRecorder(),
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=10)

    assert [block.title for block in result.source_blocks] == ["NVDA Atom thread"]
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_timeout"]
    assert result.warnings[0].details["subreddit"] == "investing"


def test_stocktwits_adapter_returns_warning_instead_of_raising_on_failure() -> None:
    json_fetcher = _FakeJsonFetcher([_stocktwits_json_fixture()])
    json_fetcher.failures.append(
        SocialSentimentProviderRateLimitError(
            "stocktwits rate limited",
            details={"status": "429"},
        )
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=json_fetcher),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_rate_limited"]
    assert result.warnings[0].details == {
        "provider": "stocktwits_public_stream",
        "source": "stocktwits",
        "status": "429",
    }


def test_stocktwits_adapter_returns_warning_for_timeout_failure() -> None:
    json_fetcher = _FakeJsonFetcher()
    json_fetcher.failures.append(SocialSentimentProviderTimeoutError("stocktwits timed out"))
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=json_fetcher),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_timeout"]


def test_stocktwits_adapter_returns_warning_for_provider_unavailable_failure() -> None:
    json_fetcher = _FakeJsonFetcher()
    json_fetcher.failures.append(
        SocialSentimentProviderError(
            "stocktwits outage",
            code="provider_unavailable",
            details={"status": "503"},
        )
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=json_fetcher),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_unavailable"]
    assert result.warnings[0].details["status"] == "503"


def test_stocktwits_adapter_returns_warning_for_malformed_json_failure() -> None:
    json_fetcher = _FakeJsonFetcher()
    json_fetcher.failures.append(
        SocialSentimentProviderError(
            "stocktwits returned malformed json",
            details={"payload": "json"},
        )
    )
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=json_fetcher),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_error"]
    assert result.warnings[0].details["payload"] == "json"


def test_stocktwits_adapter_warns_when_messages_payload_is_missing() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=_FakeJsonFetcher([{}])),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_malformed_payload"]
    assert result.warnings[0].details["field"] == "messages"


def test_stocktwits_adapter_warns_when_messages_payload_is_not_a_list() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=_FakeJsonFetcher([{"messages": {"id": 123}}])),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["provider_malformed_payload"]
    assert result.warnings[0].details["field"] == "messages"


def test_stocktwits_adapter_skips_all_malformed_messages_with_warning() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(
            json_fetcher=_FakeJsonFetcher(
                [
                    {
                        "messages": [
                            "not an object",
                            {"id": 1, "created_at": "2026-01-02T12:00:00Z"},
                            {"id": 2, "body": "Invalid timestamp", "created_at": "not-a-date"},
                        ]
                    }
                ]
            )
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=5)

    assert result.source_blocks == []
    assert result.metrics == []
    assert [warning.code for warning in result.warnings] == ["source_partial"]
    assert result.warnings[0].details == {
        "malformedMessageCount": "3",
        "provider": "stocktwits_public_stream",
        "source": "stocktwits",
    }


def test_stocktwits_adapter_preserves_valid_metrics_when_payload_is_mixed() -> None:
    adapter = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(
            json_fetcher=_FakeJsonFetcher(
                [
                    {
                        "messages": [
                            _stocktwits_message(
                                message_id=1,
                                body="Bullish into earnings.",
                                created_at="2026-01-02T12:00:00Z",
                                sentiment="Bullish",
                            ),
                            {"id": 2, "created_at": "2026-01-02T12:01:00Z"},
                            _stocktwits_message(
                                message_id=3,
                                body="No label, just watching.",
                                created_at="2026-01-02T12:02:00Z",
                                sentiment=None,
                            ),
                            _stocktwits_message(
                                message_id=4,
                                body="Bearish below support.",
                                created_at="2026-01-02T12:03:00Z",
                                sentiment="Bearish",
                            ),
                            {"id": 5, "body": "Invalid timestamp", "created_at": "bad"},
                        ]
                    }
                ]
            )
        ),
    )

    result = adapter.fetch_source_blocks("NVDA", start_date=None, end_date=None, limit=10)

    assert [block.sentiment for block in result.source_blocks] == [
        "positive",
        None,
        "negative",
    ]
    metrics = {metric.name: metric.value for metric in result.metrics}
    assert metrics == {
        "message_count": Decimal("3"),
        "bullish_count": Decimal("1"),
        "bearish_count": Decimal("1"),
        "unlabeled_count": Decimal("1"),
        "bullish_ratio": Decimal("0.3333"),
        "bearish_ratio": Decimal("0.3333"),
    }
    assert [warning.code for warning in result.warnings] == ["source_partial"]
    assert result.warnings[0].details["malformedMessageCount"] == "2"


def test_social_sentiment_service_degrades_malformed_stocktwits_source() -> None:
    stocktwits = StockTwitsSocialSentimentAdapter(
        timeout=1,
        transport=_StockTwitsTransport(json_fetcher=_FakeJsonFetcher([{}])),
    )
    service = SocialSentimentService(source_adapters=[stocktwits])

    payload = _payload(service.get_social_sentiment_snapshot("NVDA", sources=["stocktwits"]))

    assert payload["sourceBlocks"] == []
    assert payload["metrics"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_empty_source",
        "social_sentiment_provider_error",
        "social_sentiment_unavailable",
    ]
    assert warnings[1]["details"] == {
        "operation": "social_sentiment",
        "symbol": "NVDA",
        "source": "stocktwits",
        "provider": "stocktwits_public_stream",
        "field": "messages",
    }


def test_social_sentiment_provider_factories_are_extension_owned() -> None:
    finance = next(
        extension for extension in INSTALLED_EXTENSIONS if extension.key == "signaldeck.finance"
    )
    adapters = create_social_sentiment_adapters()

    assert (
        finance.provider_factories["social_sentiment_adapters"] is create_social_sentiment_adapters
    )
    assert [adapter.source for adapter in adapters] == ["reddit", "stocktwits"]


def test_social_adapter_aggregates_reddit_stocktwits_source_blocks_and_metrics() -> None:
    reddit_as_of = datetime(2026, 1, 2, 10, tzinfo=UTC)
    stocktwits_as_of = datetime(2026, 1, 2, 12, tzinfo=UTC)
    reddit = _SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Retail thread",
                summary="Discussion volume increased.",
                as_of=reddit_as_of,
                symbols=["nvda"],
                sentiment="positive",
                metrics=[
                    ProviderSocialSentimentMetric(
                        name="comment_count",
                        value=Decimal("18"),
                        unit="count",
                        source="reddit",
                        as_of=reddit_as_of,
                    )
                ],
            )
        ],
        metrics=[
            ProviderSocialSentimentMetric(
                name="mention_count",
                value=Decimal("1"),
                unit="count",
                source="reddit",
                as_of=reddit_as_of,
            )
        ],
    )
    stocktwits = _SocialAdapter(
        source="stocktwits",
        provider_name="stocktwits_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="stocktwits",
                provider="stocktwits_fixture",
                title="@trader",
                summary="Bullish into earnings.",
                as_of=stocktwits_as_of,
                symbols=["NVDA"],
                sentiment="positive",
                metrics=[
                    ProviderSocialSentimentMetric(
                        name="message_count",
                        value=Decimal("1"),
                        unit="count",
                        source="stocktwits",
                        as_of=stocktwits_as_of,
                    )
                ],
            )
        ],
        metrics=[
            ProviderSocialSentimentMetric(
                name="bullish_ratio",
                value=Decimal("1"),
                source="stocktwits",
                as_of=stocktwits_as_of,
            )
        ],
    )
    service = SocialSentimentService(source_adapters=[reddit, stocktwits])

    result = service.get_social_sentiment_snapshot(
        " nvda ",
        sources=["stocktwits", "reddit", "stocktwits"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 1, 3, tzinfo=UTC),
        item_limit=5,
    )
    payload = _payload(result)

    assert payload["symbol"] == "NVDA"
    assert payload["sources"] == ["stocktwits", "reddit"]
    assert stocktwits.calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            6,
        )
    ]
    source_blocks = cast(list[dict[str, object]], payload["sourceBlocks"])
    assert [block["source"] for block in source_blocks] == ["stocktwits", "reddit"]
    assert source_blocks[0]["provider"] == "stocktwits_fixture"
    assert source_blocks[1]["symbols"] == ["NVDA"]
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert {metric["name"] for metric in metrics} == {"bullish_ratio", "mention_count"}
    assert payload["warnings"] == []


def test_social_adapter_partial_result_warns_for_missing_source() -> None:
    reddit = _SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Only Reddit covered",
                as_of=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ],
    )
    service = SocialSentimentService(source_adapters=[reddit])

    payload = _payload(
        service.get_social_sentiment_snapshot(
            "nvda",
            sources=["reddit", "stocktwits"],
            item_limit=5,
        )
    )

    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_unavailable",
        "social_sentiment_partial_result",
    ]
    assert warnings[1]["details"] == {
        "symbol": "NVDA",
        "sources": "reddit,stocktwits",
        "uncoveredSources": "stocktwits",
    }


def test_social_adapter_rate_limit_degrades_without_raw_secret() -> None:
    stocktwits = _SocialAdapter(
        source="stocktwits",
        provider_name="stocktwits_fixture",
        failure=SocialSentimentProviderRateLimitError(
            "stocktwits token=sk-secret rate limited",
            details={"status": "429", "api_key": "sk-secret"},
        ),
    )
    service = SocialSentimentService(source_adapters=[stocktwits])

    payload = _payload(service.get_social_sentiment_snapshot("nvda", sources=["stocktwits"]))

    assert payload["sourceBlocks"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_rate_limited",
        "social_sentiment_unavailable",
    ]
    warning_json = json.dumps(warnings)
    assert "sk-secret" not in warning_json
    assert "apiKey" not in warning_json


def test_social_adapter_timeout_degrades_with_structured_warning() -> None:
    reddit = _SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        failure=SocialSentimentProviderTimeoutError("reddit timed out"),
    )
    service = SocialSentimentService(source_adapters=[reddit])

    payload = _payload(service.get_social_sentiment_snapshot("nvda", sources=["reddit"]))

    assert payload["sourceBlocks"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_timeout",
        "social_sentiment_unavailable",
    ]


def test_social_adapter_empty_result_returns_structured_warning() -> None:
    reddit = _SocialAdapter(source="reddit", provider_name="reddit_fixture")
    service = SocialSentimentService(source_adapters=[reddit])

    payload = _payload(service.get_social_sentiment_snapshot("nvda", sources=["reddit"]))

    assert payload["sourceBlocks"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "social_sentiment_empty_source",
        "social_sentiment_unavailable",
    ]


def test_social_adapter_runtime_executor_uses_injected_service_adapters() -> None:
    reddit = _SocialAdapter(
        source="reddit",
        provider_name="reddit_fixture",
        blocks=[
            ProviderSocialSentimentSourceBlock(
                source="reddit",
                provider="reddit_fixture",
                title="Runtime path",
                as_of=datetime(2026, 1, 2, tzinfo=UTC),
                symbols=["NVDA"],
            )
        ],
    )
    registry = RuntimeToolRegistry([SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC])
    context = RuntimeToolContext(
        session_factory=cast(sessionmaker[Session], _failing_session_factory),
        capability_references=[{"capabilityKey": "social", "capabilityVersion": 1}],
        provider_bundle=finance_execution_provider_bundle_from_parts(
            social_sentiment_adapters=[reddit]
        ),
    )

    payload = registry.dispatch(
        name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": " nvda ",
                "sources": ["reddit"],
                "startDate": None,
                "endDate": None,
                "itemLimit": 3,
            }
        ),
        granted_tool_keys={SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY},
        context=context,
    )

    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["sourceBlocks"] != []
    assert reddit.calls == [("NVDA", None, None, 4)]
