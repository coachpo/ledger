from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import cast

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_MCP_SERVER_KEY_RE = r"^[a-z][a-z0-9_-]{0,119}$"
_MCP_OPENAI_FUNCTION_NAME_RE = r"^[A-Za-z_][A-Za-z0-9_]{0,127}$"
_MCP_SCHEMA_HASH_RE = r"^sha256:[a-f0-9]{64}$"
_MCP_FROZEN_TOOL_KEY_RE = r"^[A-Za-z0-9_.:@-]{1,256}$"


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
    if not normalized:
        return None
    return normalized


def _normalize_mcp_server_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_MCP_SERVER_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, "
            + "underscores, and hyphens"
        )
    return normalized


def _normalize_string_mapping(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    raw_mapping = cast(dict[object, object], value)
    normalized_mapping: dict[str, str] = {}
    for raw_key, raw_value in raw_mapping.items():
        normalized_key = str(raw_key).strip()
        if not normalized_key:
            raise ValueError(f"{field_name} keys must be non-empty strings")

        normalized_value = str(raw_value).strip() if raw_value is not None else ""
        if not normalized_value:
            raise ValueError(f"{field_name}.{normalized_key} values must be non-empty strings")

        normalized_mapping[normalized_key] = normalized_value
    return normalized_mapping


def _normalize_args(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("args must be an array of strings")

    raw_args = cast(list[object], value)
    normalized_args: list[str] = []
    for index, entry in enumerate(raw_args):
        normalized_entry = str(entry).strip() if entry is not None else ""
        if not normalized_entry:
            raise ValueError(f"args[{index}] must be a non-empty string")
        normalized_args.append(normalized_entry)

    if not normalized_args:
        raise ValueError("args must contain at least one item")
    return normalized_args


def _validate_openai_function_name(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="OpenAI function name")
    if re.fullmatch(_MCP_OPENAI_FUNCTION_NAME_RE, normalized) is None:
        raise ValueError(
            "OpenAI function name must start with a letter or underscore and use only "
            + "ASCII letters, numbers, and underscores"
        )
    return normalized


def _validate_schema_hash(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Schema hash")
    if re.fullmatch(_MCP_SCHEMA_HASH_RE, normalized) is None:
        raise ValueError("Schema hash must be sha256: followed by 64 lowercase hex characters")
    return normalized


def _validate_frozen_tool_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Frozen tool key")
    if re.fullmatch(_MCP_FROZEN_TOOL_KEY_RE, normalized) is None:
        raise ValueError(
            "Frozen tool key must use only letters, numbers, underscores, hyphens, dots, "
            + "colons, and @"
        )
    return normalized


def _normalize_reverse_mapping(value: object) -> dict[str, str]:
    return _normalize_string_mapping(value, field_name="reverseMapping")


def _validate_strict_json_schema(value: object) -> dict[str, object]:
    schema = _schema_mapping(value, field_name="Strict schema")
    _validate_strict_json_schema_node(schema, field_name="strictSchema", require_object_root=True)
    return schema


def _schema_mapping(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    raw_schema = cast(dict[object, object], value)
    if not all(isinstance(key, str) and key.strip() for key in raw_schema):
        raise ValueError(f"{field_name} keys must be non-empty strings")
    return cast(dict[str, object], dict(raw_schema))


def _validate_strict_json_schema_node(
    schema: object,
    *,
    field_name: str,
    require_object_root: bool = False,
) -> None:
    schema_mapping = _schema_mapping(schema, field_name=field_name)
    if "$ref" in schema_mapping:
        raise ValueError(f"{field_name} cannot contain $ref")

    raw_type = schema_mapping.get("type")
    type_values = _schema_type_values(raw_type, field_name=field_name)
    if require_object_root and "object" not in type_values:
        raise ValueError("Strict schema root type must be object")

    unsupported_keys = sorted(set(schema_mapping) - _allowed_strict_schema_keys(type_values))
    if unsupported_keys:
        joined_keys = ", ".join(unsupported_keys)
        raise ValueError(f"{field_name} contains unsupported keywords: {joined_keys}")

    if "object" in type_values:
        _validate_strict_schema_object(schema_mapping, field_name=field_name)
    if "array" in type_values:
        items = schema_mapping.get("items")
        if items is None:
            raise ValueError(f"{field_name}.items is required for arrays")
        _validate_strict_json_schema_node(items, field_name=f"{field_name}.items")


def _schema_type_values(raw_type: object, *, field_name: str) -> set[str]:
    values: set[str]
    if isinstance(raw_type, str):
        values = {raw_type}
    elif isinstance(raw_type, list) and raw_type:
        values = set()
        raw_type_values = cast(list[object], raw_type)
        for entry in raw_type_values:
            if not isinstance(entry, str):
                raise ValueError(f"{field_name}.type entries must be strings")
            values.add(entry)
    else:
        raise ValueError(f"{field_name}.type is required")

    supported_values = {"object", "array", "string", "number", "integer", "boolean", "null"}
    unsupported_values = sorted(values - supported_values)
    if unsupported_values:
        joined_values = ", ".join(unsupported_values)
        raise ValueError(f"{field_name}.type contains unsupported values: {joined_values}")
    return values


def _allowed_strict_schema_keys(type_values: set[str]) -> set[str]:
    allowed = {"type", "description", "enum", "const"}
    if "object" in type_values:
        allowed.update({"properties", "required", "additionalProperties"})
    if "array" in type_values:
        allowed.add("items")
    if type_values & {"string", "number", "integer"}:
        allowed.update({"minimum", "maximum", "minLength", "maxLength"})
    return allowed


def _validate_strict_schema_object(schema: dict[str, object], *, field_name: str) -> None:
    if schema.get("additionalProperties") is not False:
        raise ValueError(f"{field_name}.additionalProperties must be false")

    raw_properties = schema.get("properties", {})
    if not isinstance(raw_properties, dict):
        raise ValueError(f"{field_name}.properties must be an object")
    properties = cast(dict[object, object], raw_properties)
    if not all(isinstance(key, str) and key.strip() for key in properties):
        raise ValueError(f"{field_name}.properties keys must be non-empty strings")
    typed_properties = cast(dict[str, object], dict(properties))

    raw_required = schema.get("required", [])
    if not isinstance(raw_required, list):
        raise ValueError(f"{field_name}.required must be an array of strings")
    required = cast(list[object], raw_required)
    if not all(isinstance(entry, str) for entry in required):
        raise ValueError(f"{field_name}.required must be an array of strings")
    typed_required = cast(list[str], required)

    property_names = set(typed_properties)
    if set(typed_required) != property_names or len(typed_required) != len(property_names):
        raise ValueError(f"{field_name}.required must contain every property exactly once")

    for property_name, property_schema in typed_properties.items():
        _validate_strict_json_schema_node(
            property_schema,
            field_name=f"{field_name}.properties.{property_name}",
        )


class McpServerStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class McpServerTransport(str, Enum):  # noqa: UP042
    STDIO = "stdio"
    HTTP_SSE = "http-sse"


class McpServerBase(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    enabled: bool = True
    transport: McpServerTransport

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""


class McpServerCreate(McpServerBase):
    key: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_mcp_server_key(value)

    @field_validator("command", mode="before")
    @classmethod
    def validate_command(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> list[str]:
        if value is None:
            return []
        return _normalize_args(value)

    @field_validator("env", mode="before")
    @classmethod
    def validate_env(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="env")

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="headers")

    @model_validator(mode="after")
    def validate_transport_shape(self) -> McpServerCreate:
        if self.transport == McpServerTransport.STDIO:
            if not self.command:
                raise ValueError("command is required")
            if not self.args:
                raise ValueError("args must contain at least one item")
            self.url = None
            self.headers = {}
        elif self.transport == McpServerTransport.HTTP_SSE:
            if not self.url:
                raise ValueError("url is required")
            self.command = None
            self.args = []
            self.env = {}
        return self


class McpServerUpdate(McpServerBase):
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("command", mode="before")
    @classmethod
    def validate_command(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> list[str]:
        if value is None:
            return []
        return _normalize_args(value)

    @field_validator("env", mode="before")
    @classmethod
    def validate_env(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="env")

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="headers")

    @model_validator(mode="after")
    def validate_transport_shape(self) -> McpServerUpdate:
        if self.transport == McpServerTransport.STDIO:
            if not self.command:
                raise ValueError("command is required")
            if not self.args:
                raise ValueError("args must contain at least one item")
        elif self.transport == McpServerTransport.HTTP_SSE:
            if not self.url:
                raise ValueError("url is required")
        return self


class McpToolSnapshot(CamelModel):
    mcp_server_key: str = Field(min_length=1, max_length=120)
    mcp_server_version: int = Field(ge=1)
    frozen_tool_key: str = Field(min_length=1, max_length=256)
    original_tool_name: str = Field(min_length=1, max_length=128)
    openai_function_name: str = Field(min_length=1, max_length=128)
    schema_hash: str = Field(min_length=71, max_length=71)
    strict_schema: dict[str, object]
    reverse_mapping: dict[str, str]

    @field_validator("mcp_server_key", mode="before")
    @classmethod
    def validate_mcp_server_key(cls, value: object) -> str:
        return _normalize_mcp_server_key(value)

    @field_validator("frozen_tool_key", mode="before")
    @classmethod
    def validate_frozen_tool_key(cls, value: object) -> str:
        return _validate_frozen_tool_key(value)

    @field_validator("original_tool_name", mode="before")
    @classmethod
    def validate_original_tool_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Original MCP tool name")

    @field_validator("openai_function_name", mode="before")
    @classmethod
    def validate_openai_function_name(cls, value: object) -> str:
        return _validate_openai_function_name(value)

    @field_validator("schema_hash", mode="before")
    @classmethod
    def validate_schema_hash(cls, value: object) -> str:
        return _validate_schema_hash(value)

    @field_validator("strict_schema", mode="before")
    @classmethod
    def validate_strict_schema(cls, value: object) -> dict[str, object]:
        return _validate_strict_json_schema(value)

    @field_validator("reverse_mapping", mode="before")
    @classmethod
    def validate_reverse_mapping(cls, value: object) -> dict[str, str]:
        return _normalize_reverse_mapping(value)

    @model_validator(mode="after")
    def validate_snapshot_identity(self) -> McpToolSnapshot:
        expected_mapping = {self.openai_function_name: self.original_tool_name}
        if self.reverse_mapping != expected_mapping:
            raise ValueError("reverseMapping must map openaiFunctionName to originalToolName")
        if self.mcp_server_key not in self.frozen_tool_key:
            raise ValueError("frozenToolKey must include mcpServerKey")
        if self.openai_function_name not in self.frozen_tool_key:
            raise ValueError("frozenToolKey must include openaiFunctionName")
        return self


class McpToolSnapshotList(CamelModel):
    items: list[McpToolSnapshot]


class McpClientBoundaryRead(CamelModel):
    transport: McpServerTransport
    command: list[str] | None = None
    url: str | None = None
    header_names: list[str] = Field(default_factory=list)
    env_keys: list[str] = Field(default_factory=list)
    enabled: bool


class McpServerConnectionTestRead(CamelModel):
    server_id: int
    ok: bool
    message: str
    boundary: McpClientBoundaryRead


class McpServerRead(McpServerBase):
    id: int
    key: str
    version: int = Field(ge=1)
    status: McpServerStatus
    created_at: datetime
    updated_at: datetime
    command: list[str] | None = None
    url: str | None = None
    header_names: list[str] = Field(default_factory=list)
    env_keys: list[str] = Field(default_factory=list)
    tool_snapshots: list[McpToolSnapshot] = Field(default_factory=list)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class McpServerListItemRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: McpServerStatus
    name: str
    description: str
    transport: McpServerTransport
    enabled: bool


class McpServerListRead(CamelModel):
    items: list[McpServerListItemRead]


__all__ = [
    "McpClientBoundaryRead",
    "McpServerBase",
    "McpServerCreate",
    "McpServerConnectionTestRead",
    "McpServerListItemRead",
    "McpServerListRead",
    "McpServerRead",
    "McpServerStatus",
    "McpServerTransport",
    "McpServerUpdate",
    "McpToolSnapshot",
    "McpToolSnapshotList",
]
