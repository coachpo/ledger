from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.model_gateway_dto import ModelExecutionRequest, ModelGatewayError, ModelToolCall

_NATIVE_TOOL_CAPABILITY = "nativeToolCalls"
_PARALLEL_TOOL_CAPABILITY = "parallelToolCalls"
_UNSUPPORTED = "unsupported"
_NOT_APPLICABLE = "notApplicable"
_TOOL_BLOCKING_STATUSES = {_UNSUPPORTED, _NOT_APPLICABLE}
_ALLOW_PARALLEL = "allow"
_SERIALIZE_PARALLEL = "serialize"
_FORBID_TOOLS = "forbid"


@dataclass(frozen=True, slots=True)
class ModelToolStrategySelection:
    has_tools: bool
    allow_parallel_tool_calls: bool


def select_tool_strategy(request: ModelExecutionRequest) -> ModelToolStrategySelection:
    if not request.tools:
        return ModelToolStrategySelection(has_tools=False, allow_parallel_tool_calls=False)

    policy = request.connection.parallel_tool_calls_policy
    if policy == _FORBID_TOOLS:
        raise ModelGatewayError(
            code="model_capability_required_missing",
            message="Model connection policy forbids tool calls required by this package.",
            details=[{"field": "parallelToolCallsPolicy", "issue": "Policy forbids tools"}],
        )
    native_status = _capability_status(request, _NATIVE_TOOL_CAPABILITY)
    if native_status in _TOOL_BLOCKING_STATUSES:
        raise ModelGatewayError(
            code="model_capability_required_missing",
            message="Model connection does not support required native tool calls.",
            details=[{"field": _NATIVE_TOOL_CAPABILITY, "issue": f"Capability is {native_status}"}],
        )

    parallel_status = _capability_status(request, _PARALLEL_TOOL_CAPABILITY)
    allow_parallel = policy == _ALLOW_PARALLEL and parallel_status not in _TOOL_BLOCKING_STATUSES
    if policy not in {_ALLOW_PARALLEL, _SERIALIZE_PARALLEL}:
        allow_parallel = False
    return ModelToolStrategySelection(
        has_tools=True,
        allow_parallel_tool_calls=allow_parallel,
    )


def build_model_tool_call(
    *,
    name: Any,
    arguments: Any,
    call_id: Any,
    context: str,
) -> ModelToolCall:
    normalized_name = _required_tool_call_text(name, field="name", context=context)
    normalized_call_id = _required_tool_call_text(call_id, field="call id", context=context)
    if not isinstance(arguments, str):
        raise _invalid_tool_call(
            context=context,
            issue=f"Tool call {normalized_name!r} did not include JSON-string arguments.",
        )
    _validate_arguments_json(arguments, context=context, tool_name=normalized_name)
    return ModelToolCall(
        tool_name=normalized_name,
        arguments_json=arguments,
        call_id=normalized_call_id,
    )


def _capability_status(request: ModelExecutionRequest, key: str) -> str | None:
    capabilities = request.connection.capabilities or {}
    raw_state = capabilities.get(key)
    if not isinstance(raw_state, Mapping):
        return None
    raw_status = raw_state.get("status")
    return raw_status if isinstance(raw_status, str) else None


def _required_tool_call_text(value: Any, *, field: str, context: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise _invalid_tool_call(context=context, issue=f"Tool call is missing a valid {field}.")


def _validate_arguments_json(arguments: str, *, context: str, tool_name: str) -> None:
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise _invalid_tool_call(
            context=context,
            issue=f"Tool call {tool_name!r} arguments are not valid JSON.",
        ) from exc
    if not isinstance(payload, Mapping):
        raise _invalid_tool_call(
            context=context,
            issue=f"Tool call {tool_name!r} arguments must be a JSON object.",
        )


def _invalid_tool_call(*, context: str, issue: str) -> ModelGatewayError:
    return ModelGatewayError(
        code="model_tool_call_payload_invalid",
        message=f"{context} returned a malformed tool call payload.",
        details=[{"field": "toolCall", "issue": issue}],
    )


__all__ = [
    "ModelToolStrategySelection",
    "build_model_tool_call",
    "select_tool_strategy",
]
