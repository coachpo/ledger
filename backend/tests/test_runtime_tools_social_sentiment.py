from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import (
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolRegistry,
)
from app.agents.runtime_tools.market_data import (
    parse_news_lookup_arguments,
    parse_social_sentiment_lookup_arguments,
)
from app.agents.runtime_tools.types import (
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeSocialSentimentLookupResult,
    RuntimeSocialSentimentMetric,
    RuntimeSocialSentimentSourceBlock,
    RuntimeToolWarning,
)
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _failing_session_factory() -> object:
    raise AssertionError("social sentiment contract tests should not open a database session")


def _runtime_context() -> RuntimeToolContext:
    return RuntimeToolContext(
        session_factory=cast(sessionmaker[Session], _failing_session_factory),
        capability_references=[{"capabilityKey": "social_test", "capabilityVersion": 1}],
    )


def _assert_json_safe_and_camel(payload: dict[str, object]) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return

    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


def test_social_sentiment_result_schema_normalizes_source_blocks_metrics_and_warnings() -> None:
    payload = RuntimeSocialSentimentLookupResult(
        symbol=" nvda ",
        sources=["Reddit", "stocktwits", "reddit"],
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=_NOW,
        source_blocks=[
            RuntimeSocialSentimentSourceBlock(
                source="Reddit",
                provider=" deterministic_fixture ",
                title=" Retail discussion ",
                summary=" Mentions increased. ",
                as_of=_NOW,
                symbols=[" nvda ", "NVDA"],
                sentiment="positive",
                metrics=[
                    RuntimeSocialSentimentMetric(
                        name="Mention Count",
                        value=Decimal("12"),
                        unit=" count ",
                        source="Reddit",
                        as_of=_NOW,
                    )
                ],
            )
        ],
        metrics=[RuntimeSocialSentimentMetric(name="Bullish Ratio", value=Decimal("0.67"))],
        warnings=[
            RuntimeToolWarning(
                code="source_partial",
                message="StockTwits returned a partial window.",
                details={"source": "stocktwits"},
            )
        ],
    ).model_dump(mode="json", by_alias=True)

    _assert_json_safe_and_camel(payload)
    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["sources"] == ["reddit", "stocktwits"]
    assert payload["startDate"] == "2026-01-01T00:00:00Z"
    assert payload["endDate"] == "2026-01-02T03:04:05Z"
    source_blocks = cast(list[dict[str, object]], payload["sourceBlocks"])
    assert source_blocks[0]["source"] == "reddit"
    assert source_blocks[0]["provider"] == "deterministic_fixture"
    assert source_blocks[0]["symbols"] == ["NVDA"]
    block_metrics = cast(list[dict[str, object]], source_blocks[0]["metrics"])
    assert block_metrics[0] == {
        "name": "mention_count",
        "value": "12",
        "unit": "count",
        "source": "reddit",
        "asOf": "2026-01-02T03:04:05Z",
    }
    metrics = cast(list[dict[str, object]], payload["metrics"])
    assert metrics[0]["name"] == "bullish_ratio"
    assert cast(list[dict[str, object]], payload["warnings"])[0]["code"] == "source_partial"

    with pytest.raises(ValidationError, match="startDate must be before or equal to endDate"):
        _ = RuntimeSocialSentimentLookupResult(
            symbol="NVDA",
            start_date=_NOW,
            end_date=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_social_sentiment_parser_validation_normalizes_inputs_separately_from_news_lookup() -> None:
    social_arguments = parse_social_sentiment_lookup_arguments(
        json.dumps(
            {
                "symbol": " nvda ",
                "sources": ["StockTwits", "reddit", "stocktwits"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-02T03:04:05Z",
                "itemLimit": None,
            }
        )
    )
    news_arguments = parse_news_lookup_arguments(
        json.dumps(
            {
                "symbols": [" nvda "],
                "query": " social chatter ",
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        )
    )

    assert social_arguments == {
        "symbol": "NVDA",
        "sources": ("stocktwits", "reddit"),
        "start_date": datetime(2026, 1, 1, tzinfo=UTC),
        "end_date": _NOW,
        "item_limit": 25,
    }
    assert news_arguments == {
        "symbols": ["NVDA"],
        "query": "social chatter",
        "start_date": None,
        "end_date": None,
        "item_limit": 25,
    }
    assert "sources" not in news_arguments
    assert "query" not in social_arguments


@pytest.mark.parametrize(
    ("arguments", "expected_message"),
    [
        (
            {
                "symbol": "NVDA",
                "sources": ["forums"],
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "ledger_social_sentiment_lookup sources must use: reddit, stocktwits.",
        ),
        (
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": "2026-01-04",
                "endDate": "2026-01-03",
                "itemLimit": 2,
            },
            "ledger_social_sentiment_lookup startDate must be before or equal to endDate.",
        ),
        (
            {
                "symbol": " ",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 2,
            },
            "ledger_social_sentiment_lookup symbol is required.",
        ),
        (
            {
                "symbol": "NVDA",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": 51,
            },
            "ledger_social_sentiment_lookup itemLimit must be at most 50.",
        ),
    ],
)
def test_social_sentiment_invalid_arguments_fail_deterministically(
    arguments: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_social_sentiment_lookup_arguments(json.dumps(arguments))

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


def test_social_sentiment_dispatch_returns_deterministic_provider_boundary_warnings() -> None:
    registry = RuntimeToolRegistry([SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC])

    payload = registry.dispatch(
        name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json=json.dumps(
            {
                "symbol": " nvda ",
                "sources": None,
                "startDate": None,
                "endDate": None,
                "itemLimit": None,
            }
        ),
        granted_tool_keys={SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )

    _assert_json_safe_and_camel(payload)
    assert payload["toolKey"] == SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["symbol"] == "NVDA"
    assert payload["sources"] == ["reddit", "stocktwits"]
    assert payload["sourceBlocks"] == []
    assert payload["metrics"] == []
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "social_sentiment_provider_unavailable",
        "social_sentiment_unavailable",
    ]
    assert warnings[0]["details"] == {"operation": "social_sentiment", "symbol": "NVDA"}
    assert warnings[1]["details"] == {
        "operation": "social_sentiment",
        "symbol": "NVDA",
        "sources": "reddit,stocktwits",
    }


def test_tradingagents_fixture_grants_social_sentiment_separately_from_news_lookup() -> None:
    compiled = compile_workflow_package_manifest(_FIXTURE_PATH.read_text(encoding="utf-8"))
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    spec = cast(dict[str, object], package_definition["spec"])
    profiles_by_key = {
        str(profile["key"]): profile
        for profile in cast(list[dict[str, object]], spec["capabilityProfiles"])
    }
    agents_by_key = {
        str(agent["key"]): agent for agent in cast(list[dict[str, object]], spec["agents"])
    }

    assert cast(list[str], profiles_by_key["social_sentiment_tools"]["toolKeys"]) == [
        SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
    ]
    assert cast(list[str], profiles_by_key["news_research_tools"]["toolKeys"]) == [
        "ledger.news.lookup",
        "ledger.insider_data.lookup",
    ]
    assert cast(list[str], agents_by_key["social_analyst"]["capabilityProfiles"]) == [
        "social_sentiment_tools"
    ]
    assert cast(list[str], agents_by_key["news_analyst"]["capabilityProfiles"]) == [
        "news_research_tools"
    ]
