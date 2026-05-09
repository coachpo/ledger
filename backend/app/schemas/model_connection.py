from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone

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

    path = parsed.path.rstrip("/")
    lower_path = path.lower()
    if lower_path.endswith("/v1/responses"):
        raise ValueError(
            "Base URL must point to the /v1 root; "
            + "set apiStyle to responses instead of using /v1/responses"
        )
    if lower_path.endswith("/v1/chat/completions"):
        raise ValueError(
            "Base URL must point to the /v1 root; "
            + "set apiStyle to chat_completions instead of using /v1/chat/completions"
        )
    if "/v1/" in lower_path:
        raise ValueError("Base URL must point to the /v1 root")
    if not path:
        path = "/v1"
    elif not lower_path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def normalize_model_connection_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_MODEL_CONNECTION_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


class ModelConnectionStatus(str, Enum):  # noqa: UP042
    ACTIVE = "active"
    ARCHIVED = "archived"


type ModelConnectionReasoningEffort = str


class ModelConnectionApiStyle(str, Enum):  # noqa: UP042
    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"


class ModelConnectionCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    base_url: str
    model_id: str = Field(min_length=1, max_length=200)
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default="medium",
        max_length=128,
    )
    api_style: ModelConnectionApiStyle = ModelConnectionApiStyle.RESPONSES
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
    base_url: str | None = None
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default=None,
        max_length=128,
    )
    api_style: ModelConnectionApiStyle | None = None
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

    @field_validator("timeout_seconds", "api_style", mode="before")
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
    status: ModelConnectionStatus
    name: str
    description: str
    base_url: str
    model_id: str
    reasoning_effort: ModelConnectionReasoningEffort | None = Field(
        default=None,
        max_length=128,
    )
    api_style: ModelConnectionApiStyle
    timeout_seconds: int = Field(ge=1)
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None

    @field_validator("last_tested_at")
    @classmethod
    def validate_last_tested_at(cls, value: datetime | None) -> datetime | None:
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


__all__ = [
    "ModelConnectionApiStyle",
    "ModelConnectionConnectionTestRead",
    "ModelConnectionCreate",
    "ModelConnectionListItemRead",
    "ModelConnectionListRead",
    "ModelConnectionRead",
    "ModelConnectionReasoningEffort",
    "ModelConnectionStatus",
    "ModelConnectionUpdate",
    "normalize_model_connection_key",
]
