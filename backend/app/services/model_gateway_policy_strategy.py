from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.services.model_gateway_dto import (
    ModelExecutionRequest,
    ModelExecutionStrategies,
    ModelGatewayError,
)

_REASONING_CAPABILITY = "reasoningHints"
_UNSUPPORTED = "unsupported"
_NOT_APPLICABLE = "notApplicable"
_REASONING_BLOCKING_STATUSES = {_UNSUPPORTED, _NOT_APPLICABLE}


@dataclass(frozen=True, slots=True)
class ModelReasoningStrategySelection:
    strategy: str
    reasoning_effort: str | None


@dataclass(frozen=True, slots=True)
class ModelStreamingStrategySelection:
    strategy: str


def select_reasoning_strategy(
    request: ModelExecutionRequest,
) -> ModelReasoningStrategySelection:
    if request.connection.reasoning_policy == "forbid":
        return ModelReasoningStrategySelection(
            strategy="disabledByPolicy",
            reasoning_effort=None,
        )
    reasoning_effort = request.connection.reasoning_effort
    if reasoning_effort is None:
        return ModelReasoningStrategySelection(
            strategy="disabled",
            reasoning_effort=None,
        )
    status = _capability_status(request, _REASONING_CAPABILITY)
    if status in _REASONING_BLOCKING_STATUSES:
        raise ModelGatewayError(
            code="model_reasoning_unsupported",
            message="Model connection does not support configured reasoning hints.",
            details=[
                {
                    "field": _REASONING_CAPABILITY,
                    "issue": f"Capability is {status}",
                }
            ],
        )
    return ModelReasoningStrategySelection(
        strategy="enabled",
        reasoning_effort=reasoning_effort,
    )


def select_streaming_strategy(
    request: ModelExecutionRequest,
) -> ModelStreamingStrategySelection:
    if request.connection.streaming_policy == "forbid":
        return ModelStreamingStrategySelection(strategy="disabledByPolicy")
    return ModelStreamingStrategySelection(strategy="disabled")


def select_model_execution_strategies(
    request: ModelExecutionRequest,
    *,
    output_strategy: str,
    has_tools: bool,
    allow_parallel_tool_calls: bool,
) -> ModelExecutionStrategies:
    selected = ModelExecutionStrategies(
        output_strategy=output_strategy,
        tool_call_strategy="none" if not has_tools else ("parallel" if allow_parallel_tool_calls else "serialize"),
        parallel_tool_calls=allow_parallel_tool_calls if has_tools else False,
    )
    try:
        reasoning = select_reasoning_strategy(request)
    except ModelGatewayError as exc:
        raise exc.with_execution_context(
            usage=None,
            selected_strategies=selected,
            duration_ms=None,
        ) from exc
    streaming = select_streaming_strategy(request)
    return ModelExecutionStrategies(
        output_strategy=output_strategy,
        tool_call_strategy=selected.tool_call_strategy,
        parallel_tool_calls=selected.parallel_tool_calls,
        reasoning_strategy=reasoning.strategy,
        reasoning_effort=reasoning.reasoning_effort,
        streaming_strategy=streaming.strategy,
    )


def _capability_status(request: ModelExecutionRequest, key: str) -> str | None:
    capabilities = request.connection.capabilities or {}
    raw_state = capabilities.get(key)
    if not isinstance(raw_state, Mapping):
        return None
    raw_status = raw_state.get("status")
    return raw_status if isinstance(raw_status, str) else None


__all__ = [
    "ModelReasoningStrategySelection",
    "ModelStreamingStrategySelection",
    "select_model_execution_strategies",
    "select_reasoning_strategy",
    "select_streaming_strategy",
]
