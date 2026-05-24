from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.model_gateway_dto import (
    ModelCapabilityProbeOutcome,
    ModelCapabilityProbeRequest,
    ModelCapabilityProbeResult,
    ModelConnectionTestRequest,
    ModelConnectionTestResult,
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelExecutionStrategies,
    ModelExecutionUsage,
    ModelGatewayConnectionConfig,
    ModelGatewayError,
    ModelProtocolAdapter,
    ModelToolExecutor,
)
from app.services.model_gateway_openai import OpenAIProtocolAdapter
from app.services.model_gateway_output_validation import select_output_strategy
from app.services.model_gateway_policy_strategy import (
    select_reasoning_strategy,
    select_streaming_strategy,
)
from app.services.model_gateway_tool_strategy import select_tool_strategy

_SUPPORTED_OPENAI_COMPATIBLE_API_STYLES = frozenset({"responses", "chat_completions"})


class ModelExecutionGateway:
    def __init__(
        self,
        protocol_adapter: ModelProtocolAdapter | None = None,
        *,
        client_factory: type[Any] | None = None,
    ) -> None:
        if protocol_adapter is not None:
            self._protocol_adapter = protocol_adapter
        elif client_factory is not None:
            self._protocol_adapter = OpenAIProtocolAdapter(client_factory=client_factory)
        else:
            self._protocol_adapter = OpenAIProtocolAdapter()

    def invoke(
        self,
        request: ModelExecutionRequest,
        *,
        tool_executor: ModelToolExecutor,
    ) -> ModelExecutionResult:
        connection = request.connection
        if connection.connection_kind == "deterministic_smoke":
            return ModelExecutionResult(
                output=self._deterministic_output_for_schema(request.output_schema.schema),
                usage=ModelExecutionUsage(total_tokens=1),
                selected_strategies=self._selected_strategies_for_request(request),
                duration_ms=0,
            )
        if connection.api_key is None:
            raise ModelGatewayError(
                code="agent_model_connection_api_key_missing",
                message=(
                    f"Agent {request.agent_key!r} cannot run because model connection "
                    f"{connection.name!r} is missing an API key"
                ),
            )
        if connection.api_style not in _SUPPORTED_OPENAI_COMPATIBLE_API_STYLES:
            raise self._unsupported_api_style_error(
                connection=connection,
                agent_key=request.agent_key,
            )
        return self._protocol_adapter.invoke(request, tool_executor=tool_executor)

    @staticmethod
    def _selected_strategies_for_request(
        request: ModelExecutionRequest,
    ) -> ModelExecutionStrategies:
        output_strategy = select_output_strategy(request)
        tool_strategy = select_tool_strategy(request)
        reasoning_strategy = select_reasoning_strategy(request)
        streaming_strategy = select_streaming_strategy(request)
        return ModelExecutionStrategies(
            output_strategy=output_strategy.strategy,
            tool_call_strategy=(
                "none"
                if not tool_strategy.has_tools
                else ("parallel" if tool_strategy.allow_parallel_tool_calls else "serialize")
            ),
            parallel_tool_calls=(
                tool_strategy.allow_parallel_tool_calls if tool_strategy.has_tools else False
            ),
            reasoning_strategy=reasoning_strategy.strategy,
            reasoning_effort=reasoning_strategy.reasoning_effort,
            streaming_strategy=streaming_strategy.strategy,
        )

    def test_connection(
        self,
        request: ModelConnectionTestRequest,
    ) -> ModelConnectionTestResult:
        connection = request.connection
        if connection.connection_kind == "deterministic_smoke":
            return ModelConnectionTestResult(
                ok=True,
                message="Deterministic smoke test succeeded.",
            )
        if connection.api_key is None:
            return ModelConnectionTestResult(
                ok=False,
                message="API key is not configured.",
            )
        if connection.api_style not in _SUPPORTED_OPENAI_COMPATIBLE_API_STYLES:
            message = (
                "Model connection validation failed: unsupported API style "
                f"{connection.api_style!r}."
            )
            return ModelConnectionTestResult(
                ok=False,
                message=self._normalize_message(message, api_key=connection.api_key),
            )
        return self._protocol_adapter.test_connection(request)

    def probe_capabilities(
        self,
        request: ModelCapabilityProbeRequest,
    ) -> ModelCapabilityProbeResult:
        connection = request.connection
        if connection.connection_kind == "deterministic_smoke":
            return self._deterministic_probe_capabilities(request)
        if connection.api_key is None:
            return self._capability_probe_result(
                request.capability_keys,
                status="unsupported",
                detail="API key is not configured.",
            )
        if connection.api_style not in _SUPPORTED_OPENAI_COMPATIBLE_API_STYLES:
            message = (
                "Model connection validation failed: unsupported API style "
                f"{connection.api_style!r}."
            )
            return self._capability_probe_result(
                request.capability_keys,
                status="unsupported",
                detail=self._normalize_message(message, api_key=connection.api_key),
            )
        return self._protocol_adapter.probe_capabilities(request)

    @classmethod
    def _deterministic_probe_capabilities(
        cls,
        request: ModelCapabilityProbeRequest,
    ) -> ModelCapabilityProbeResult:
        return ModelCapabilityProbeResult(
            capabilities={
                capability_key: cls._deterministic_probe_outcome(
                    request.connection,
                    capability_key,
                )
                for capability_key in request.capability_keys
            }
        )

    @staticmethod
    def _deterministic_probe_outcome(
        connection: ModelGatewayConnectionConfig,
        capability_key: str,
    ) -> ModelCapabilityProbeOutcome:
        if capability_key == "text_generation":
            return ModelCapabilityProbeOutcome(
                status="supported",
                detail="Deterministic smoke generation is available.",
            )
        if capability_key == "chat_completions":
            status = "supported" if connection.api_style == "chat_completions" else "notApplicable"
            return ModelCapabilityProbeOutcome(
                status=status,
                detail="Capability follows the selected protocol profile.",
            )
        if capability_key == "responses_api":
            status = "supported" if connection.api_style == "responses" else "notApplicable"
            return ModelCapabilityProbeOutcome(
                status=status,
                detail="Capability follows the selected protocol profile.",
            )
        return ModelCapabilityProbeOutcome(
            status="unknown",
            detail="Deterministic smoke connections do not call a provider for this probe.",
        )

    @staticmethod
    def _capability_probe_result(
        capability_keys: tuple[str, ...],
        *,
        status: str,
        detail: str,
    ) -> ModelCapabilityProbeResult:
        return ModelCapabilityProbeResult(
            capabilities={
                capability_key: ModelCapabilityProbeOutcome(status=status, detail=detail)
                for capability_key in capability_keys
            }
        )

    @staticmethod
    def _unsupported_api_style_error(
        *,
        connection: ModelGatewayConnectionConfig,
        agent_key: str,
    ) -> ModelGatewayError:
        return ModelGatewayError(
            code="agent_model_connection_api_style_unsupported",
            message=(
                f"Agent {agent_key!r} cannot run because model connection "
                f"{connection.name!r} uses unsupported API style {connection.api_style!r}."
            ),
        )

    @classmethod
    def _deterministic_output_for_schema(cls, schema: Mapping[str, Any]) -> Any:
        return cls._deterministic_json_value(schema, name="output", root_schema=schema)

    @classmethod
    def _deterministic_json_value(
        cls,
        schema: Mapping[str, Any],
        *,
        name: str,
        root_schema: Mapping[str, Any],
    ) -> Any:
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            defs = root_schema.get("$defs")
            target = defs.get(ref.removeprefix("#/$defs/")) if isinstance(defs, Mapping) else None
            if isinstance(target, Mapping):
                return cls._deterministic_json_value(target, name=name, root_schema=root_schema)
        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties")
            if not isinstance(properties, Mapping):
                return {}
            required = schema.get("required")
            required_names = required if isinstance(required, list) else list(properties.keys())
            return {
                str(key): cls._deterministic_json_value(
                    value if isinstance(value, Mapping) else {},
                    name=str(key),
                    root_schema=root_schema,
                )
                for key, value in properties.items()
                if key in required_names
            }
        if schema_type == "array":
            items = schema.get("items")
            item_schema = items if isinstance(items, Mapping) else {}
            return [cls._deterministic_json_value(item_schema, name=name, root_schema=root_schema)]
        if schema_type in {"integer", "number"}:
            return 1
        if schema_type == "boolean":
            return True
        if isinstance(schema.get("properties"), Mapping):
            return {}
        return f"deterministic {name}"

    @staticmethod
    def _normalize_message(message: str, *, api_key: str | None) -> str:
        normalized = " ".join(str(message).split()).strip()
        if api_key:
            normalized = normalized.replace(api_key, "[REDACTED]")
        if len(normalized) > 500:
            return f"{normalized[:497]}..."
        return normalized or "Model gateway request failed."


__all__ = ["ModelExecutionGateway"]
