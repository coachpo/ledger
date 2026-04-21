from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_MCP_SERVER_KEY_RE = r"^[a-z][a-z0-9_-]{0,119}$"


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
            "Key must start with a letter and use only lowercase letters, "
            "numbers, underscores, and hyphens"
        )
    return normalized


def _normalize_string_mapping(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    normalized_mapping: dict[str, str] = {}
    for raw_key, raw_value in value.items():
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

    normalized_args: list[str] = []
    for index, entry in enumerate(value):
        normalized_entry = str(entry).strip() if entry is not None else ""
        if not normalized_entry:
            raise ValueError(f"args[{index}] must be a non-empty string")
        normalized_args.append(normalized_entry)

    if not normalized_args:
        raise ValueError("args must contain at least one item")
    return normalized_args


class McpServerStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class McpServerTransport(str, Enum):  # noqa: UP042
    STDIO = "stdio"
    HTTP_SSE = "http-sse"


class McpServerConfigBase(CamelModel):
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


class McpServerStdioConfig(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    enabled: bool = True
    transport: Literal[McpServerTransport.STDIO] = McpServerTransport.STDIO
    command: str = Field(min_length=1)
    args: list[str] = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("command", mode="before")
    @classmethod
    def validate_command(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="command")

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> list[str]:
        return _normalize_args(value)

    @field_validator("env", mode="before")
    @classmethod
    def validate_env(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="env")


class McpServerHttpSseConfig(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    enabled: bool = True
    transport: Literal[McpServerTransport.HTTP_SSE] = McpServerTransport.HTTP_SSE
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="url")

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: object) -> dict[str, str]:
        return _normalize_string_mapping(value, field_name="headers")


McpServerConfig = Annotated[
    Union[McpServerStdioConfig, McpServerHttpSseConfig],
    Field(discriminator="transport"),
]


class McpServerConfigEnvelope(CamelModel):
    mcp_servers: dict[str, McpServerConfig] = Field(min_length=1, max_length=1)

    @field_validator("mcp_servers", mode="before")
    @classmethod
    def validate_mcp_servers(cls, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("mcpServers must be an object")
        normalized: dict[str, object] = {}
        for raw_key, raw_config in value.items():
            normalized_key = _normalize_mcp_server_key(raw_key)
            normalized[normalized_key] = raw_config
        return normalized

    @model_validator(mode="after")
    def validate_single_entry(self) -> McpServerConfigEnvelope:
        if len(self.mcp_servers) != 1:
            raise ValueError("mcpServers must contain exactly one server")
        return self

    @property
    def server_key(self) -> str:
        return next(iter(self.mcp_servers))

    @property
    def server_config(self) -> McpServerConfig:
        return self.mcp_servers[self.server_key]


class McpServerDraftCreate(McpServerConfigEnvelope):
    pass


class McpServerDraftUpdate(McpServerConfigEnvelope):
    pass


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


class McpServerRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: McpServerStatus
    config: McpServerConfigEnvelope
    created_at: datetime
    updated_at: datetime

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
    "McpServerConfig",
    "McpServerConfigEnvelope",
    "McpServerConnectionTestRead",
    "McpServerDraftCreate",
    "McpServerDraftUpdate",
    "McpServerHttpSseConfig",
    "McpServerListItemRead",
    "McpServerListRead",
    "McpServerRead",
    "McpServerStatus",
    "McpServerStdioConfig",
    "McpServerTransport",
]
