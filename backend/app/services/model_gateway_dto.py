from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.failure_taxonomy import (
    ToolFailureClassification,
    classification_for_error_code,
    runtime_failure_metadata,
)


def _metadata_without_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ModelGatewayConnectionConfig:
    id: int
    name: str
    base_url: str
    model_id: str
    reasoning_effort: str | None
    api_style: str
    timeout_seconds: int
    api_key: str | None
    capabilities: Mapping[str, Any] | None = None
    output_strategy_policy: str = "prefer_strict_schema"
    parallel_tool_calls_policy: str = "serialize"
    reasoning_policy: str = "allow"
    streaming_policy: str = "allow"


@dataclass(frozen=True, slots=True)
class ModelOutputSchema:
    name: str
    schema: Mapping[str, Any]
    runtime_model: type[BaseModel] | None = None


ModelToolDeclaration = SignalDeckToolDeclaration


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    tool_name: str
    arguments_json: str
    call_id: str

    @property
    def name(self) -> str:
        return self.tool_name


@dataclass(frozen=True, slots=True)
class ModelToolResult:
    call_id: str
    output: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ModelExecutionUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw: Mapping[str, Any] | None = None

    @property
    def total_tokens_or_zero(self) -> int:
        if self.total_tokens is not None:
            return int(self.total_tokens)
        return int(self.input_tokens or 0) + int(self.output_tokens or 0)

    def to_metadata(self) -> dict[str, Any]:
        return _metadata_without_none(
            {
                "inputTokens": self.input_tokens,
                "outputTokens": self.output_tokens,
                "totalTokens": self.total_tokens_or_zero,
            }
        )


@dataclass(frozen=True, slots=True)
class ModelExecutionStrategies:
    output_strategy: str | None = None
    tool_call_strategy: str | None = None
    parallel_tool_calls: bool | None = None
    reasoning_strategy: str | None = None
    reasoning_effort: str | None = None
    streaming_strategy: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return _metadata_without_none(
            {
                "outputStrategy": self.output_strategy,
                "toolCallStrategy": self.tool_call_strategy,
                "parallelToolCalls": self.parallel_tool_calls,
                "reasoningStrategy": self.reasoning_strategy,
                "reasoningEffort": self.reasoning_effort,
                "streamingStrategy": self.streaming_strategy,
            }
        )


@dataclass(frozen=True, slots=True)
class ModelExecutionRequest:
    connection: ModelGatewayConnectionConfig
    agent_key: str
    instructions: str
    input_text: str
    output_schema: ModelOutputSchema
    tools: tuple[ModelToolDeclaration, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelExecutionResult:
    output: Any
    usage: ModelExecutionUsage = field(default_factory=ModelExecutionUsage)
    selected_strategies: ModelExecutionStrategies = field(default_factory=ModelExecutionStrategies)
    duration_ms: int | None = None
    tool_retry_metadata: Mapping[str, Any] | None = None

    def runtime_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        usage = self.usage.to_metadata()
        if usage:
            metadata["usage"] = usage
        selected_strategies = self.selected_strategies.to_metadata()
        if selected_strategies:
            metadata["selectedStrategies"] = selected_strategies
        if self.tool_retry_metadata is not None:
            metadata["toolCallRetries"] = dict(self.tool_retry_metadata)
        return metadata


@dataclass(frozen=True, slots=True)
class ModelConnectionTestRequest:
    connection: ModelGatewayConnectionConfig
    instructions: str
    input_text: str


@dataclass(frozen=True, slots=True)
class ModelConnectionTestResult:
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class ModelCapabilityProbeRequest:
    connection: ModelGatewayConnectionConfig
    capability_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelCapabilityProbeOutcome:
    status: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilityProbeResult:
    capabilities: Mapping[str, ModelCapabilityProbeOutcome]


class ModelGatewayError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Sequence[Mapping[str, Any]] | None = None,
        usage: ModelExecutionUsage | None = None,
        selected_strategies: ModelExecutionStrategies | None = None,
        duration_ms: int | None = None,
        failure_classification: ToolFailureClassification | None = None,
        tool_retry_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = [dict(detail) for detail in details or ()]
        self.usage = usage
        self.selected_strategies = selected_strategies
        self.duration_ms = duration_ms
        self.tool_retry_metadata = dict(tool_retry_metadata) if tool_retry_metadata else None
        self.failure_classification: ToolFailureClassification = (
            failure_classification or classification_for_error_code(code)
        )

    def with_execution_context(
        self,
        *,
        usage: ModelExecutionUsage | None,
        selected_strategies: ModelExecutionStrategies | None,
        duration_ms: int | None,
    ) -> ModelGatewayError:
        if self.usage is None:
            self.usage = usage
        if self.selected_strategies is None:
            self.selected_strategies = selected_strategies
        if self.duration_ms is None:
            self.duration_ms = duration_ms
        return self

    @property
    def failure_class(self) -> str:
        return self.failure_classification.failure_class.value

    @property
    def retryable(self) -> bool:
        return self.failure_classification.retryable

    def runtime_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = runtime_failure_metadata(self.failure_classification)
        usage = self.usage.to_metadata() if self.usage is not None else {}
        if usage:
            metadata["usage"] = usage
        selected_strategies = (
            self.selected_strategies.to_metadata() if self.selected_strategies is not None else {}
        )
        if selected_strategies:
            metadata["selectedStrategies"] = selected_strategies
        if self.tool_retry_metadata is not None:
            metadata["toolCallRetries"] = dict(self.tool_retry_metadata)
        return metadata


class ModelToolExecutor(Protocol):
    def __call__(self, tool_call: ModelToolCall) -> ModelToolResult: ...


class ModelProtocolAdapter(Protocol):
    def invoke(
        self,
        request: ModelExecutionRequest,
        *,
        tool_executor: ModelToolExecutor,
    ) -> ModelExecutionResult: ...

    def test_connection(
        self,
        request: ModelConnectionTestRequest,
    ) -> ModelConnectionTestResult: ...

    def probe_capabilities(
        self,
        request: ModelCapabilityProbeRequest,
    ) -> ModelCapabilityProbeResult: ...


__all__ = [
    "ModelCapabilityProbeOutcome",
    "ModelCapabilityProbeRequest",
    "ModelCapabilityProbeResult",
    "ModelConnectionTestRequest",
    "ModelConnectionTestResult",
    "ModelExecutionRequest",
    "ModelExecutionResult",
    "ModelExecutionStrategies",
    "ModelExecutionUsage",
    "ModelGatewayConnectionConfig",
    "ModelGatewayError",
    "ModelOutputSchema",
    "ModelProtocolAdapter",
    "ModelToolCall",
    "ModelToolDeclaration",
    "ModelToolExecutor",
    "ModelToolResult",
]
