from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.runtime import (
    ApprovalMode,
    CapabilityType,
    PersonaProfileKind,
    SpecLifecycleStatus,
    SpecOrigin,
)

_STABLE_SPEC_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"
_DOTTED_IDENTIFIER_RE = r"^[a-z][a-z0-9_]{0,119}(?:\.[a-z][a-z0-9_]{0,119})+$"
_PERSONA_PROFILE_KEY_RE = r"^[a-z][a-z0-9_]{0,119}(?::[a-z][a-z0-9_]{0,119})*$"


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


def _normalize_stable_spec_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_SPEC_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _normalize_dotted_identifier_list(values: list[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    for value in values:
        normalized_values.append(_normalize_dotted_identifier(value, field_name=field_name))
    return normalized_values


def _normalize_dotted_identifier(value: object, *, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name=field_name).lower()
    if re.fullmatch(_DOTTED_IDENTIFIER_RE, normalized) is None:
        raise ValueError(f"{field_name} must use dot-separated lowercase identifiers")
    return normalized


def _normalize_optional_dotted_identifier(value: object, *, field_name: str) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    return _normalize_dotted_identifier(normalized, field_name=field_name)


def _normalize_persona_profile_key_list(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    for value in values:
        normalized = _normalize_required_text(
            value, field_name="Default persona profile key"
        ).lower()
        if re.fullmatch(_PERSONA_PROFILE_KEY_RE, normalized) is None:
            raise ValueError(
                "Default persona profile keys must use lowercase identifiers "
                "with optional ':' segments"
            )
        normalized_values.append(normalized)
    return normalized_values


def _normalize_optional_persona_handle(value: object) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if re.fullmatch(_STABLE_SPEC_KEY_RE, lowered) is None:
        raise ValueError(
            "Handle must start with a letter and use only lowercase letters, numbers, "
            "and underscores"
        )
    return lowered


def _derive_entry_agent_key(graph_definition: dict[str, Any]) -> str | None:
    direct_entry_agent_key = graph_definition.get("entry_agent_key") or graph_definition.get(
        "entryAgentKey"
    )
    if isinstance(direct_entry_agent_key, str) and direct_entry_agent_key.strip():
        return direct_entry_agent_key.strip()

    entry_step_key = graph_definition.get("entry_step_key") or graph_definition.get("entryStepKey")
    steps = graph_definition.get("steps")
    if not isinstance(entry_step_key, str) or not isinstance(steps, list):
        return None

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_key = step.get("step_key") or step.get("stepKey")
        if step_key != entry_step_key:
            continue
        agent_spec_key = step.get("agent_spec_key") or step.get("agentSpecKey")
        if isinstance(agent_spec_key, str) and agent_spec_key.strip():
            return agent_spec_key.strip()
    return None


class AgentSpecDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    final_output_contract: FinalOutputContractRead | None = None
    default_capability_bundle_keys: list[str] = Field(default_factory=list)
    default_persona_profile_keys: list[str] = Field(default_factory=list)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_stable_spec_key(value)

    @field_validator("name", "instructions", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("default_capability_bundle_keys")
    @classmethod
    def validate_default_capability_bundle_keys(cls, value: list[str]) -> list[str]:
        return _normalize_dotted_identifier_list(
            value,
            field_name="Default capability bundle keys",
        )

    @field_validator("default_persona_profile_keys")
    @classmethod
    def validate_default_persona_profile_keys(cls, value: list[str]) -> list[str]:
        return _normalize_persona_profile_key_list(value)


class AgentSpecDraftUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, min_length=1)
    model_policy: dict[str, Any] | None = None
    final_output_contract: FinalOutputContractRead | None = None
    default_capability_bundle_keys: list[str] | None = None
    default_persona_profile_keys: list[str] | None = None

    @field_validator("model_policy", mode="before")
    @classmethod
    def reject_null_model_policy(cls, value: object) -> object:
        if value is None:
            raise ValueError("Model policy must be an object")
        return value

    @field_validator(
        "default_capability_bundle_keys",
        "default_persona_profile_keys",
        mode="before",
    )
    @classmethod
    def reject_null_lists(cls, value: object) -> object:
        if value is None:
            raise ValueError("List fields must be arrays")
        return value

    @field_validator("name", "instructions", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("default_capability_bundle_keys")
    @classmethod
    def validate_default_capability_bundle_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_dotted_identifier_list(
            value,
            field_name="Default capability bundle keys",
        )

    @field_validator("default_persona_profile_keys")
    @classmethod
    def validate_default_persona_profile_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_persona_profile_key_list(value)

    @model_validator(mode="after")
    def validate_payload(self) -> AgentSpecDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class WorkflowSpecDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    graph_definition: dict[str, Any] = Field(default_factory=dict)
    final_output_contract: FinalOutputContractRead
    mention_policy: MentionPolicyRead
    execution_mode: str | None = None
    default_tool_ids: list[str] = Field(default_factory=list)
    allowed_capability_bundle_keys: list[str] = Field(default_factory=list)
    connector_ids: list[str] = Field(default_factory=list)
    review_mode: str | None = None
    approval_policy_overrides: list[ApprovalPolicyOverrideRead] = Field(default_factory=list)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_stable_spec_key(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("execution_mode", "review_mode", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("default_tool_ids", "connector_ids")
    @classmethod
    def validate_dotted_identifier_lists(cls, value: list[str]) -> list[str]:
        return _normalize_dotted_identifier_list(value, field_name="Identifiers")

    @field_validator("allowed_capability_bundle_keys")
    @classmethod
    def validate_allowed_capability_bundle_keys(cls, value: list[str]) -> list[str]:
        return _normalize_dotted_identifier_list(value, field_name="Allowed capability bundle keys")


class WorkflowSpecDraftUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    graph_definition: dict[str, Any] | None = None
    final_output_contract: FinalOutputContractRead | None = None
    mention_policy: MentionPolicyRead | None = None
    execution_mode: str | None = None
    default_tool_ids: list[str] | None = None
    allowed_capability_bundle_keys: list[str] | None = None
    connector_ids: list[str] | None = None
    review_mode: str | None = None
    approval_policy_overrides: list[ApprovalPolicyOverrideRead] | None = None

    @field_validator(
        "graph_definition",
        "final_output_contract",
        "mention_policy",
        "default_tool_ids",
        "allowed_capability_bundle_keys",
        "connector_ids",
        "approval_policy_overrides",
        mode="before",
    )
    @classmethod
    def reject_null_mutable_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Mutable spec fields cannot be null")
        return value

    @field_validator("name", "execution_mode", "review_mode", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("default_tool_ids", "connector_ids")
    @classmethod
    def validate_dotted_identifier_lists(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_dotted_identifier_list(value, field_name="Identifiers")

    @field_validator("allowed_capability_bundle_keys")
    @classmethod
    def validate_allowed_capability_bundle_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_dotted_identifier_list(value, field_name="Allowed capability bundle keys")

    @model_validator(mode="after")
    def validate_payload(self) -> WorkflowSpecDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class StudioVersionHistoryItem(CamelModel):
    version: int = Field(ge=1)
    status: SpecLifecycleStatus
    origin: SpecOrigin
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class StudioVersionHistoryRead(CamelModel):
    items: list[StudioVersionHistoryItem]


class FinalOutputContractRead(CamelModel):
    kind: str
    schema_: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("schema", "schema_"),
    )
    description: str

    @field_validator("kind", "description", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class MentionPolicyRead(CamelModel):
    version: int = Field(ge=1)
    allow_character_personas: bool = Field(
        validation_alias=AliasChoices(
            "allow_character_personas",
            "allowCharacterPersonas",
            "allow_characters",
            "allowCharacters",
        )
    )
    allowed_builtin_handles: list[str] = Field(default_factory=list)


class ApprovalPolicyOverrideRead(CamelModel):
    step_key: str
    capability_key: str | None = None
    approval_mode: ApprovalMode

    @field_validator("step_key", mode="before")
    @classmethod
    def validate_step_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Step key")


class AgentSpecRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    origin: SpecOrigin
    status: SpecLifecycleStatus
    name: str
    instructions: str
    model_policy: dict[str, Any] = Field(default_factory=dict)
    final_output_contract: FinalOutputContractRead | None = None
    default_capability_bundle_keys: list[str] = Field(default_factory=list)
    default_persona_profile_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("key", "name", "instructions", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class AgentSpecListRead(CamelModel):
    items: list[AgentSpecRead]


class WorkflowSpecRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    origin: SpecOrigin
    status: SpecLifecycleStatus
    name: str
    graph_definition: dict[str, Any] = Field(default_factory=dict)
    final_output_contract: dict[str, Any] = Field(default_factory=dict)
    mention_policy: MentionPolicyRead
    execution_mode: str | None = None
    default_tool_ids: list[str] = Field(default_factory=list)
    allowed_capability_bundle_keys: list[str] = Field(default_factory=list)
    connector_ids: list[str] = Field(default_factory=list)
    review_mode: str | None = None
    approval_policy_overrides: list[ApprovalPolicyOverrideRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("key", "name", "execution_mode", "review_mode", mode="before")
    @classmethod
    def validate_text_fields(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @computed_field
    def entry_agent_key(self) -> str | None:
        return _derive_entry_agent_key(self.graph_definition)


class WorkflowSpecListRead(CamelModel):
    items: list[WorkflowSpecRead]


class PersonaProfileDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    handle: str | None = Field(default=None, max_length=120)
    system_prompt_fragment: str = ""
    prompt_append_fragment: str = ""
    default_capability_bundle_keys: list[str] = Field(default_factory=list)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_dotted_identifier(value, field_name="Key")

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Display name")

    @field_validator("handle", mode="before")
    @classmethod
    def validate_handle(cls, value: object) -> str | None:
        return _normalize_optional_persona_handle(value)

    @field_validator("system_prompt_fragment", "prompt_append_fragment", mode="before")
    @classmethod
    def validate_prompt_fields(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("default_capability_bundle_keys")
    @classmethod
    def validate_default_capability_bundle_keys(cls, value: list[str]) -> list[str]:
        return _normalize_dotted_identifier_list(
            value,
            field_name="Default capability bundle keys",
        )


class PersonaProfileDraftUpdate(CamelModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    handle: str | None = Field(default=None, max_length=120)
    system_prompt_fragment: str | None = None
    prompt_append_fragment: str | None = None
    default_capability_bundle_keys: list[str] | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_optional_display_name(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("handle", mode="before")
    @classmethod
    def validate_optional_handle(cls, value: object) -> str | None:
        return _normalize_optional_persona_handle(value)

    @field_validator("system_prompt_fragment", "prompt_append_fragment", mode="before")
    @classmethod
    def validate_optional_prompt_fields(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("default_capability_bundle_keys", mode="before")
    @classmethod
    def reject_null_default_capability_bundle_keys(cls, value: object) -> object:
        if value is None:
            raise ValueError("Default capability bundle keys must be an array")
        return value

    @field_validator("default_capability_bundle_keys")
    @classmethod
    def validate_default_capability_bundle_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_dotted_identifier_list(
            value,
            field_name="Default capability bundle keys",
        )

    @model_validator(mode="after")
    def validate_payload(self) -> PersonaProfileDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class PersonaProfileRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    origin: SpecOrigin
    status: SpecLifecycleStatus
    kind: PersonaProfileKind
    display_name: str
    enabled: bool
    handle: str | None = None
    canonical_target_id: str
    parent_profile_key: str | None = None
    parent_profile_version: int | None = Field(default=None, ge=1)
    legacy_source_version: int | None = Field(default=None, ge=1)
    system_prompt_fragment: str
    prompt_append_fragment: str
    default_capability_bundle_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "key",
        "display_name",
        "handle",
        "canonical_target_id",
        "parent_profile_key",
        mode="before",
    )
    @classmethod
    def validate_text_fields(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, field_name="Value")

    @field_validator("system_prompt_fragment", mode="before")
    @classmethod
    def validate_system_prompt_fragment(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @field_validator("prompt_append_fragment", mode="before")
    @classmethod
    def validate_prompt_append_fragment(cls, value: object) -> str:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            return ""
        return normalized

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class PersonaProfileListRead(CamelModel):
    items: list[PersonaProfileRead]


class CapabilityBundleMemberWrite(CamelModel):
    member_type: CapabilityType = Field(
        validation_alias=AliasChoices("member_type", "memberType", "type")
    )
    capability_key: str = Field(
        validation_alias=AliasChoices("capability_key", "capabilityKey", "key")
    )
    capability_version: int = Field(
        ge=1,
        validation_alias=AliasChoices("capability_version", "capabilityVersion", "version"),
    )

    @field_validator("member_type", mode="before")
    @classmethod
    def validate_member_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("capability_key", mode="before")
    @classmethod
    def validate_capability_key(cls, value: object) -> str:
        return _normalize_dotted_identifier(value, field_name="Capability key")


class CapabilityBundleMemberRead(CapabilityBundleMemberWrite):
    pass


class CapabilityRegistryEntryDraftCreate(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    type: CapabilityType
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    approval_mode: ApprovalMode | None = None
    adapter_key: str | None = Field(default=None, max_length=120)
    config_schema: dict[str, Any] | None = None
    bundle_members: list[CapabilityBundleMemberWrite] | None = None
    transport: str | None = Field(default=None, max_length=40)
    lifecycle: str | None = Field(default=None, max_length=40)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_dotted_identifier(value, field_name="Key")

    @field_validator("display_name", "description", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("adapter_key", mode="before")
    @classmethod
    def validate_adapter_key(cls, value: object) -> str | None:
        return _normalize_optional_dotted_identifier(value, field_name="Adapter key")

    @field_validator("transport", "lifecycle", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            return None
        return normalized.lower()


class CapabilityRegistryEntryDraftUpdate(CamelModel):
    type: CapabilityType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    approval_mode: ApprovalMode | None = None
    adapter_key: str | None = Field(default=None, max_length=120)
    config_schema: dict[str, Any] | None = None
    bundle_members: list[CapabilityBundleMemberWrite] | None = None
    transport: str | None = Field(default=None, max_length=40)
    lifecycle: str | None = Field(default=None, max_length=40)

    @field_validator("display_name", "description", mode="before")
    @classmethod
    def validate_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("adapter_key", mode="before")
    @classmethod
    def validate_optional_adapter_key(cls, value: object) -> str | None:
        return _normalize_optional_dotted_identifier(value, field_name="Adapter key")

    @field_validator("transport", "lifecycle", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            return None
        return normalized.lower()

    @model_validator(mode="after")
    def validate_payload(self) -> CapabilityRegistryEntryDraftUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class CapabilityRegistryEntryRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    origin: SpecOrigin
    status: SpecLifecycleStatus
    type: CapabilityType
    display_name: str
    description: str
    approval_mode: ApprovalMode
    adapter_key: str | None = None
    config_schema: dict[str, Any] | None = None
    bundle_members: list[CapabilityBundleMemberRead] | None = None
    transport: str | None = None
    lifecycle: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "key",
        "display_name",
        "description",
        "adapter_key",
        "transport",
        "lifecycle",
        mode="before",
    )
    @classmethod
    def validate_text_fields(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class CapabilityRegistryEntryListRead(CamelModel):
    items: list[CapabilityRegistryEntryRead]
