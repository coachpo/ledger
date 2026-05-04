from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator

from app.schemas.agent_manifest import AgentManifestDiagnostic
from app.schemas.capability import CapabilityRead
from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.mcp_server import McpClientBoundaryRead, McpServerStatus, McpServerTransport
from app.schemas.model_connection import ModelConnectionListItemRead, ModelConnectionReasoningEffort
from app.schemas.output_schema import OutputSchemaRead

_STABLE_AGENT_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"
_STABLE_MCP_SERVER_KEY_RE = r"^[a-z][a-z0-9_-]{0,119}$"
AGENT_MANIFEST_SOURCE_MAX_LENGTH = 262_144


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


def _normalize_agent_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_AGENT_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _validate_manifest_source(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("manifestSource must be a string")
    if not value.strip():
        raise ValueError("manifestSource is required")
    if len(value) > AGENT_MANIFEST_SOURCE_MAX_LENGTH:
        raise ValueError(
            f"manifestSource must be at most {AGENT_MANIFEST_SOURCE_MAX_LENGTH} characters"
        )
    return value


def _normalize_mcp_server_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="MCP server key").lower()
    if re.fullmatch(_STABLE_MCP_SERVER_KEY_RE, normalized) is None:
        raise ValueError(
            "MCP server key must start with a letter and use only lowercase letters, "
            "numbers, underscores, and hyphens"
        )
    return normalized


class AgentStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class AgentCapabilityRefWrite(CamelModel):
    capability_key: str = Field(min_length=1, max_length=120)
    capability_version: int | None = Field(default=None, ge=1)

    @field_validator("capability_key", mode="before")
    @classmethod
    def validate_capability_key(cls, value: object) -> str:
        return _normalize_agent_key(value)


class AgentMcpServerRefWrite(CamelModel):
    mcp_server_key: str = Field(min_length=1, max_length=120)
    mcp_server_version: int = Field(ge=1)

    @field_validator("mcp_server_key", mode="before")
    @classmethod
    def validate_mcp_server_key(cls, value: object) -> str:
        return _normalize_mcp_server_key(value)


class AgentVersionBase(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    model_connection_id: int = Field(ge=1)
    system_prompt: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema_key: str = Field(min_length=1, max_length=120)
    output_schema_version: int | None = Field(default=None, ge=1)
    capabilities: list[AgentCapabilityRefWrite] = Field(default_factory=list)
    mcp_servers: list[AgentMcpServerRefWrite] = Field(default_factory=list)
    budget_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @field_validator("name", "system_prompt", mode="before")
    @classmethod
    def validate_required_text_fields(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> str:
        field_name = (info.field_name or "field").replace("_", " ").title()
        return _normalize_required_text(value, field_name=field_name)

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("output_schema_key", mode="before")
    @classmethod
    def validate_output_schema_key(cls, value: object) -> str:
        return _normalize_agent_key(value)


class AgentCreate(AgentVersionBase):
    key: str = Field(min_length=1, max_length=120)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_agent_key(value)


class AgentUpdate(AgentVersionBase):
    pass


class AgentManifestWriteRequest(CamelModel):
    manifest_source: str

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str:
        return _validate_manifest_source(value)


class AgentManifestValidationRequest(AgentManifestWriteRequest):
    pass


class AgentManifestValidationMetadata(CamelModel):
    api_version: str
    key: str
    name: str
    description: str


class AgentManifestValidationRead(CamelModel):
    diagnostics: list[AgentManifestDiagnostic]
    metadata: AgentManifestValidationMetadata | None = None
    compiled_payload: dict[str, Any] | None = None
    run_input_schema: dict[str, Any] | None = None


class AgentMcpServerRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: McpServerStatus
    name: str
    description: str
    transport: McpServerTransport
    enabled: bool
    boundary: McpClientBoundaryRead


class AgentModelConnectionSnapshotRead(CamelModel):
    base_url: str
    model_id: str
    organization: str | None = None
    project: str | None = None
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(default=None, max_length=128)
    api_style: str
    timeout_seconds: int = Field(ge=1)


class AgentRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: AgentStatus
    name: str
    description: str
    manifest_api_version: str
    manifest_source: str
    manifest_hash: str
    compiler_version: str
    model_connection_id: int = Field(ge=1)
    model_connection: ModelConnectionListItemRead
    model_connection_snapshot: AgentModelConnectionSnapshotRead
    system_prompt: str
    input_schema: dict[str, Any]
    output_schema: OutputSchemaRead
    capabilities: list[CapabilityRead]
    mcp_servers: list[AgentMcpServerRead]
    budget_usd: Decimal
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class AgentListRead(CamelModel):
    items: list[AgentRead]


__all__ = [
    "AGENT_MANIFEST_SOURCE_MAX_LENGTH",
    "AgentCapabilityRefWrite",
    "AgentCreate",
    "AgentListRead",
    "AgentManifestValidationMetadata",
    "AgentManifestValidationRead",
    "AgentManifestValidationRequest",
    "AgentManifestWriteRequest",
    "AgentModelConnectionSnapshotRead",
    "AgentMcpServerRead",
    "AgentMcpServerRefWrite",
    "AgentRead",
    "AgentStatus",
    "AgentUpdate",
]
