from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_SKILL_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"
_SERVER_DECLARED_TOOL_KEY_RE = r"^[a-z][a-z0-9_]{0,119}(?:\.[a-z][a-z0-9_]{0,119})+$"


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


def _normalize_skill_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_SKILL_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _normalize_tool_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Tool").lower()
    if re.fullmatch(_SERVER_DECLARED_TOOL_KEY_RE, normalized) is None:
        raise ValueError("Tool must use dot-separated lowercase identifiers")
    return normalized


class SkillStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class SkillToolDefinitionWrite(CamelModel):
    tool: str = Field(min_length=1, max_length=200)

    @field_validator("tool", mode="before")
    @classmethod
    def validate_tool(cls, value: object) -> str:
        return _normalize_tool_key(value)


class SkillToolDefinitionRead(SkillToolDefinitionWrite):
    display_name: str
    description: str


class SkillDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    tool_definitions: list[SkillToolDefinitionWrite] = Field(min_length=1)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_skill_key(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""


class SkillDraftUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    tool_definitions: list[SkillToolDefinitionWrite] | None = None

    @field_validator("tool_definitions", mode="before")
    @classmethod
    def reject_null_tool_definitions(cls, value: object) -> object:
        if value is None:
            raise ValueError("toolDefinitions must be an array")
        return value

    @field_validator("name", "description", mode="before")
    @classmethod
    def validate_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_payload(self) -> SkillDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class SkillRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: SkillStatus
    name: str
    description: str
    tool_definitions: list[SkillToolDefinitionRead]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class SkillListRead(CamelModel):
    items: list[SkillRead]


__all__ = [
    "SkillDraftCreate",
    "SkillDraftUpdate",
    "SkillListRead",
    "SkillRead",
    "SkillStatus",
    "SkillToolDefinitionRead",
    "SkillToolDefinitionWrite",
]
