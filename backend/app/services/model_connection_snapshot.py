from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from app.models.model_connection import ModelConnection
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionOutputStrategyPolicy,
    ModelConnectionParallelToolCallsPolicy,
    ModelConnectionProtocolProfile,
    ModelConnectionReasoningPolicy,
    ModelConnectionStreamingPolicy,
    default_model_connection_capabilities,
)

MODEL_CONNECTION_RUNTIME_SNAPSHOT_KEYS = (
    "protocol_profile",
    "base_url",
    "model_id",
    "reasoning_effort",
    "capabilities",
    "output_strategy_policy",
    "parallel_tool_calls_policy",
    "reasoning_policy",
    "streaming_policy",
    "probe_cache_ttl_seconds",
    "api_style",
    "timeout_seconds",
)


@dataclass(frozen=True)
class ModelConnectionRuntimeSnapshot:
    protocol_profile: str
    base_url: str
    model_id: str
    reasoning_effort: str | None
    capabilities: dict[str, object]
    output_strategy_policy: str
    parallel_tool_calls_policy: str
    reasoning_policy: str
    streaming_policy: str
    probe_cache_ttl_seconds: int
    api_style: str
    timeout_seconds: int


def build_model_connection_runtime_snapshot(
    connection: ModelConnection,
) -> dict[str, object]:
    capabilities = _dump_capabilities(
        _load_capabilities(connection.protocol_profile, connection.capabilities)
    )
    return {
        "protocol_profile": connection.protocol_profile,
        "base_url": connection.base_url,
        "model_id": connection.model_id,
        "reasoning_effort": connection.reasoning_effort,
        "capabilities": capabilities,
        "output_strategy_policy": connection.output_strategy_policy,
        "parallel_tool_calls_policy": connection.parallel_tool_calls_policy,
        "reasoning_policy": connection.reasoning_policy,
        "streaming_policy": connection.streaming_policy,
        "probe_cache_ttl_seconds": connection.probe_cache_ttl_seconds,
        "api_style": connection.api_style,
        "timeout_seconds": connection.timeout_seconds,
    }


def parse_model_connection_runtime_snapshot(
    raw_snapshot: object,
) -> ModelConnectionRuntimeSnapshot:
    if not isinstance(raw_snapshot, Mapping):
        raise ValueError("Model connection snapshot must be an object")
    snapshot = _snapshot_mapping(cast(Mapping[object, object], raw_snapshot))
    protocol_profile = _parse_protocol_profile(snapshot)
    base_url = _required_snapshot_text(snapshot, "base_url", "baseUrl")
    model_id = _required_snapshot_text(snapshot, "model_id", "modelId")
    reasoning_effort = _snapshot_reasoning_effort(
        _get(snapshot, "reasoning_effort", "reasoningEffort")
    )
    capabilities = _dump_capabilities(_parse_capabilities(snapshot, protocol_profile))
    output_strategy_policy = _parse_policy(
        snapshot,
        field_name="output_strategy_policy",
        legacy_field_name="outputStrategyPolicy",
        enum_type=ModelConnectionOutputStrategyPolicy,
        default_value=ModelConnectionOutputStrategyPolicy.PREFER_STRICT_SCHEMA.value,
    )
    parallel_tool_calls_policy = _parse_policy(
        snapshot,
        field_name="parallel_tool_calls_policy",
        legacy_field_name="parallelToolCallsPolicy",
        enum_type=ModelConnectionParallelToolCallsPolicy,
        default_value=ModelConnectionParallelToolCallsPolicy.SERIALIZE.value,
    )
    reasoning_policy = _parse_policy(
        snapshot,
        field_name="reasoning_policy",
        legacy_field_name="reasoningPolicy",
        enum_type=ModelConnectionReasoningPolicy,
        default_value=ModelConnectionReasoningPolicy.ALLOW.value,
    )
    streaming_policy = _parse_policy(
        snapshot,
        field_name="streaming_policy",
        legacy_field_name="streamingPolicy",
        enum_type=ModelConnectionStreamingPolicy,
        default_value=ModelConnectionStreamingPolicy.ALLOW.value,
    )
    probe_cache_ttl_seconds = _positive_int(
        _get(snapshot, "probe_cache_ttl_seconds", "probeCacheTtlSeconds"),
        field_name="probe_cache_ttl_seconds",
        default_value=900,
    )
    api_style = _required_snapshot_text(snapshot, "api_style", "apiStyle")
    expected_api_style = _protocol_profile_to_api_style(protocol_profile)
    if api_style != expected_api_style:
        raise ValueError("Model connection snapshot api_style does not match protocol_profile")
    timeout_seconds = _positive_int(
        _get(snapshot, "timeout_seconds", "timeoutSeconds"),
        field_name="timeout_seconds",
        default_value=None,
    )

    return ModelConnectionRuntimeSnapshot(
        protocol_profile=protocol_profile,
        base_url=base_url,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        capabilities=capabilities,
        output_strategy_policy=output_strategy_policy,
        parallel_tool_calls_policy=parallel_tool_calls_policy,
        reasoning_policy=reasoning_policy,
        streaming_policy=streaming_policy,
        probe_cache_ttl_seconds=probe_cache_ttl_seconds,
        api_style=api_style,
        timeout_seconds=timeout_seconds,
    )


def snapshot_to_json(
    snapshot: ModelConnectionRuntimeSnapshot,
) -> dict[str, object]:
    return {
        "protocol_profile": snapshot.protocol_profile,
        "base_url": snapshot.base_url,
        "model_id": snapshot.model_id,
        "reasoning_effort": snapshot.reasoning_effort,
        "capabilities": snapshot.capabilities,
        "output_strategy_policy": snapshot.output_strategy_policy,
        "parallel_tool_calls_policy": snapshot.parallel_tool_calls_policy,
        "reasoning_policy": snapshot.reasoning_policy,
        "streaming_policy": snapshot.streaming_policy,
        "probe_cache_ttl_seconds": snapshot.probe_cache_ttl_seconds,
        "api_style": snapshot.api_style,
        "timeout_seconds": snapshot.timeout_seconds,
    }


def _snapshot_mapping(raw_snapshot: Mapping[object, object]) -> Mapping[str, object]:
    if not all(isinstance(key, str) for key in raw_snapshot):
        raise ValueError("Model connection snapshot keys must be strings")
    return cast(Mapping[str, object], raw_snapshot)


def _get(snapshot: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in snapshot:
            return snapshot[key]
    return None


def _required_snapshot_text(
    snapshot: Mapping[str, object],
    *keys: str,
) -> str:
    value = _get(snapshot, *keys)
    if not isinstance(value, str) or not value.strip():
        field_name = keys[0] if keys else "field"
        raise ValueError(f"Model connection snapshot {field_name} must be a non-empty string")
    return value.strip()


def _snapshot_reasoning_effort(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Model connection snapshot reasoning_effort must be a string or null")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Model connection snapshot reasoning_effort must be a non-empty string")
    if len(normalized) > 128:
        raise ValueError(
            "Model connection snapshot reasoning_effort must be at most 128 characters"
        )
    return normalized


def _parse_protocol_profile(snapshot: Mapping[str, object]) -> str:
    value = _get(snapshot, "protocol_profile", "protocolProfile")
    if value is None:
        api_style = _get(snapshot, "api_style", "apiStyle")
        if api_style == "chat_completions":
            value = ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value
        elif api_style == "responses":
            value = ModelConnectionProtocolProfile.OPENAI_RESPONSES.value
        else:
            raise ValueError("Model connection snapshot must include protocol_profile or api_style")
    try:
        return ModelConnectionProtocolProfile(str(value)).value
    except ValueError as exc:
        raise ValueError("Model connection snapshot protocol_profile is invalid") from exc


def _protocol_profile_to_api_style(protocol_profile: str) -> str:
    if protocol_profile == ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value:
        return "chat_completions"
    return "responses"


def _load_capabilities(
    protocol_profile: str,
    raw_capabilities: object,
) -> ModelConnectionCapabilities:
    if raw_capabilities is None:
        return default_model_connection_capabilities(protocol_profile)
    if not isinstance(raw_capabilities, Mapping):
        raise ValueError("Model connection snapshot capabilities must be an object")
    try:
        return ModelConnectionCapabilities.model_validate(raw_capabilities)
    except ValidationError as exc:
        raise ValueError("Model connection snapshot capabilities are invalid") from exc


def _parse_capabilities(
    snapshot: Mapping[str, object],
    protocol_profile: str,
) -> ModelConnectionCapabilities:
    return _load_capabilities(protocol_profile, _get(snapshot, "capabilities"))


def _dump_capabilities(capabilities: ModelConnectionCapabilities) -> dict[str, object]:
    return cast(dict[str, object], capabilities.model_dump(mode="json", by_alias=True))


def _parse_policy(
    snapshot: Mapping[str, object],
    *,
    field_name: str,
    legacy_field_name: str,
    enum_type: type[Any],
    default_value: str,
) -> str:
    value = _get(snapshot, field_name, legacy_field_name)
    if value is None:
        value = default_value
    try:
        return cast(str, enum_type(str(value)).value)
    except ValueError as exc:
        raise ValueError(f"Model connection snapshot {field_name} is invalid") from exc


def _positive_int(
    value: object,
    *,
    field_name: str,
    default_value: int | None,
) -> int:
    if value is None:
        if default_value is None:
            raise ValueError(f"Model connection snapshot {field_name} is required")
        value = default_value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Model connection snapshot {field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"Model connection snapshot {field_name} must be positive")
    return int(value)


__all__ = [
    "MODEL_CONNECTION_RUNTIME_SNAPSHOT_KEYS",
    "ModelConnectionRuntimeSnapshot",
    "build_model_connection_runtime_snapshot",
    "parse_model_connection_runtime_snapshot",
    "snapshot_to_json",
]
