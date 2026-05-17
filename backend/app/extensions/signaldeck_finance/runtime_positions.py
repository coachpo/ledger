from __future__ import annotations

import json
from typing import cast

from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec
from app.core.formatting import normalize_symbol
from app.extensions.signaldeck_finance.grant_policy import (
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    POSITION_LOOKUP_GRANT_POLICY,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.extensions.signaldeck_finance.runtime_types import POSITION_LOOKUP_TOOL_KEY
from app.services.position_service import PositionService

POSITION_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_positions_lookup"

_POSITION_LOOKUP_DISPLAY_NAME = "Position Lookup"
_POSITION_LOOKUP_DESCRIPTION = (
    "Read persisted SignalDeck positions for a portfolio slug, optionally filtered by symbol, "
    "limit, and offset."
)
_POSITION_LOOKUP_GUIDANCE = (
    "When you need persisted SignalDeck position context, call the "
    "signaldeck_positions_lookup tool instead of inventing portfolio holdings."
)
_POSITION_LOOKUP_INVALID_JSON_MESSAGE = (
    "OpenAI response requested signaldeck_positions_lookup with invalid JSON arguments."
)
_POSITION_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "portfolioSlug": {"type": "string"},
        "symbol": {"type": ["string", "null"]},
        "limit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 200,
        },
        "offset": {"type": ["integer", "null"], "minimum": 0},
    },
    "required": ["portfolioSlug", "symbol", "limit", "offset"],
    "additionalProperties": False,
}


def parse_position_lookup_arguments(arguments_json: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=_POSITION_LOOKUP_INVALID_JSON_MESSAGE,
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="signaldeck_positions_lookup arguments must be a JSON object.",
        )
    raw_arguments = cast(dict[str, object], raw_payload)

    allowed_keys = {"portfolioSlug", "symbol", "limit", "offset"}
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "signaldeck_positions_lookup arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )

    portfolio_slug = _parse_required_string_argument(
        raw_arguments.get("portfolioSlug"),
        field_name="portfolioSlug",
    )
    symbol = _parse_optional_string_argument(
        raw_arguments.get("symbol"),
        field_name="symbol",
    )
    if symbol is not None:
        symbol = normalize_symbol(symbol)
    return {
        "portfolio_slug": portfolio_slug,
        "symbol": symbol,
        "limit": _parse_optional_integer_argument(
            raw_arguments.get("limit"),
            field_name="limit",
            minimum=1,
            maximum=200,
        )
        or 50,
        "offset": _parse_optional_integer_argument(
            raw_arguments.get("offset"),
            field_name="offset",
            minimum=0,
        )
        or 0,
    }


def execute_position_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    with context.session_factory() as session:
        positions = PositionService(session, quote_provider=None).lookup_positions(
            capability_references=list(context.capability_references),
            grant_policy=POSITION_LOOKUP_GRANT_POLICY,
            portfolio_slug=cast(str, arguments["portfolio_slug"]),
            symbol=cast(str | None, arguments["symbol"]),
            limit=cast(int, arguments["limit"]),
            offset=cast(int, arguments["offset"]),
        )
    return {
        "count": len(positions),
        "portfolioSlug": arguments["portfolio_slug"],
        "positions": [
            cast(dict[str, object], position.model_dump(mode="json", by_alias=True))
            for position in positions
        ],
    }


def _parse_required_string_argument(value: object, *, field_name: str) -> str:
    normalized = _parse_optional_string_argument(value, field_name=field_name)
    if normalized is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_positions_lookup {field_name} is required.",
        )
    return normalized


def _parse_optional_string_argument(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_positions_lookup {field_name} must be a string.",
        )
    normalized = value.strip()
    return normalized or None


def _parse_optional_integer_argument(
    value: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_positions_lookup {field_name} must be an integer.",
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_positions_lookup {field_name} must be at least {minimum}.",
        )
    if maximum is not None and value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_positions_lookup {field_name} must be at most {maximum}.",
        )
    return int(value)


POSITION_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=POSITION_LOOKUP_TOOL_KEY,
    openai_function_name=POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name=_POSITION_LOOKUP_DISPLAY_NAME,
    description=_POSITION_LOOKUP_DESCRIPTION,
    parameters_schema=_POSITION_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_POSITION_LOOKUP_GUIDANCE,
    sort_order=20,
    denied_code=POSITION_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_position_lookup_arguments,
    executor=execute_position_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)


__all__ = [
    "POSITION_LOOKUP_OPENAI_FUNCTION_NAME",
    "POSITION_LOOKUP_TOOL_SPEC",
    "execute_position_lookup",
    "parse_position_lookup_arguments",
]
