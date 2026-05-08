from __future__ import annotations

import json
from typing import cast

from pydantic import ValidationError

from app.agents.runtime_tools.types import (
    REPORT_MEMORY_WRITE_TOOL_KEY,
    RuntimeReportMemoryWriteResult,
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
)
from app.core.formatting import normalize_symbol
from app.schemas.memory_report import (
    AgentMemoryReportCreateMetadata,
    AgentMemoryTrustedCreateContext,
)
from app.services.capability_service import (
    REPORT_LOOKUP_ACCESS_DENIED_CODE,
    REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_LOOKUP_TOOL_KEY,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
)
from app.services.memory_service import MemoryService
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
            "enum": ["compiled", "uploaded", "external", "agent", None],
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

REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME = "ledger_reports_write"

_REPORT_MEMORY_WRITE_DISPLAY_NAME = "Report Memory Write"
_REPORT_MEMORY_WRITE_DESCRIPTION = "Create a pending agent-memory report from decision text."
_REPORT_MEMORY_WRITE_GUIDANCE = (
    "When you commit a trading decision that should be remembered, call the "
    "ledger_reports_write tool with only ticker, portfolio/horizon context, confidence, "
    "summary, and decision text. Do not include run, agent, workflow, outcome, return, "
    "alpha, timestamp, or reflection fields."
)
_REPORT_MEMORY_WRITE_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "portfolioSlug": {"type": ["string", "null"]},
                "horizonDays": {"type": ["integer", "null"], "minimum": 1},
                "confidence": {"type": ["string", "null"]},
                "decisionSummary": {"type": ["string", "null"]},
                "decision": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["buy", "hold", "sell"]},
                        "rationale": {"type": "string"},
                        "riskSummary": {"type": "string"},
                        "executionPlan": {"type": "string"},
                    },
                    "required": ["action", "rationale", "riskSummary", "executionPlan"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "ticker",
                "portfolioSlug",
                "horizonDays",
                "confidence",
                "decisionSummary",
                "decision",
            ],
            "additionalProperties": False,
        }
    },
    "required": ["analysis"],
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
    if source is not None and source not in {"compiled", "uploaded", "external", "agent"}:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "ledger_reports_lookup source must be one of compiled, uploaded, external, "
                "or agent."
            ),
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


def parse_report_memory_write_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"analysis"},
        function_name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    )
    try:
        payload = AgentMemoryReportCreateMetadata.model_validate(raw_arguments)
    except ValidationError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="ledger_reports_write arguments failed validation.",
            details=_validation_details_from_pydantic_error(exc),
        ) from exc
    return {"payload": payload}


def execute_report_memory_write(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    trusted_context = _trusted_memory_write_context(context)
    payload = cast(AgentMemoryReportCreateMetadata, arguments["payload"])
    memory_request = MemoryService.write_request_from_report_create(
        payload=payload,
        trusted_context=trusted_context,
    )
    with context.session_factory() as session:
        result = MemoryService(session).write_memory(
            capability_references=context.capability_references,
            payload=memory_request,
        )
    return cast(
        dict[str, object],
        RuntimeReportMemoryWriteResult.from_memory_write_result(result).model_dump(
            mode="json",
            by_alias=True,
        ),
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


def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(str(part) for part in location) if location else "input"
        details.append(
            {
                "field": field or "input",
                "issue": str(error.get("msg", "Invalid value")),
            }
        )
    return details


def _trusted_memory_write_context(
    context: RuntimeToolContext,
) -> AgentMemoryTrustedCreateContext:
    run_id = context.run_id
    agent_key = context.agent_key
    agent_version = context.agent_version
    step_id = context.step_id
    slot = context.slot
    missing_fields: list[str] = []
    if run_id is None:
        missing_fields.append("runId")
    if agent_key is None:
        missing_fields.append("agentKey")
    if agent_version is None:
        missing_fields.append("agentVersion")
    if step_id is None:
        missing_fields.append("stepId")
    if slot is None:
        missing_fields.append("slot")
    if missing_fields:
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=(
                "ledger_reports_write requires runtime context fields: "
                f"{', '.join(missing_fields)}."
            ),
        )
    assert run_id is not None
    assert agent_key is not None
    assert agent_version is not None
    assert step_id is not None
    assert slot is not None
    return AgentMemoryTrustedCreateContext(
        run_id=run_id,
        agent_key=agent_key,
        agent_version=agent_version,
        agent_name=context.agent_name,
        workflow_key=context.workflow_key,
        workflow_version=context.workflow_version,
        step_id=step_id,
        slot=slot,
        trace_id=context.trace_id,
    )


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

REPORT_MEMORY_WRITE_TOOL_SPEC = RuntimeToolSpec(
    key=REPORT_MEMORY_WRITE_TOOL_KEY,
    openai_function_name=REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    display_name=_REPORT_MEMORY_WRITE_DISPLAY_NAME,
    description=_REPORT_MEMORY_WRITE_DESCRIPTION,
    parameters_schema=_REPORT_MEMORY_WRITE_PARAMETERS_SCHEMA,
    guidance=_REPORT_MEMORY_WRITE_GUIDANCE,
    sort_order=15,
    denied_code=REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    denied_message=REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    parser=parse_report_memory_write_arguments,
    executor=execute_report_memory_write,
)


__all__ = [
    "REPORT_LOOKUP_OPENAI_FUNCTION_NAME",
    "REPORT_LOOKUP_TOOL_SPEC",
    "REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME",
    "REPORT_MEMORY_WRITE_TOOL_SPEC",
    "execute_report_lookup",
    "execute_report_memory_write",
    "parse_report_lookup_arguments",
    "parse_report_memory_write_arguments",
]
