from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import AliasPath, Field, field_validator, model_validator

from app.schemas.common import CamelModel

_STABLE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


class OrchestrationRoleCreate(CamelModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    enabled: bool = True

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _STABLE_IDENTIFIER_RE.fullmatch(normalized) is None:
            raise ValueError(
                "Key must start with a letter and use only lowercase letters, numbers, "
                "and underscores"
            )
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("system_prompt")
    @classmethod
    def normalize_system_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("System prompt is required")
        return normalized


class OrchestrationRoleUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("system_prompt")
    @classmethod
    def normalize_system_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("System prompt is required")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> OrchestrationRoleUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class OrchestrationRoleRead(CamelModel):
    id: int
    key: str
    name: str
    description: str | None
    system_prompt: str
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class OrchestrationCharacterCreate(CamelModel):
    handle: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    role_id: int
    prompt_append: str | None = None
    enabled: bool = True

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _STABLE_IDENTIFIER_RE.fullmatch(normalized) is None:
            raise ValueError(
                "Handle must start with a letter and use only lowercase letters, numbers, "
                "and underscores"
            )
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized

    @field_validator("description", "prompt_append")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class OrchestrationCharacterUpdate(CamelModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    role_id: int | None = None
    prompt_append: str | None = None
    enabled: bool | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized

    @field_validator("description", "prompt_append")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_payload(self) -> OrchestrationCharacterUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "handle" in self.model_fields_set:
            raise ValueError("Handle is immutable")
        return self


class OrchestrationCharacterRead(CamelModel):
    id: int
    handle: str
    display_name: str
    description: str | None
    role_id: int
    role_key: str = Field(validation_alias=AliasPath("role", "key"))
    prompt_append: str | None
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class MentionCatalogItem(CamelModel):
    handle: str
    canonical_target_id: str
    kind: Literal["builtin", "character"]
    display_name: str
    description: str | None
    role_key: str | None = None


class MentionCatalogRead(CamelModel):
    targets: list[MentionCatalogItem]
