from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, ensure_timezone


class ExtensionContributionRead(CamelModel):
    extension_key: str
    category: str
    summary: str
    surface: str
    owner_extension_key: str
    dependencies: list[str] = Field(default_factory=list)


class ExtensionToggleRequest(CamelModel):
    enabled: bool
    disabled_reason: str | None = Field(default=None, max_length=500)

    @field_validator("disabled_reason", mode="before")
    @classmethod
    def normalize_disabled_reason(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("disabledReason must be a string")
        normalized = value.strip()
        return normalized or None


class ExtensionRead(CamelModel):
    key: str
    label: str
    enabled: bool
    default_enabled: bool
    phase: str
    versioning_rule: str
    contribution_categories: list[str]
    dependencies: list[str] = Field(default_factory=list)
    contributions: list[ExtensionContributionRead]
    state_version: int = Field(ge=1)
    enabled_at: datetime | None = None
    disabled_at: datetime | None = None
    disabled_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("enabled_at", "disabled_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class ExtensionListRead(CamelModel):
    items: list[ExtensionRead]


__all__ = [
    "ExtensionContributionRead",
    "ExtensionListRead",
    "ExtensionRead",
    "ExtensionToggleRequest",
]
