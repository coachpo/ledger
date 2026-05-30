from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone, to_camel

_STABLE_MODEL_CONNECTION_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_optional_secret(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("API key cannot be empty")
    return normalized


def _normalize_reasoning_effort(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Reasoning effort must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Reasoning effort is required")
    return normalized


def _normalize_base_url(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Base URL")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a valid http or https URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL must not include query parameters or fragments")

    return normalized


def build_model_connection_openai_base_url(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Base URL")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a valid http or https URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL must not include query parameters or fragments")

    path = parsed.path.rstrip("/")
    runtime_path = path if path.lower().endswith("/v1") else (f"{path}/v1" if path else "/v1")
    return urlunsplit((parsed.scheme, parsed.netloc, runtime_path, "", ""))


def normalize_model_connection_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_MODEL_CONNECTION_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


type ModelConnectionReasoningEffort = str


class ModelConnectionProtocolProfile(str, Enum):  # noqa: UP042
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    OPENAI_RESPONSES = "openai_responses"


class ModelConnectionCapabilityStatus(str, Enum):  # noqa: UP042
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "notApplicable"


class ModelConnectionOutputStrategyPolicy(str, Enum):  # noqa: UP042
    REQUIRE_STRICT_SCHEMA = "require_strict_schema"
    PREFER_STRICT_SCHEMA = "prefer_strict_schema"
    ALLOW_JSON_OBJECT_VALIDATION = "allow_json_object_validation"
    ALLOW_PLAIN_TEXT = "allow_plain_text"


class ModelConnectionParallelToolCallsPolicy(str, Enum):  # noqa: UP042
    ALLOW = "allow"
    SERIALIZE = "serialize"
    FORBID = "forbid"


class ModelConnectionReasoningPolicy(str, Enum):  # noqa: UP042
    ALLOW = "allow"
    FORBID = "forbid"


class ModelConnectionStreamingPolicy(str, Enum):  # noqa: UP042
    ALLOW = "allow"
    FORBID = "forbid"


_PROTOCOL_PROFILE_TO_API_STYLE = {
    ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value: "chat_completions",
    ModelConnectionProtocolProfile.OPENAI_RESPONSES.value: "responses",
}
_API_STYLE_TO_PROTOCOL_PROFILE = {
    api_style: protocol_profile
    for protocol_profile, api_style in _PROTOCOL_PROFILE_TO_API_STYLE.items()
}


def api_style_for_model_connection_protocol_profile(value: object) -> str:
    profile = value.value if isinstance(value, ModelConnectionProtocolProfile) else str(value)
    try:
        return _PROTOCOL_PROFILE_TO_API_STYLE[profile]
    except KeyError as exc:
        raise ValueError("Protocol profile is invalid") from exc


def protocol_profile_for_legacy_api_style(value: object) -> str:
    api_style = str(value).strip()
    return _API_STYLE_TO_PROTOCOL_PROFILE.get(
        api_style,
        ModelConnectionProtocolProfile.OPENAI_RESPONSES.value,
    )


class ModelConnectionCapabilityState(CamelModel):
    status: ModelConnectionCapabilityStatus = ModelConnectionCapabilityStatus.UNKNOWN
    detail: str | None = Field(default=None, max_length=1000)
    last_probed_at: datetime | None = None

    @field_validator("detail", mode="before")
    @classmethod
    def validate_detail(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("last_probed_at")
    @classmethod
    def validate_last_probed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class ModelConnectionCapabilities(CamelModel):
    text_generation: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    chat_completions: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    responses_api: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    streaming: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    native_tool_calls: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    parallel_tool_calls: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    json_object_output: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    strict_json_schema_output: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    reasoning_hints: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    usage_reporting: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )
    system_messages: ModelConnectionCapabilityState = Field(
        default_factory=ModelConnectionCapabilityState,
    )


_MODEL_CONNECTION_CAPABILITY_FIELD_NAMES = tuple(ModelConnectionCapabilities.model_fields)
_MODEL_CONNECTION_CAPABILITY_FIELD_NAME_SET = set(_MODEL_CONNECTION_CAPABILITY_FIELD_NAMES)
_MODEL_CONNECTION_CAPABILITY_PUBLIC_NAME_BY_FIELD = {
    field_name: to_camel(field_name) for field_name in _MODEL_CONNECTION_CAPABILITY_FIELD_NAMES
}
_MODEL_CONNECTION_CAPABILITY_FIELD_BY_PUBLIC_NAME = {
    public_name: field_name
    for field_name, public_name in _MODEL_CONNECTION_CAPABILITY_PUBLIC_NAME_BY_FIELD.items()
}


def normalize_model_connection_capability_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Capability key")
    candidate = _MODEL_CONNECTION_CAPABILITY_FIELD_BY_PUBLIC_NAME.get(normalized, normalized)
    if candidate not in _MODEL_CONNECTION_CAPABILITY_FIELD_NAME_SET:
        supported = ", ".join(_MODEL_CONNECTION_CAPABILITY_PUBLIC_NAME_BY_FIELD.values())
        raise ValueError(f"Capability key must be one of: {supported}")
    return candidate


def _capability_state(status: ModelConnectionCapabilityStatus) -> ModelConnectionCapabilityState:
    return ModelConnectionCapabilityState(status=status)


def default_model_connection_capabilities(
    protocol_profile: object = ModelConnectionProtocolProfile.OPENAI_RESPONSES,
) -> ModelConnectionCapabilities:
    profile = (
        protocol_profile.value
        if isinstance(protocol_profile, ModelConnectionProtocolProfile)
        else str(protocol_profile)
    )
    chat_status = ModelConnectionCapabilityStatus.UNKNOWN
    responses_status = ModelConnectionCapabilityStatus.UNKNOWN
    if profile == ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value:
        chat_status = ModelConnectionCapabilityStatus.SUPPORTED
        responses_status = ModelConnectionCapabilityStatus.NOT_APPLICABLE
    elif profile == ModelConnectionProtocolProfile.OPENAI_RESPONSES.value:
        chat_status = ModelConnectionCapabilityStatus.NOT_APPLICABLE
        responses_status = ModelConnectionCapabilityStatus.SUPPORTED

    return ModelConnectionCapabilities(
        text_generation=_capability_state(ModelConnectionCapabilityStatus.SUPPORTED),
        chat_completions=_capability_state(chat_status),
        responses_api=_capability_state(responses_status),
    )


def dump_model_connection_capabilities(
    capabilities: ModelConnectionCapabilities,
) -> dict[str, object]:
    return capabilities.model_dump(mode="json", by_alias=True)


class ModelConnectionCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    protocol_profile: ModelConnectionProtocolProfile = (
        ModelConnectionProtocolProfile.OPENAI_RESPONSES
    )
    base_url: str
    model_id: str = Field(min_length=1, max_length=200)
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default="medium",
        max_length=128,
    )
    timeout_seconds: int = Field(default=60, ge=1)
    api_key: str | None = None

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return normalize_model_connection_key(value)

    @field_validator("name", "model_id", mode="before")
    @classmethod
    def validate_required_text_fields(cls, value: object, info: ValidationInfo) -> str:
        field_name = (info.field_name or "field").replace("_", " ").title()
        return _normalize_required_text(value, field_name=field_name)

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, value: object) -> str:
        return _normalize_base_url(value)

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def validate_reasoning_effort(cls, value: object) -> str | None:
        return _normalize_reasoning_effort(value)

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, value: object) -> str | None:
        return _normalize_optional_secret(value)


class ModelConnectionUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    protocol_profile: ModelConnectionProtocolProfile | None = None
    base_url: str | None = None
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default=None,
        max_length=128,
    )
    timeout_seconds: int | None = Field(default=None, ge=1)
    api_key: str | None = None

    @field_validator("name", "model_id", mode="before")
    @classmethod
    def validate_optional_required_text_fields(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> str:
        field_name = (info.field_name or "field").replace("_", " ").title()
        return _normalize_required_text(value, field_name=field_name)

    @field_validator("description", mode="before")
    @classmethod
    def validate_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_optional_base_url(cls, value: object) -> str:
        return _normalize_base_url(value)

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def validate_reasoning_effort(cls, value: object) -> str | None:
        return _normalize_reasoning_effort(value)

    @field_validator("timeout_seconds", "protocol_profile", mode="before")
    @classmethod
    def reject_null_scalar_updates(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            field_name = info.field_name or "field"
            raise ValueError(f"{field_name} cannot be null")
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_optional_api_key(cls, value: object) -> str | None:
        return _normalize_optional_secret(value)

    @model_validator(mode="after")
    def validate_payload(self) -> ModelConnectionUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "api_key" in self.model_fields_set and self.api_key is None:
            raise ValueError("apiKey cannot be null")
        return self


class ModelConnectionListItemRead(CamelModel):
    id: int
    key: str
    name: str
    description: str
    protocol_profile: ModelConnectionProtocolProfile
    base_url: str
    model_id: str
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default=None,
        max_length=128,
    )
    capabilities: ModelConnectionCapabilities
    output_strategy_policy: ModelConnectionOutputStrategyPolicy
    parallel_tool_calls_policy: ModelConnectionParallelToolCallsPolicy
    reasoning_policy: ModelConnectionReasoningPolicy
    streaming_policy: ModelConnectionStreamingPolicy
    last_probed_at: datetime | None = None
    probe_cache_ttl_seconds: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1)
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None

    @field_validator("last_tested_at", "last_probed_at")
    @classmethod
    def validate_optional_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class ModelConnectionRead(ModelConnectionListItemRead):
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class ModelConnectionListRead(CamelModel):
    items: list[ModelConnectionListItemRead]


class ModelConnectionConnectionTestRead(CamelModel):
    model_connection_id: int
    ok: bool
    message: str
    last_tested_at: datetime

    @field_validator("last_tested_at")
    @classmethod
    def validate_test_timestamp(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class ModelConnectionCapabilityProbeRequest(CamelModel):
    capability_keys: list[str] = Field(default_factory=list)
    refresh: bool = False

    @field_validator("capability_keys", mode="before")
    @classmethod
    def normalize_capability_keys(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Capability keys must be an array of strings")
        normalized_keys = [normalize_model_connection_capability_key(item) for item in value]
        if len(set(normalized_keys)) != len(normalized_keys):
            raise ValueError("Capability keys must be unique")
        return normalized_keys


class ModelConnectionCapabilityProbeRead(CamelModel):
    model_connection_id: int
    requested_capability_keys: list[str] = Field(default_factory=list)
    cached: bool
    last_probed_at: datetime
    probe_cache_ttl_seconds: int = Field(ge=1)
    capabilities: ModelConnectionCapabilities

    @field_validator("last_probed_at")
    @classmethod
    def validate_last_probed_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class ModelConnectionCompatibilityResolution(CamelModel):
    key: str
    name: str
    protocol_profile: ModelConnectionProtocolProfile
    base_url: str
    model_id: str
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default=None,
        max_length=128,
    )
    capabilities: ModelConnectionCapabilities = Field(default_factory=ModelConnectionCapabilities)
    output_strategy_policy: ModelConnectionOutputStrategyPolicy = (
        ModelConnectionOutputStrategyPolicy.PREFER_STRICT_SCHEMA
    )
    parallel_tool_calls_policy: ModelConnectionParallelToolCallsPolicy = (
        ModelConnectionParallelToolCallsPolicy.SERIALIZE
    )
    reasoning_policy: ModelConnectionReasoningPolicy = ModelConnectionReasoningPolicy.ALLOW
    streaming_policy: ModelConnectionStreamingPolicy = ModelConnectionStreamingPolicy.ALLOW
    probe_cache_ttl_seconds: int = Field(default=900, ge=1)
    api_style: str
    timeout_seconds: int = Field(ge=1)
    has_api_key: bool

    @field_validator("key", "name", "base_url", "model_id", "api_style", mode="before")
    @classmethod
    def validate_required_runtime_text_fields(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> str:
        field_name = (info.field_name or "field").replace("_", " ").title()
        return _normalize_required_text(value, field_name=field_name)

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def validate_runtime_reasoning_effort(cls, value: object) -> str | None:
        return _normalize_reasoning_effort(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_effective_runtime_profile(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        name = normalized.get("name")
        if (not isinstance(name, str) or not name.strip()) and normalized.get("key") is not None:
            normalized["name"] = normalized["key"]
        if "timeoutSeconds" not in normalized and "timeout_seconds" not in normalized:
            normalized["timeoutSeconds"] = 60
        if "hasApiKey" not in normalized and "has_api_key" not in normalized:
            normalized["hasApiKey"] = False
        protocol_profile = normalized.get("protocolProfile") or normalized.get("protocol_profile")
        api_style = normalized.get("apiStyle") or normalized.get("api_style")
        if protocol_profile is None:
            if api_style == "chat_completions":
                protocol_profile = ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value
            elif api_style == "responses":
                protocol_profile = ModelConnectionProtocolProfile.OPENAI_RESPONSES.value
            else:
                raise ValueError(
                    "Model connection snapshot must include protocolProfile or apiStyle"
                )
        try:
            protocol_profile_enum = ModelConnectionProtocolProfile(str(protocol_profile))
        except ValueError as exc:
            raise ValueError("Model connection snapshot protocolProfile is invalid") from exc
        normalized["protocolProfile"] = protocol_profile_enum.value
        expected_api_style = (
            "chat_completions"
            if protocol_profile_enum == ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS
            else "responses"
        )
        if api_style is None:
            normalized["apiStyle"] = expected_api_style
        else:
            normalized_api_style = str(api_style).strip()
            if normalized_api_style != expected_api_style:
                raise ValueError(
                    "Model connection snapshot apiStyle does not match protocolProfile"
                )
            normalized["apiStyle"] = normalized_api_style
        if "capabilities" not in normalized or normalized.get("capabilities") is None:
            normalized["capabilities"] = default_model_connection_capabilities(
                protocol_profile_enum
            )
        if "outputStrategyPolicy" not in normalized and "output_strategy_policy" not in normalized:
            normalized["outputStrategyPolicy"] = (
                ModelConnectionOutputStrategyPolicy.PREFER_STRICT_SCHEMA.value
            )
        if (
            "parallelToolCallsPolicy" not in normalized
            and "parallel_tool_calls_policy" not in normalized
        ):
            normalized["parallelToolCallsPolicy"] = (
                ModelConnectionParallelToolCallsPolicy.SERIALIZE.value
            )
        if "reasoningPolicy" not in normalized and "reasoning_policy" not in normalized:
            normalized["reasoningPolicy"] = ModelConnectionReasoningPolicy.ALLOW.value
        if "streamingPolicy" not in normalized and "streaming_policy" not in normalized:
            normalized["streamingPolicy"] = ModelConnectionStreamingPolicy.ALLOW.value
        if "probeCacheTtlSeconds" not in normalized and "probe_cache_ttl_seconds" not in normalized:
            normalized["probeCacheTtlSeconds"] = 900
        return normalized


__all__ = [
    "ModelConnectionCapabilities",
    "ModelConnectionCapabilityState",
    "ModelConnectionCapabilityStatus",
    "ModelConnectionCapabilityProbeRead",
    "ModelConnectionCapabilityProbeRequest",
    "ModelConnectionConnectionTestRead",
    "ModelConnectionCompatibilityResolution",
    "ModelConnectionCreate",
    "ModelConnectionListItemRead",
    "ModelConnectionListRead",
    "ModelConnectionOutputStrategyPolicy",
    "ModelConnectionParallelToolCallsPolicy",
    "ModelConnectionProtocolProfile",
    "ModelConnectionRead",
    "ModelConnectionReasoningEffort",
    "ModelConnectionReasoningPolicy",
    "ModelConnectionStreamingPolicy",
    "ModelConnectionUpdate",
    "api_style_for_model_connection_protocol_profile",
    "build_model_connection_openai_base_url",
    "default_model_connection_capabilities",
    "dump_model_connection_capabilities",
    "normalize_model_connection_capability_key",
    "normalize_model_connection_key",
    "protocol_profile_for_legacy_api_style",
]
