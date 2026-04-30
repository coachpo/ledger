from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Literal, cast

from pydantic import AliasChoices, Field, field_serializer, field_validator, model_validator

from app.schemas.common import CamelModel

AGENT_MANIFEST_API_VERSION = "ledger.agent/v1"

_STABLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_STABLE_MCP_SERVER_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,119}$")
_PIN_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]{0,119})@(?P<version>[1-9][0-9]*)$")
_MCP_PIN_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_-]{0,119})@(?P<version>[1-9][0-9]*)$")

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Description must be a string")
    return value.strip()


def _validate_stable_key(value: object, *, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name=field_name)
    if _STABLE_KEY_RE.fullmatch(normalized) is None:
        raise ValueError(
            f"{field_name} must start with a lowercase letter and use only lowercase letters, "
            + "numbers, and underscores"
        )
    return normalized


class AgentManifestDiagnosticSeverity(str, Enum):  # noqa: UP042
    ERROR = "error"
    WARNING = "warning"


class AgentManifestDiagnostic(CamelModel):
    severity: AgentManifestDiagnosticSeverity
    message: str
    path: str
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)


class AgentManifestPinnedRef(CamelModel):
    key: str
    version: int = Field(ge=1)

    @classmethod
    def parse(
        cls,
        value: object,
        *,
        field_name: str,
        allow_hyphen: bool = False,
    ) -> AgentManifestPinnedRef:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string in the form <key>@<version>")
        normalized = value.strip()
        match = (_MCP_PIN_RE if allow_hyphen else _PIN_RE).fullmatch(normalized)
        if match is None:
            raise ValueError(f"{field_name} must pin an exact numeric version as <key>@<version>")
        return cls(key=match.group("key"), version=int(match.group("version")))

    def to_pin(self) -> str:
        return f"{self.key}@{self.version}"


class AgentManifestMetadata(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _validate_stable_key(value, field_name="Agent key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value)


class AgentManifestSpec(CamelModel):
    model_connection: str = Field(alias="modelConnection", min_length=1, max_length=120)
    system_prompt: str = Field(alias="systemPrompt", min_length=1)
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    output_schema: AgentManifestPinnedRef = Field(alias="outputSchema")
    capabilities: list[AgentManifestPinnedRef] = Field(
        default_factory=list,
        validation_alias=AliasChoices("capabilities", "skills"),
    )
    mcp_servers: list[AgentManifestPinnedRef] = Field(default_factory=list, alias="mcpServers")
    budget_usd: str = Field(default="0", alias="budgetUsd")

    @property
    def skills(self) -> list[AgentManifestPinnedRef]:
        return self.capabilities

    @model_validator(mode="before")
    @classmethod
    def reject_conflicting_capability_aliases(cls, value: object) -> object:
        if isinstance(value, dict) and "capabilities" in value and "skills" in value:
            raise ValueError("Use either spec.capabilities or legacy spec.skills, not both")
        return value

    @field_validator("model_connection", mode="before")
    @classmethod
    def validate_model_connection(cls, value: object) -> str:
        return _validate_stable_key(value, field_name="Model connection")

    @field_validator("system_prompt", mode="before")
    @classmethod
    def validate_system_prompt(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="System prompt")

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("inputSchema must be an object schema")
        return value

    @field_validator("output_schema", mode="before")
    @classmethod
    def validate_output_schema(cls, value: object) -> AgentManifestPinnedRef:
        return AgentManifestPinnedRef.parse(value, field_name="outputSchema")

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities(cls, value: object) -> list[AgentManifestPinnedRef]:
        return _parse_ref_list(value, field_name="capabilities")

    @field_validator("mcp_servers", mode="before")
    @classmethod
    def validate_mcp_servers(cls, value: object) -> list[AgentManifestPinnedRef]:
        return _parse_ref_list(value, field_name="mcpServers", allow_hyphen=True)

    @field_validator("budget_usd", mode="before")
    @classmethod
    def validate_budget_usd(cls, value: object) -> str:
        if value is None:
            return "0"
        if not isinstance(value, str):
            raise ValueError("budgetUsd must be a decimal string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("budgetUsd is required")
        try:
            decimal_value = Decimal(normalized)
        except InvalidOperation as exc:
            raise ValueError("budgetUsd must be a decimal string") from exc
        if not decimal_value.is_finite() or decimal_value < 0:
            raise ValueError("budgetUsd must be a non-negative decimal string")
        return normalized

    @field_serializer("output_schema", when_used="json")
    def serialize_output_schema(self, value: AgentManifestPinnedRef) -> str:
        return value.to_pin()

    @field_serializer("capabilities", "mcp_servers", when_used="json")
    def serialize_ref_list(self, value: list[AgentManifestPinnedRef]) -> list[str]:
        return [item.to_pin() for item in value]


def _parse_ref_list(
    value: object,
    *,
    field_name: str,
    allow_hyphen: bool = False,
) -> list[AgentManifestPinnedRef]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array of <key>@<version> strings")
    raw_items = cast(list[object], value)
    return [
        AgentManifestPinnedRef.parse(item, field_name=field_name, allow_hyphen=allow_hyphen)
        for item in raw_items
    ]


class AgentManifest(CamelModel):
    api_version: Literal["ledger.agent/v1"] = Field(alias="apiVersion")
    kind: Literal["Agent"]
    metadata: AgentManifestMetadata
    spec: AgentManifestSpec


class AgentManifestParseResult(CamelModel):
    manifest: AgentManifest | None = None
    diagnostics: list[AgentManifestDiagnostic] = Field(default_factory=list)


_ = AgentManifest.model_rebuild()


__all__ = [
    "AGENT_MANIFEST_API_VERSION",
    "AgentManifest",
    "AgentManifestDiagnostic",
    "AgentManifestDiagnosticSeverity",
    "AgentManifestMetadata",
    "AgentManifestParseResult",
    "AgentManifestPinnedRef",
    "AgentManifestSpec",
]
