from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import (
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
    RuntimeToolContext,
    RuntimeToolRegistry,
)
from app.agents.runtime_tools.types import (
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeSocialSentimentLookupResult,
)
from app.extensions.ledger_finance.provider_factories import create_social_sentiment_adapters
from app.extensions.ledger_finance.provider_factories import (
    register as register_finance_workspace_provider_factories,
)
from app.services.social_sentiment_provider import (
    ProviderSocialSentimentMetric,
    ProviderSocialSentimentSourceBlock,
    ProviderSocialSentimentSourceResult,
    ProviderSocialSentimentWarning,
    SocialSentimentProviderError,
    SocialSentimentProviderRateLimitError,
    SocialSentimentProviderTimeoutError,
    SocialSentimentSource,
)
from app.services.social_sentiment_service import SocialSentimentService


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


def _failing_session_factory() -> object:
    raise AssertionError("social sentiment lookup should not open a database session")


def _payload(result: RuntimeSocialSentimentLookupResult) -> dict[str, object]:
    return cast(dict[str, object], result.model_dump(mode="json", by_alias=True))


def test_social_sentiment_provider_factories_are_extension_owned() -> None:
    registrations = {
        registration.key: registration
        for registration in register_finance_workspace_provider_factories()
    }
    adapters = create_social_sentiment_adapters()

    assert registrations["social_sentiment_adapters"].factory is create_social_sentiment_adapters
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

    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
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
        social_sentiment_adapters=[reddit],
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
