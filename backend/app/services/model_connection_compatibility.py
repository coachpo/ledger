from __future__ import annotations

from pydantic import ValidationError

from app.models.model_connection import ModelConnection
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionCompatibilityResolution,
    api_style_for_model_connection_protocol_profile,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
)
from app.services.execution_plan import PackageResolvedModelBinding
from app.services.model_gateway_dto import ModelGatewayConnectionConfig


class CompatibilityResolutionService:
    @staticmethod
    def _get_api_key(connection: ModelConnection) -> str | None:
        payload = connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
        raw_api_key = payload.get("apiKey")
        if raw_api_key is None:
            return None
        normalized = str(raw_api_key).strip()
        return normalized or None

    @staticmethod
    def _capabilities(connection: ModelConnection) -> ModelConnectionCapabilities:
        try:
            return ModelConnectionCapabilities.model_validate(connection.capabilities)
        except ValidationError:
            return default_model_connection_capabilities(connection.protocol_profile)

    def resolve_connection(
        self, connection: ModelConnection
    ) -> ModelConnectionCompatibilityResolution:
        return ModelConnectionCompatibilityResolution.model_validate(
            {
                "key": connection.key,
                "name": connection.name,
                "protocolProfile": connection.protocol_profile,
                "baseUrl": connection.base_url,
                "modelId": connection.model_id,
                "reasoningEffort": connection.reasoning_effort,
                "capabilities": self._capabilities(connection),
                "outputStrategyPolicy": connection.output_strategy_policy,
                "parallelToolCallsPolicy": connection.parallel_tool_calls_policy,
                "reasoningPolicy": connection.reasoning_policy,
                "streamingPolicy": connection.streaming_policy,
                "probeCacheTtlSeconds": connection.probe_cache_ttl_seconds,
                "apiStyle": api_style_for_model_connection_protocol_profile(
                    connection.protocol_profile
                ),
                "timeoutSeconds": connection.timeout_seconds,
                "hasApiKey": self._get_api_key(connection) is not None,
            }
        )

    def to_gateway_connection_config(
        self,
        connection: ModelConnection,
        *,
        resolution: ModelConnectionCompatibilityResolution | None = None,
    ) -> ModelGatewayConnectionConfig:
        resolved = resolution or self.resolve_connection(connection)
        return ModelGatewayConnectionConfig(
            id=connection.id,
            name=resolved.name,
            base_url=resolved.base_url,
            model_id=resolved.model_id,
            reasoning_effort=resolved.reasoning_effort,
            api_style=resolved.api_style,
            timeout_seconds=resolved.timeout_seconds,
            api_key=self._get_api_key(connection),
            capabilities=dump_model_connection_capabilities(resolved.capabilities),
            output_strategy_policy=resolved.output_strategy_policy.value,
            parallel_tool_calls_policy=resolved.parallel_tool_calls_policy.value,
            reasoning_policy=resolved.reasoning_policy.value,
            streaming_policy=resolved.streaming_policy.value,
        )

    def to_gateway_connection_config_from_package_binding(
        self,
        binding: PackageResolvedModelBinding,
        *,
        live_connection: ModelConnection,
    ) -> ModelGatewayConnectionConfig:
        return ModelGatewayConnectionConfig(
            id=live_connection.id,
            name=binding.name,
            base_url=binding.base_url,
            model_id=binding.model_id,
            reasoning_effort=binding.reasoning_effort,
            api_style=binding.api_style,
            timeout_seconds=binding.timeout_seconds,
            api_key=self._get_api_key(live_connection),
            capabilities=binding.capabilities,
            output_strategy_policy=binding.output_strategy_policy,
            parallel_tool_calls_policy=binding.parallel_tool_calls_policy,
            reasoning_policy=binding.reasoning_policy,
            streaming_policy=binding.streaming_policy,
        )

    @staticmethod
    def resolve_package_model_binding(
        binding: PackageResolvedModelBinding,
    ) -> ModelConnectionCompatibilityResolution:
        return ModelConnectionCompatibilityResolution.model_validate(
            {
                "key": binding.key,
                "name": binding.name,
                "protocolProfile": binding.protocol_profile,
                "baseUrl": binding.base_url,
                "modelId": binding.model_id,
                "reasoningEffort": binding.reasoning_effort,
                "capabilities": binding.capabilities,
                "outputStrategyPolicy": binding.output_strategy_policy,
                "parallelToolCallsPolicy": binding.parallel_tool_calls_policy,
                "reasoningPolicy": binding.reasoning_policy,
                "streamingPolicy": binding.streaming_policy,
                "probeCacheTtlSeconds": binding.probe_cache_ttl_seconds,
                "apiStyle": binding.api_style,
                "timeoutSeconds": binding.timeout_seconds,
                "hasApiKey": binding.has_api_key,
            }
        )

    @staticmethod
    def to_package_resolved_model_binding(
        resolution: ModelConnectionCompatibilityResolution,
    ) -> PackageResolvedModelBinding:
        return PackageResolvedModelBinding(
            key=resolution.key,
            name=resolution.name,
            protocol_profile=resolution.protocol_profile.value,
            base_url=resolution.base_url,
            model_id=resolution.model_id,
            reasoning_effort=resolution.reasoning_effort,
            capabilities=dump_model_connection_capabilities(resolution.capabilities),
            output_strategy_policy=resolution.output_strategy_policy.value,
            parallel_tool_calls_policy=resolution.parallel_tool_calls_policy.value,
            reasoning_policy=resolution.reasoning_policy.value,
            streaming_policy=resolution.streaming_policy.value,
            probe_cache_ttl_seconds=resolution.probe_cache_ttl_seconds,
            api_style=resolution.api_style,
            timeout_seconds=resolution.timeout_seconds,
            has_api_key=resolution.has_api_key,
        )


__all__ = ["CompatibilityResolutionService"]
