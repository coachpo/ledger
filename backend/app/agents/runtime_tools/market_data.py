from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from app.agents.runtime_tools.types import (
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    RuntimeHistoryLookupResult,
    RuntimeQuoteLookupResult,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from app.core.formatting import normalize_currency, normalize_symbol
from app.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from app.services.capability_service import (
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
)
from app.services.market_data_service import MarketDataService, QuoteProvider, QuoteProviderError

MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME = "ledger_market_data_quote_lookup"
MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME = "ledger_market_data_history_lookup"

_QUOTE_SYMBOL_LIMIT = 10
_HISTORY_SYMBOL_LIMIT = 5
_HISTORY_DEFAULT_POINT_LIMIT = 120
_HISTORY_MAX_POINT_LIMIT = 250
_HISTORY_RANGES = {"1mo", "3mo", "ytd", "1y", "max"}

_QUOTE_LOOKUP_DESCRIPTION = "Read trusted market quote snapshots for up to 10 symbols."
_QUOTE_LOOKUP_GUIDANCE = (
    "When you need current or delayed market quotes, call the ledger_market_data_quote_lookup "
    "tool instead of inventing prices."
)
_QUOTE_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _QUOTE_SYMBOL_LIMIT,
        },
        "baseCurrency": {"type": ["string", "null"], "minLength": 3, "maxLength": 3},
    },
    "required": ["symbols", "baseCurrency"],
    "additionalProperties": False,
}

_HISTORY_LOOKUP_DESCRIPTION = (
    "Read trusted historical close-price series for up to 5 symbols and a bounded point count."
)
_HISTORY_LOOKUP_GUIDANCE = (
    "When you need historical market prices, call the ledger_market_data_history_lookup "
    "tool instead of inventing price history."
)
_HISTORY_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _HISTORY_SYMBOL_LIMIT,
        },
        "range": {"type": ["string", "null"], "enum": ["1mo", "3mo", "ytd", "1y", "max", None]},
        "pointLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _HISTORY_MAX_POINT_LIMIT,
        },
    },
    "required": ["symbols", "range", "pointLimit"],
    "additionalProperties": False,
}


def parse_quote_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "baseCurrency"},
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbols": _parse_symbols_argument(
            raw_arguments.get("symbols"),
            function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            maximum=_QUOTE_SYMBOL_LIMIT,
        ),
        "base_currency": _parse_base_currency(raw_arguments.get("baseCurrency")),
    }


def parse_history_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "range", "pointLimit"},
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbols": _parse_symbols_argument(
            raw_arguments.get("symbols"),
            function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            maximum=_HISTORY_SYMBOL_LIMIT,
        ),
        "range": _parse_history_range(raw_arguments.get("range")),
        "point_limit": _parse_optional_integer_argument(
            raw_arguments.get("pointLimit"),
            function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="pointLimit",
            minimum=1,
            maximum=_HISTORY_MAX_POINT_LIMIT,
        )
        or _HISTORY_DEFAULT_POINT_LIMIT,
    }


def execute_quote_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    quotes: list[MarketQuoteRead] = []
    warnings: list[RuntimeToolWarning] = []

    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        for symbol in cast(list[str], arguments["symbols"]):
            quote, raw_warnings = service.lookup_quote_snapshot(
                capability_references=context.capability_references,
                symbol=symbol,
                base_currency=cast(str, arguments["base_currency"]),
            )
            if quote is not None:
                quotes.append(quote)
            warnings.extend(
                _warning_models(raw_warnings, symbol=symbol, default_code="quote_unavailable")
            )

    return cast(
        dict[str, object],
        RuntimeQuoteLookupResult(quotes=quotes, warnings=warnings).model_dump(
            mode="json",
            by_alias=True,
        ),
    )


def execute_history_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    range_value = cast(str, arguments["range"])
    point_limit = cast(int, arguments["point_limit"])
    series: list[MarketHistorySeriesRead] = []
    warnings: list[RuntimeToolWarning] = []

    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        for symbol in cast(list[str], arguments["symbols"]):
            try:
                history = service.lookup_history_snapshot(
                    capability_references=context.capability_references,
                    symbol=symbol,
                    range_value=range_value,
                )
            except QuoteProviderError as exc:
                warnings.append(_warning_model(str(exc), symbol=symbol, code="history_unavailable"))
                continue
            series.extend(_trim_history_series(history.series, point_limit=point_limit))
            warnings.extend(
                _warning_models(history.warnings, symbol=symbol, default_code="history_unavailable")
            )

    bounds = _history_bounds(series)
    return cast(
        dict[str, object],
        RuntimeHistoryLookupResult(
            range=range_value,
            interval=MarketDataService.history_interval_by_range[range_value],
            start_date=bounds[0],
            end_date=bounds[1],
            series=series,
            warnings=warnings,
        ).model_dump(mode="json", by_alias=True),
    )


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"OpenAI response requested {function_name} with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} arguments must be a JSON object.",
        )
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(
    raw_arguments: dict[str, object],
    *,
    allowed_keys: set[str],
    function_name: str,
) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{function_name} arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )


def _parse_symbols_argument(value: object, *, function_name: str, maximum: int) -> list[str]:
    if value is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols is required.",
        )
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must be an array of strings.",
        )
    raw_symbols = cast(list[object], value)
    symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in raw_symbols:
        if not isinstance(raw_symbol, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} symbols must be an array of strings.",
            )
        symbol = normalize_symbol(raw_symbol)
        if not symbol:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} symbols must not contain empty values.",
            )
        if symbol in seen_symbols:
            continue
        symbols.append(symbol)
        seen_symbols.add(symbol)
    if not symbols:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must contain at least one symbol.",
        )
    if len(symbols) > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must contain at most {maximum} symbols.",
        )
    return symbols


def _parse_base_currency(value: object) -> str:
    if value is None:
        return "USD"
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME} " "baseCurrency must be a string."
            ),
        )
    normalized = normalize_currency(value)
    if len(normalized) != 3 or not normalized.isalpha():
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME} "
                "baseCurrency must be a 3-letter ISO code."
            ),
        )
    return normalized


def _parse_history_range(value: object) -> str:
    if value is None:
        return "3mo"
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME} range must be a string.",
        )
    normalized = value.strip().lower()
    if normalized not in _HISTORY_RANGES:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME} "
                "range must be one of 1mo, 3mo, ytd, 1y, or max."
            ),
        )
    return normalized


def _parse_optional_integer_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be an integer.",
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be at least {minimum}.",
        )
    if value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be at most {maximum}.",
        )
    return int(value)


def _require_quote_provider(context: RuntimeToolContext, *, function_name: str) -> QuoteProvider:
    if context.quote_provider is None:
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=f"{function_name} requires an injected quote provider.",
        )
    return context.quote_provider


def _trim_history_series(
    series: list[MarketHistorySeriesRead],
    *,
    point_limit: int,
) -> list[MarketHistorySeriesRead]:
    trimmed: list[MarketHistorySeriesRead] = []
    for item in series:
        points = item.points[-point_limit:]
        trimmed.append(
            MarketHistorySeriesRead(
                symbol=item.symbol,
                currency=item.currency,
                provider=item.provider,
                points=points,
            )
        )
    return trimmed


def _history_bounds(
    series: list[MarketHistorySeriesRead],
) -> tuple[datetime | None, datetime | None]:
    point_times = [point.at for item in series for point in item.points]
    if not point_times:
        return None, None
    return min(point_times), max(point_times)


def _warning_models(
    messages: list[str],
    *,
    symbol: str,
    default_code: str,
) -> list[RuntimeToolWarning]:
    return [_warning_model(message, symbol=symbol, code=default_code) for message in messages]


def _warning_model(message: str, *, symbol: str, code: str) -> RuntimeToolWarning:
    normalized_message = " ".join(message.split()).strip()
    return RuntimeToolWarning(
        code=code,
        message=normalized_message or f"Market data unavailable for {symbol}.",
        details={"symbol": symbol},
    )


MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Data Quote Lookup",
    description=_QUOTE_LOOKUP_DESCRIPTION,
    parameters_schema=_QUOTE_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_QUOTE_LOOKUP_GUIDANCE,
    sort_order=30,
    denied_code=MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_quote_lookup_arguments,
    executor=execute_quote_lookup,
)

MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Data History Lookup",
    description=_HISTORY_LOOKUP_DESCRIPTION,
    parameters_schema=_HISTORY_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_HISTORY_LOOKUP_GUIDANCE,
    sort_order=40,
    denied_code=MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_history_lookup_arguments,
    executor=execute_history_lookup,
)

__all__ = [
    "MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC",
    "execute_history_lookup",
    "execute_quote_lookup",
    "parse_history_lookup_arguments",
    "parse_quote_lookup_arguments",
]
