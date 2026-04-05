from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.core.formatting import normalize_currency
from app.schemas.common import CamelModel

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PortfolioCreate(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    description: str | None = None
    base_currency: str = Field(min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG_RE.match(normalized):
            raise ValueError(
                "Slug must start with a letter and contain only"
                " lowercase letters, digits, and underscores"
            )
        return normalized

    @field_validator("base_currency")
    @classmethod
    def validate_base_currency(cls, value: str) -> str:
        normalized = normalize_currency(value)
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Base currency must be a 3-letter ISO code")
        return normalized


class PortfolioUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> PortfolioUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name is required")
        return self


class PortfolioRead(CamelModel):
    id: int
    name: str
    slug: str
    description: str | None
    base_currency: str
    position_count: int
    balance_count: int
    created_at: datetime
    updated_at: datetime
