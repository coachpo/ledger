from __future__ import annotations

import json
from typing import cast

from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec
from app.core.formatting import normalize_symbol
from app.services.capability_service import (
    REPORT_LOOKUP_ACCESS_DENIED_CODE,
    REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_LOOKUP_TOOL_KEY,
)
from app.services.report_service import ReportService

REPORT_LOOKUP_OPENAI_FUNCTION_NAME = "ledger_reports_lookup"

_REPORT_LOOKUP_DISPLAY_NAME = "Report Lookup"
_REPORT_LOOKUP_DESCRIPTION = (
    "Read persisted Ledger reports by ticker, tag, review type, portfolio slug, source, "
    "limit, and offset."
)
_REPORT_LOOKUP_GUIDANCE = (
    "When you need persisted Ledger report context, call the ledger_reports_lookup tool instead "
    "of inventing report content."
)
_REPORT_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "ticker": {"type": ["string", "null"]},
        "tag": {"type": ["string", "null"]},
        "reviewType": {"type": ["string", "null"]},
        "portfolioSlug": {"type": ["string", "null"]},
        "source": {
            "type": ["string", "null"],
            "enum": ["compiled", "uploaded", "external", None],
        },
        "limit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 50,
        },
        "offset": {"type": ["integer", "null"], "minimum": 0},
    },
    "required": [
        "ticker",
        "tag",
        "reviewType",
        "portfolioSlug",
        "source",
        "limit",
        "offset",
    ],
    "additionalProperties": False,
}


def parse_report_lookup_arguments(arguments_json: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="OpenAI response requested ledger_reports_lookup with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="ledger_reports_lookup arguments must be a JSON object.",
        )
    raw_arguments = cast(dict[str, object], raw_payload)

    allowed_keys = {"ticker", "tag", "reviewType", "portfolioSlug", "source", "limit", "offset"}
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "ledger_reports_lookup arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )

    ticker = _parse_optional_string_argument(raw_arguments.get("ticker"))
    if ticker is not None:
        ticker = normalize_symbol(ticker)
    source = _parse_optional_string_argument(raw_arguments.get("source"))
    if source is not None and source not in {"compiled", "uploaded", "external"}:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="ledger_reports_lookup source must be one of compiled, uploaded, or external.",
        )
    return {
        "ticker": ticker,
        "tag": _parse_optional_string_argument(raw_arguments.get("tag")),
        "review_type": _parse_optional_string_argument(raw_arguments.get("reviewType")),
        "portfolio_slug": _parse_optional_string_argument(raw_arguments.get("portfolioSlug")),
        "source": source,
        "limit": _parse_optional_integer_argument(
            raw_arguments.get("limit"),
            field_name="limit",
            minimum=1,
            maximum=50,
        )
        or 50,
        "offset": _parse_optional_integer_argument(
            raw_arguments.get("offset"),
            field_name="offset",
            minimum=0,
        )
        or 0,
    }


def execute_report_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    with context.session_factory() as session:
        reports = ReportService(session).lookup_reports(
            capability_references=context.capability_references,
            ticker=cast(str | None, arguments["ticker"]),
            tag=cast(str | None, arguments["tag"]),
            review_type=cast(str | None, arguments["review_type"]),
            portfolio_slug=cast(str | None, arguments["portfolio_slug"]),
            source=cast(str | None, arguments["source"]),
            limit=cast(int, arguments["limit"]),
            offset=cast(int, arguments["offset"]),
        )
    return {
        "count": len(reports),
        "reports": [
            cast(dict[str, object], report.model_dump(mode="json", by_alias=True))
            for report in reports
        ],
    }


def _parse_optional_string_argument(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="ledger_reports_lookup string arguments must be strings.",
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
            message=f"ledger_reports_lookup {field_name} must be an integer.",
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"ledger_reports_lookup {field_name} must be at least {minimum}.",
        )
    if maximum is not None and value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"ledger_reports_lookup {field_name} must be at most {maximum}.",
        )
    return int(value)


REPORT_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=REPORT_LOOKUP_TOOL_KEY,
    openai_function_name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name=_REPORT_LOOKUP_DISPLAY_NAME,
    description=_REPORT_LOOKUP_DESCRIPTION,
    parameters_schema=_REPORT_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_REPORT_LOOKUP_GUIDANCE,
    sort_order=10,
    denied_code=REPORT_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_report_lookup_arguments,
    executor=execute_report_lookup,
)


__all__ = [
    "REPORT_LOOKUP_OPENAI_FUNCTION_NAME",
    "REPORT_LOOKUP_TOOL_SPEC",
    "execute_report_lookup",
    "parse_report_lookup_arguments",
]
