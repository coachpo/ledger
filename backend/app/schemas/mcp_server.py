from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_MCP_SERVER_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"


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
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


class McpServerStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class McpServerTransport(str, Enum):  # noqa: UP042
    STDIO = "stdio"
    HTTP_SSE = "http-sse"


class McpServerDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    transport: McpServerTransport
    command: str | None = None
    url: str | None = None
    auth: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_mcp_server_key(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", "command", "url", mode="before")
    @classmethod
    def validate_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class McpServerDraftUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    transport: McpServerTransport | None = None
    command: str | None = None
    url: str | None = None
    auth: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("auth", mode="before")
    @classmethod
    def reject_null_auth(cls, value: object) -> object:
        if value is None:
            raise ValueError("auth must be an object")
        return value

    @field_validator("name", "description", "command", "url", mode="before")
    @classmethod
    def validate_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_payload(self) -> McpServerDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


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
    name: str
    description: str
    transport: McpServerTransport
    command: str | None = None
    url: str | None = None
    auth: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class McpServerListRead(CamelModel):
    items: list[McpServerRead]


__all__ = [
    "McpClientBoundaryRead",
    "McpServerConnectionTestRead",
    "McpServerDraftCreate",
    "McpServerDraftUpdate",
    "McpServerListRead",
    "McpServerRead",
    "McpServerStatus",
    "McpServerTransport",
]
