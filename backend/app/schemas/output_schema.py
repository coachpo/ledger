from __future__ import annotations

# ruff: noqa: UP007
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union, cast

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_OUTPUT_SCHEMA_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"

JsonPrimitive = Union[str, int, float, bool]  # noqa: UP007
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


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


def _normalize_output_schema_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_OUTPUT_SCHEMA_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _normalize_builder_name(value: object, *, field_name: str) -> str:
    return _normalize_required_text(value, field_name=field_name)


def _primitive_kind(value: JsonPrimitive) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    return "number"


class OutputSchemaStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class OutputSchemaKind(str, Enum):  # noqa: UP042
    STANDALONE = "standalone"
    SHARED = "shared"


class OutputSchemaBuilderBase(CamelModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    default_value: JsonValue | None = Field(default=None, alias="defaultValue")

    @field_validator("title", "description", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @model_serializer(mode="wrap")
    def serialize_without_absent_default_value(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        serialized = cast(dict[str, object], handler(self))
        if "default_value" not in self.model_fields_set:
            serialized.pop("defaultValue", None)
            serialized.pop("default_value", None)
        return serialized


class OutputSchemaBuilderString(OutputSchemaBuilderBase):
    kind: Literal["string"] = "string"


class OutputSchemaBuilderInteger(OutputSchemaBuilderBase):
    kind: Literal["integer"] = "integer"


class OutputSchemaBuilderNumber(OutputSchemaBuilderBase):
    kind: Literal["number"] = "number"


class OutputSchemaBuilderBoolean(OutputSchemaBuilderBase):
    kind: Literal["boolean"] = "boolean"


class OutputSchemaBuilderEnum(OutputSchemaBuilderBase):
    kind: Literal["enum"] = "enum"
    values: list[JsonPrimitive] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: list[JsonPrimitive]) -> list[JsonPrimitive]:
        if len({_primitive_kind(item) for item in value}) != 1:
            raise ValueError("Enum values must all use the same primitive type")
        return value


class OutputSchemaBuilderLiteral(OutputSchemaBuilderBase):
    kind: Literal["literal"] = "literal"
    value: JsonPrimitive


class OutputSchemaBuilderField(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    required: bool = True
    definition: OutputSchemaBuilderNode = Field(alias="schema")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_builder_name(value, field_name="Field name")


class OutputSchemaBuilderObject(OutputSchemaBuilderBase):
    kind: Literal["object"] = "object"
    fields: list[OutputSchemaBuilderField] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def validate_unique_field_names(
        cls, value: list[OutputSchemaBuilderField]
    ) -> list[OutputSchemaBuilderField]:
        seen_names: set[str] = set()
        for field in value:
            if field.name in seen_names:
                raise ValueError(f"Duplicate field name: {field.name}")
            seen_names.add(field.name)
        return value


class OutputSchemaBuilderArray(OutputSchemaBuilderBase):
    kind: Literal["array"] = "array"
    items: OutputSchemaBuilderNode


class OutputSchemaBuilderRef(OutputSchemaBuilderBase):
    kind: Literal["ref"] = "ref"
    schema_key: str = Field(min_length=1, max_length=120)
    schema_version: int | None = Field(default=None, ge=1)

    @field_validator("schema_key", mode="before")
    @classmethod
    def validate_schema_key(cls, value: object) -> str:
        return _normalize_output_schema_key(value)


class OutputSchemaBuilderDiscriminatedUnion(OutputSchemaBuilderBase):
    kind: Literal["discriminated_union"] = "discriminated_union"
    discriminator: str = Field(min_length=1, max_length=120)
    variants: list[OutputSchemaBuilderNode] = Field(min_length=2)

    @field_validator("discriminator", mode="before")
    @classmethod
    def validate_discriminator(cls, value: object) -> str:
        return _normalize_builder_name(value, field_name="Discriminator")


OutputSchemaBuilderNode = Annotated[  # noqa: UP007
    Union[
        OutputSchemaBuilderString,
        OutputSchemaBuilderInteger,
        OutputSchemaBuilderNumber,
        OutputSchemaBuilderBoolean,
        OutputSchemaBuilderEnum,
        OutputSchemaBuilderLiteral,
        OutputSchemaBuilderObject,
        OutputSchemaBuilderArray,
        OutputSchemaBuilderRef,
        OutputSchemaBuilderDiscriminatedUnion,
    ],  # noqa: UP007
    Field(discriminator="kind"),
]

OutputSchemaBuilderField.model_rebuild()
OutputSchemaBuilderArray.model_rebuild()
OutputSchemaBuilderDiscriminatedUnion.model_rebuild()


class OutputSchemaDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    kind: OutputSchemaKind = OutputSchemaKind.STANDALONE
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    builder: OutputSchemaBuilderNode | None = None
    json_schema: dict[str, Any] | None = None

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_output_schema_key(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @model_validator(mode="after")
    def validate_schema_views(self) -> OutputSchemaDraftCreate:
        if self.builder is None and self.json_schema is None:
            raise ValueError("Either builder or jsonSchema must be provided")
        return self


class OutputSchemaDraftUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    builder: OutputSchemaBuilderNode | None = None
    json_schema: dict[str, Any] | None = None

    @field_validator("builder", "json_schema", mode="before")
    @classmethod
    def reject_null_schema_views(cls, value: object) -> object:
        if value is None:
            raise ValueError("Schema view fields cannot be null")
        return value

    @field_validator("name", "description", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_payload(self) -> OutputSchemaDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class OutputSchemaRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: OutputSchemaStatus
    kind: OutputSchemaKind
    name: str
    description: str
    json_schema: dict[str, Any]
    builder: OutputSchemaBuilderNode
    registry_refs: list[str]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class OutputSchemaListRead(CamelModel):
    items: list[OutputSchemaRead]


OutputSchemaRead.model_rebuild()
OutputSchemaDraftCreate.model_rebuild()
OutputSchemaDraftUpdate.model_rebuild()


__all__ = [
    "JsonPrimitive",
    "JsonValue",
    "OutputSchemaBuilderArray",
    "OutputSchemaBuilderBoolean",
    "OutputSchemaBuilderDiscriminatedUnion",
    "OutputSchemaBuilderEnum",
    "OutputSchemaBuilderField",
    "OutputSchemaBuilderInteger",
    "OutputSchemaBuilderLiteral",
    "OutputSchemaBuilderNode",
    "OutputSchemaBuilderNumber",
    "OutputSchemaBuilderObject",
    "OutputSchemaBuilderRef",
    "OutputSchemaBuilderString",
    "OutputSchemaDraftCreate",
    "OutputSchemaDraftUpdate",
    "OutputSchemaKind",
    "OutputSchemaListRead",
    "OutputSchemaRead",
    "OutputSchemaStatus",
]
