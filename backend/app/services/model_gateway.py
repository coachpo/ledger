from __future__ import annotations

from typing import Any

from app.services.model_gateway_dto import (
    ModelCapabilityProbeOutcome,
    ModelCapabilityProbeRequest,
    ModelCapabilityProbeResult,
    ModelConnectionTestRequest,
    ModelConnectionTestResult,
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelGatewayConnectionConfig,
    ModelGatewayError,
    ModelToolExecutor,
)
from app.services.model_gateway_openai import OpenAIProtocolAdapter

_SUPPORTED_OPENAI_COMPATIBLE_API_STYLES = frozenset({"responses", "chat_completions"})


class ModelExecutionGateway:
    def __init__(
        self,
        protocol_adapter: OpenAIProtocolAdapter | None = None,
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

    def test_connection(
        self,
        request: ModelConnectionTestRequest,
    ) -> ModelConnectionTestResult:
        connection = request.connection
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

    @staticmethod
    def _normalize_message(message: str, *, api_key: str | None) -> str:
        normalized = " ".join(str(message).split()).strip()
        if api_key:
            normalized = normalized.replace(api_key, "[REDACTED]")
        if len(normalized) > 500:
            return f"{normalized[:497]}..."
        return normalized or "Model gateway request failed."


__all__ = ["ModelExecutionGateway"]
