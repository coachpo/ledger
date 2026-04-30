from __future__ import annotations

from collections.abc import Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import (
    POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    POSITION_LOOKUP_TOOL_SPEC,
    REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    REPORT_LOOKUP_TOOL_SPEC,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolRegistry,
    RuntimeToolSpec,
)
from app.agents.runtime_tools.positions import parse_position_lookup_arguments
from app.agents.runtime_tools.reports import parse_report_lookup_arguments
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.services.position_service import PositionService
from app.services.report_service import ReportService
from app.services.skill_service import (
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_TOOL_KEY,
    REPORT_LOOKUP_TOOL_KEY,
)

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class _SessionScope:
    def __enter__(self) -> object:
        return object()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False


def _session_factory() -> _SessionScope:
    return _SessionScope()


def _failing_session_factory() -> _SessionScope:
    raise AssertionError("invalid runtime tool arguments should not open a session")


def _runtime_context(
    *,
    skill_references: Sequence[dict[str, object]] | None = None,
    fail_on_session: bool = False,
) -> RuntimeToolContext:
    session_factory = _failing_session_factory if fail_on_session else _session_factory
    return RuntimeToolContext(
        session_factory=cast(sessionmaker[Session], session_factory),
        skill_references=list(
            skill_references
            or [
                {
                    "skillKey": "runtime_tool_test_skill",
                    "skillVersion": 1,
                }
            ]
        ),
    )


def _parse_noop(arguments_json: str) -> dict[str, object]:
    return {"argumentsJson": arguments_json}


def _execute_noop(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    return {"arguments": arguments}


def _runtime_tool_spec(
    *,
    key: str = "ledger.test.lookup",
    openai_function_name: str = "ledger_test_lookup",
    sort_order: int = 10,
) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        key=key,
        openai_function_name=openai_function_name,
        display_name="Test Runtime Tool",
        description="Test runtime tool.",
        parameters_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        guidance=f"Call the {openai_function_name} tool for tests.",
        sort_order=sort_order,
        denied_code="agent_execution_access_denied",
        denied_message=f"Agent is not authorized to use {key}.",
        parser=_parse_noop,
        executor=_execute_noop,
    )


def _assert_strict_openai_tool_schema(tool: dict[str, object]) -> None:
    assert "displayName" not in tool
    assert "display_name" not in tool
    assert tool["type"] == "function"
    assert tool["strict"] is True
    parameters = cast(dict[str, object], tool["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == list(properties)


def _report_read() -> ReportRead:
    return ReportRead.model_validate(
        {
            "id": 7,
            "name": "NVDA Backend Lookup",
            "slug": "nvda_backend_lookup",
            "source": "external",
            "content": "# NVDA\n\nRevenue acceleration remains intact.",
            "metadata_": {
                "tags": ["earnings"],
                "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
            },
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )


def _position_read() -> PositionRead:
    return PositionRead.model_validate(
        {
            "id": 11,
            "portfolio_id": 5,
            "symbol": "NVDA",
            "name": "NVIDIA Corporation",
            "quantity": Decimal("12.00000000"),
            "average_cost": Decimal("101.50000000"),
            "currency": "USD",
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )


def test_runtime_tool_spec_is_frozen_and_separates_display_metadata_from_execution_fields() -> None:
    assert REPORT_LOOKUP_TOOL_SPEC.key == REPORT_LOOKUP_TOOL_KEY
    assert REPORT_LOOKUP_TOOL_SPEC.openai_function_name == REPORT_LOOKUP_OPENAI_FUNCTION_NAME
    assert REPORT_LOOKUP_TOOL_SPEC.display_name == "Report Lookup"
    assert REPORT_LOOKUP_TOOL_SPEC.key != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.openai_function_name
    assert REPORT_LOOKUP_TOOL_SPEC.display_name != REPORT_LOOKUP_TOOL_SPEC.description

    assert POSITION_LOOKUP_TOOL_SPEC.key == POSITION_LOOKUP_TOOL_KEY
    assert POSITION_LOOKUP_TOOL_SPEC.openai_function_name == POSITION_LOOKUP_OPENAI_FUNCTION_NAME
    assert POSITION_LOOKUP_TOOL_SPEC.display_name == "Position Lookup"
    assert POSITION_LOOKUP_TOOL_SPEC.key != POSITION_LOOKUP_TOOL_SPEC.openai_function_name
    assert POSITION_LOOKUP_TOOL_SPEC.display_name != POSITION_LOOKUP_TOOL_SPEC.openai_function_name
    assert POSITION_LOOKUP_TOOL_SPEC.display_name != POSITION_LOOKUP_TOOL_SPEC.description

    field_name = "key"
    with pytest.raises(FrozenInstanceError):
        setattr(REPORT_LOOKUP_TOOL_SPEC, field_name, "ledger.changed")


def test_runtime_tool_context_carries_session_factory_and_skill_references() -> None:
    skill_references: list[dict[str, object]] = [{"skillKey": "report_reader", "skillVersion": 3}]
    context = _runtime_context(skill_references=skill_references)

    assert context.session_factory is not None
    assert context.skill_references == skill_references


def test_runtime_tool_registry_rejects_duplicate_keys_and_openai_function_names() -> None:
    spec = _runtime_tool_spec()

    with pytest.raises(ValueError, match="Duplicate runtime tool key"):
        _ = RuntimeToolRegistry(
            [spec, replace(spec, openai_function_name="ledger_test_lookup_alt")]
        )

    with pytest.raises(ValueError, match="Duplicate runtime tool OpenAI function name"):
        _ = RuntimeToolRegistry([spec, replace(spec, key="ledger.test.lookup.alt")])


def test_runtime_tool_registry_returns_granted_strict_definitions_in_sort_order() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC, REPORT_LOOKUP_TOOL_SPEC])

    tools = registry.get_openai_tool_definitions({POSITION_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in tools] == [
        REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    ]
    for tool in tools:
        _assert_strict_openai_tool_schema(tool)
    assert tools[0]["description"] == (
        "Read persisted Ledger reports by ticker, tag, review type, portfolio slug, source, "
        "limit, and offset."
    )
    assert tools[1]["description"] == (
        "Read persisted Ledger positions for a portfolio slug, optionally filtered by symbol, "
        "limit, and offset."
    )

    report_parameters = cast(dict[str, object], tools[0]["parameters"])
    report_properties = cast(dict[str, object], report_parameters["properties"])
    assert report_parameters["required"] == [
        "ticker",
        "tag",
        "reviewType",
        "portfolioSlug",
        "source",
        "limit",
        "offset",
    ]
    source_property = cast(dict[str, object], report_properties["source"])
    assert source_property["enum"] == [
        "compiled",
        "uploaded",
        "external",
        None,
    ]
    position_parameters = cast(dict[str, object], tools[1]["parameters"])
    position_properties = cast(dict[str, object], position_parameters["properties"])
    assert position_parameters["required"] == ["portfolioSlug", "symbol", "limit", "offset"]
    position_limit_property = cast(dict[str, object], position_properties["limit"])
    assert position_limit_property["maximum"] == 200

    position_only_tools = registry.get_openai_tool_definitions({POSITION_LOOKUP_TOOL_KEY})
    assert [tool["name"] for tool in position_only_tools] == [POSITION_LOOKUP_OPENAI_FUNCTION_NAME]


def test_runtime_tool_registry_deep_copies_openai_parameter_schemas() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    tools = registry.get_openai_tool_definitions({REPORT_LOOKUP_TOOL_KEY})
    parameters = cast(dict[str, object], tools[0]["parameters"])
    properties = cast(dict[str, object], parameters["properties"])
    ticker_property = cast(dict[str, object], properties["ticker"])
    ticker_property["type"] = "mutated"

    fresh_tools = registry.get_openai_tool_definitions({REPORT_LOOKUP_TOOL_KEY})

    fresh_parameters = cast(dict[str, object], fresh_tools[0]["parameters"])
    fresh_properties = cast(dict[str, object], fresh_parameters["properties"])
    fresh_ticker_property = cast(dict[str, object], fresh_properties["ticker"])
    assert fresh_ticker_property["type"] == [
        "string",
        "null",
    ]


def test_runtime_tool_registry_aggregates_guidance_in_sort_order() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC, REPORT_LOOKUP_TOOL_SPEC])

    assert registry.get_guidance({POSITION_LOOKUP_TOOL_KEY, REPORT_LOOKUP_TOOL_KEY}) == (
        "When you need persisted Ledger report context, call the ledger_reports_lookup tool "
        "instead of inventing report content.\n\n"
        "When you need persisted Ledger position context, call the ledger_positions_lookup tool "
        "instead of inventing portfolio holdings."
    )
    assert registry.get_guidance(set()) == ""


def test_runtime_tool_registry_rejects_unknown_and_ungranted_names_before_parsing() -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as unknown_error:
        _ = registry.dispatch(
            name="ledger_unknown_lookup",
            arguments_json='{"portfolioSlug":"reference"}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert unknown_error.value.code == "agent_tool_call_unsupported"
    assert (
        unknown_error.value.message
        == "Agent requested unsupported server tool 'ledger_unknown_lookup'."
    )

    with pytest.raises(RuntimeToolError) as ungranted_error:
        _ = registry.dispatch(
            name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json="not-json",
            granted_tool_keys=set(),
            context=context,
        )
    assert ungranted_error.value.code == POSITION_LOOKUP_ACCESS_DENIED_CODE
    assert ungranted_error.value.message == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested ledger_reports_lookup with invalid JSON arguments.",
        ),
        ("[]", "ledger_reports_lookup arguments must be a JSON object."),
        (
            '{"unsupported":true}',
            "ledger_reports_lookup arguments contained unsupported fields: unsupported",
        ),
        (
            '{"source":"manual"}',
            "ledger_reports_lookup source must be one of compiled, uploaded, or external.",
        ),
        ('{"ticker":123}', "ledger_reports_lookup string arguments must be strings."),
        ('{"limit":51}', "ledger_reports_lookup limit must be at most 50."),
        ('{"offset":-1}', "ledger_reports_lookup offset must be at least 0."),
    ],
)
def test_report_runtime_tool_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_report_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


@pytest.mark.parametrize(
    ("arguments_json", "expected_message"),
    [
        (
            "{",
            "OpenAI response requested ledger_positions_lookup with invalid JSON arguments.",
        ),
        ("[]", "ledger_positions_lookup arguments must be a JSON object."),
        (
            '{"portfolioSlug":"reference","unsupported":true}',
            "ledger_positions_lookup arguments contained unsupported fields: unsupported",
        ),
        ("{}", "ledger_positions_lookup portfolioSlug is required."),
        ('{"portfolioSlug":123}', "ledger_positions_lookup portfolioSlug must be a string."),
        (
            '{"portfolioSlug":"reference","limit":"1"}',
            "ledger_positions_lookup limit must be an integer.",
        ),
        (
            '{"portfolioSlug":"reference","limit":201}',
            "ledger_positions_lookup limit must be at most 200.",
        ),
        (
            '{"portfolioSlug":"reference","offset":-1}',
            "ledger_positions_lookup offset must be at least 0.",
        ),
    ],
)
def test_position_runtime_tool_parser_preserves_validation_messages(
    arguments_json: str,
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        _ = parse_position_lookup_arguments(arguments_json)

    assert exc_info.value.code == "agent_tool_call_invalid"
    assert exc_info.value.message == expected_message
    assert exc_info.value.details == []


def test_registry_dispatch_rejects_invalid_arguments_before_service_execution() -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC, POSITION_LOOKUP_TOOL_SPEC])
    context = _runtime_context(fail_on_session=True)

    with pytest.raises(RuntimeToolError) as report_error:
        _ = registry.dispatch(
            name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"limit":51}',
            granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert report_error.value.message == "ledger_reports_lookup limit must be at most 50."

    with pytest.raises(RuntimeToolError) as position_error:
        _ = registry.dispatch(
            name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
            arguments_json='{"portfolioSlug":"reference","limit":201}',
            granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
            context=context,
        )
    assert position_error.value.message == "ledger_positions_lookup limit must be at most 200."


def test_report_runtime_tool_dispatches_to_report_service_with_defaults_and_output_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([REPORT_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_reports(
        self: ReportService,
        *,
        skill_references: Sequence[dict[str, object]],
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        del self
        captured_calls.append(
            {
                "skill_references": skill_references,
                "ticker": ticker,
                "tag": tag,
                "review_type": review_type,
                "portfolio_slug": portfolio_slug,
                "source": source,
                "limit": limit,
                "offset": offset,
            }
        )
        return [_report_read()]

    monkeypatch.setattr(ReportService, "lookup_reports", fake_lookup_reports)

    payload = registry.dispatch(
        name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"ticker":" nvda "}',
        granted_tool_keys={REPORT_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )

    assert captured_calls == [
        {
            "skill_references": [{"skillKey": "runtime_tool_test_skill", "skillVersion": 1}],
            "ticker": "NVDA",
            "tag": None,
            "review_type": None,
            "portfolio_slug": None,
            "source": None,
            "limit": 50,
            "offset": 0,
        }
    ]
    assert payload["count"] == 1
    reports = cast(list[dict[str, object]], payload["reports"])
    assert len(reports) == 1
    assert reports[0]["slug"] == "nvda_backend_lookup"
    assert reports[0]["metadata"] == {
        "author": None,
        "description": None,
        "tags": ["earnings"],
        "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
    }
    assert reports[0]["createdAt"] == "2026-01-02T03:04:05Z"


def test_position_runtime_tool_dispatches_to_position_service_with_defaults_and_output_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = RuntimeToolRegistry([POSITION_LOOKUP_TOOL_SPEC])
    captured_calls: list[dict[str, object]] = []

    def fake_lookup_positions(
        self: PositionService,
        *,
        skill_references: list[dict[str, object]],
        portfolio_slug: str,
        symbol: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PositionRead]:
        captured_calls.append(
            {
                "skill_references": skill_references,
                "portfolio_slug": portfolio_slug,
                "symbol": symbol,
                "limit": limit,
                "offset": offset,
                "quote_provider": self.quote_provider,
            }
        )
        if portfolio_slug == "unknown_portfolio":
            return []
        return [_position_read()]

    monkeypatch.setattr(PositionService, "lookup_positions", fake_lookup_positions)

    payload = registry.dispatch(
        name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"portfolioSlug":" position_lookup_reference ","symbol":" nvda "}',
        granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )

    assert captured_calls[0] == {
        "skill_references": [{"skillKey": "runtime_tool_test_skill", "skillVersion": 1}],
        "portfolio_slug": "position_lookup_reference",
        "symbol": "NVDA",
        "limit": 50,
        "offset": 0,
        "quote_provider": None,
    }
    assert payload == {
        "count": 1,
        "portfolioSlug": "position_lookup_reference",
        "positions": [
            {
                "id": 11,
                "portfolioId": 5,
                "symbol": "NVDA",
                "name": "NVIDIA Corporation",
                "quantity": "12.00000000",
                "averageCost": "101.50000000",
                "currency": "USD",
                "createdAt": "2026-01-02T03:04:05Z",
                "updatedAt": "2026-01-02T03:04:05Z",
            }
        ],
    }

    empty_payload = registry.dispatch(
        name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
        arguments_json='{"portfolioSlug":"unknown_portfolio","symbol":"NVDA","limit":10,"offset":0}',
        granted_tool_keys={POSITION_LOOKUP_TOOL_KEY},
        context=_runtime_context(),
    )
    assert empty_payload == {
        "count": 0,
        "portfolioSlug": "unknown_portfolio",
        "positions": [],
    }
