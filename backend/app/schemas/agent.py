from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import Field, ValidationInfo, field_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.mcp_server import McpClientBoundaryRead, McpServerStatus, McpServerTransport
from app.schemas.output_schema import OutputSchemaRead
from app.schemas.skill import SkillRead

_STABLE_AGENT_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"


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


class AgentStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class AgentSkillRefWrite(CamelModel):
    skill_key: str = Field(min_length=1, max_length=120)
    skill_version: int | None = Field(default=None, ge=1)

    @field_validator("skill_key", mode="before")
    @classmethod
    def validate_skill_key(cls, value: object) -> str:
        return _normalize_agent_key(value)


class AgentMcpServerRefWrite(CamelModel):
    mcp_server_key: str = Field(min_length=1, max_length=120)
    mcp_server_version: int | None = Field(default=None, ge=1)

    @field_validator("mcp_server_key", mode="before")
    @classmethod
    def validate_mcp_server_key(cls, value: object) -> str:
        return _normalize_agent_key(value)


class AgentVersionBase(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema_key: str = Field(min_length=1, max_length=120)
    output_schema_version: int | None = Field(default=None, ge=1)
    skills: list[AgentSkillRefWrite] = Field(default_factory=list)
    mcp_servers: list[AgentMcpServerRefWrite] = Field(default_factory=list)
    temperature: float = 0.0
    max_tool_rounds: int = Field(default=1, ge=1)
    budget_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    streaming: bool = False

    @field_validator("name", "model", "system_prompt", mode="before")
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


class AgentRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: AgentStatus
    name: str
    description: str
    model: str
    system_prompt: str
    input_schema: dict[str, Any]
    output_schema: OutputSchemaRead
    skills: list[SkillRead]
    mcp_servers: list[AgentMcpServerRead]
    temperature: float
    max_tool_rounds: int
    budget_usd: Decimal
    streaming: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class AgentListRead(CamelModel):
    items: list[AgentRead]


class AgentTestPanelRequest(CamelModel):
    sample_input: dict[str, Any] = Field(default_factory=dict)


class AgentTestPanelRead(CamelModel):
    agent: AgentRead
    sample_input: dict[str, Any]


__all__ = [
    "AgentCreate",
    "AgentListRead",
    "AgentMcpServerRead",
    "AgentMcpServerRefWrite",
    "AgentRead",
    "AgentSkillRefWrite",
    "AgentStatus",
    "AgentTestPanelRead",
    "AgentTestPanelRequest",
    "AgentUpdate",
]
