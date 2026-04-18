from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.services.runtime_seed_catalog import (
    SEEDED_AGENT_SPECS,
    SEEDED_BUILTIN_SPECS,
    SEEDED_CAPABILITY_BUNDLE_SPECS,
    SEEDED_CONNECTOR_SPECS,
    SEEDED_TOOL_SPECS,
    get_seeded_connector_spec,
    get_seeded_tool_spec,
)

_SEEDED_ORIGIN = "seeded"
_ACTIVE_STATUS = "ACTIVE"
_SEEDED_RUNTIME_VERSION = 1
_PHASE_1_CYCLE_CONTEXT_ARTIFACT_KEYS = (
    "prompt_report_slug",
    "prompt_report",
    "authored_entry_prompt_body",
    "compiled_entry_prompt_body",
    "execution_context_body",
    "full_user_prompt",
    "resolved_mentions",
    "mentioned_target_outputs",
    "mentioned_target_output_ids",
)


class RuntimeSeedBootstrapDriftError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSeedBootstrapResult:
    workflow_specs_inserted: int = 0
    agent_specs_inserted: int = 0
    persona_profiles_inserted: int = 0
    capability_registry_entries_inserted: int = 0

    @property
    def total_inserted(self) -> int:
        return (
            self.workflow_specs_inserted
            + self.agent_specs_inserted
            + self.persona_profiles_inserted
            + self.capability_registry_entries_inserted
        )


@dataclass(frozen=True)
class _SeedMirrorTableSpec:
    entity_name: str
    model: type[Any]
    fields: tuple[str, ...]
    build_expected: Callable[[], dict[tuple[str, int], dict[str, Any]]]


def bootstrap_runtime_seed_mirrors(session: Session) -> RuntimeSeedBootstrapResult:
    agent_specs_inserted = _sync_seeded_rows(session, _AGENT_TABLE_SPEC)
    persona_profiles_inserted = _sync_seeded_rows(session, _PERSONA_TABLE_SPEC)
    capability_registry_entries_inserted = _sync_seeded_rows(session, _CAPABILITY_TABLE_SPEC)
    session.flush()
    return RuntimeSeedBootstrapResult(
        workflow_specs_inserted=0,
        agent_specs_inserted=agent_specs_inserted,
        persona_profiles_inserted=persona_profiles_inserted,
        capability_registry_entries_inserted=capability_registry_entries_inserted,
    )


def _sync_seeded_rows(session: Session, table_spec: _SeedMirrorTableSpec) -> int:
    expected_payloads = table_spec.build_expected()
    existing_rows = session.scalars(select(table_spec.model)).all()
    matched_identities: set[tuple[str, int]] = set()
    unexpected_seeded_rows: list[dict[str, Any]] = []

    for row in existing_rows:
        actual_payload = _row_payload(row, table_spec.fields)
        identity = (str(actual_payload["key"]), int(actual_payload["version"]))
        expected_payload = expected_payloads.get(identity)
        if expected_payload is not None:
            if actual_payload != expected_payload:
                raise RuntimeSeedBootstrapDriftError(
                    "Seed drift detected for "
                    f"{table_spec.entity_name} {identity[0]!r} v{identity[1]}: expected "
                    f"{_to_canonical_json(expected_payload)} but found "
                    f"{_to_canonical_json(actual_payload)}"
                )
            matched_identities.add(identity)
            continue

        if actual_payload["origin"] == _SEEDED_ORIGIN:
            unexpected_seeded_rows.append({"key": identity[0], "version": identity[1]})

    if unexpected_seeded_rows:
        raise RuntimeSeedBootstrapDriftError(
            "Seed drift detected for "
            f"{table_spec.entity_name}: unexpected seeded rows "
            f"{_to_canonical_json(unexpected_seeded_rows)}"
        )

    inserted = 0
    for identity, payload in expected_payloads.items():
        if identity in matched_identities:
            continue
        session.add(table_spec.model(**_build_insert_payload(table_spec.model, payload)))
        inserted += 1

    return inserted


def _row_payload(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields}


def _build_insert_payload(model: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    insert_payload = dict(payload)
    if model is CapabilityRegistryEntry:
        if insert_payload.get("bundle_members") is None:
            insert_payload.pop("bundle_members", None)
        if insert_payload.get("config_schema") is None:
            insert_payload.pop("config_schema", None)
    return insert_payload


def _to_canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _build_expected_agent_payloads() -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (agent.key, _SEEDED_RUNTIME_VERSION): {
            "key": agent.key,
            "version": _SEEDED_RUNTIME_VERSION,
            "origin": _SEEDED_ORIGIN,
            "status": _ACTIVE_STATUS,
            "name": agent.role,
            "instructions": agent.system_prompt,
            "model_policy": {},
            "final_output_contract": None,
            "default_capability_bundle_keys": [],
            "default_persona_profile_keys": [],
        }
        for agent in SEEDED_AGENT_SPECS
    }


def _build_expected_persona_payloads() -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (builtin.canonical_target_id, _SEEDED_RUNTIME_VERSION): {
            "key": builtin.canonical_target_id,
            "version": _SEEDED_RUNTIME_VERSION,
            "origin": _SEEDED_ORIGIN,
            "status": _ACTIVE_STATUS,
            "kind": "builtin_profile",
            "display_name": builtin.display_name,
            "enabled": True,
            "handle": builtin.handle,
            "canonical_target_id": builtin.canonical_target_id,
            "parent_profile_key": None,
            "parent_profile_version": None,
            "legacy_entity_type": None,
            "legacy_entity_key": None,
            "legacy_source_version": builtin.revision,
            "system_prompt_fragment": builtin.description,
            "prompt_append_fragment": "",
            "default_capability_bundle_keys": list(builtin.capability_bundle_keys),
        }
        for builtin in SEEDED_BUILTIN_SPECS
    }


def _build_expected_capability_payloads() -> dict[tuple[str, int], dict[str, Any]]:
    payloads: dict[tuple[str, int], dict[str, Any]] = {}

    for tool in SEEDED_TOOL_SPECS:
        payloads[(tool.tool_id, _SEEDED_RUNTIME_VERSION)] = {
            "key": tool.tool_id,
            "version": _SEEDED_RUNTIME_VERSION,
            "origin": _SEEDED_ORIGIN,
            "status": _ACTIVE_STATUS,
            "type": "tool",
            "display_name": tool.display_name,
            "description": tool.description,
            "approval_mode": "not_required",
            "adapter_key": tool.tool_id,
            "config_schema": _build_tool_config_schema(tool.tool_id),
            "bundle_members": None,
            "transport": None,
            "lifecycle": None,
        }

    for connector in SEEDED_CONNECTOR_SPECS:
        payloads[(connector.connector_id, _SEEDED_RUNTIME_VERSION)] = {
            "key": connector.connector_id,
            "version": _SEEDED_RUNTIME_VERSION,
            "origin": _SEEDED_ORIGIN,
            "status": _ACTIVE_STATUS,
            "type": "connector",
            "display_name": connector.display_name,
            "description": connector.description,
            "approval_mode": "required",
            "adapter_key": connector.connector_id,
            "config_schema": _build_connector_config_schema(connector.connector_id),
            "bundle_members": None,
            "transport": connector.transport,
            "lifecycle": connector.lifecycle,
        }

    for bundle in SEEDED_CAPABILITY_BUNDLE_SPECS:
        payloads[(bundle.bundle_key, _SEEDED_RUNTIME_VERSION)] = {
            "key": bundle.bundle_key,
            "version": _SEEDED_RUNTIME_VERSION,
            "origin": _SEEDED_ORIGIN,
            "status": _ACTIVE_STATUS,
            "type": "bundle",
            "display_name": bundle.display_name,
            "description": bundle.description,
            "approval_mode": "not_required",
            "adapter_key": None,
            "config_schema": None,
            "bundle_members": _build_bundle_members(bundle.tool_ids, bundle.connector_ids),
            "transport": None,
            "lifecycle": None,
        }

    return payloads


def _build_bundle_members(
    tool_ids: tuple[str, ...], connector_ids: tuple[str, ...]
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []

    for tool_id in tool_ids:
        if get_seeded_tool_spec(tool_id) is None:
            raise ValueError(f"Seeded bundle references unknown tool {tool_id!r}")
        members.append({"key": tool_id, "type": "tool", "version": _SEEDED_RUNTIME_VERSION})

    for connector_id in connector_ids:
        if get_seeded_connector_spec(connector_id) is None:
            raise ValueError(f"Seeded bundle references unknown connector {connector_id!r}")
        members.append(
            {"key": connector_id, "type": "connector", "version": _SEEDED_RUNTIME_VERSION}
        )

    return members


def _build_tool_config_schema(tool_id: str) -> dict[str, Any]:
    if tool_id == "ledger.report_lookup":
        return {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
            "additionalProperties": False,
        }
    if tool_id == "ledger.orchestration_catalog_lookup":
        return {
            "type": "object",
            "properties": {"handle": {"type": "string"}},
            "additionalProperties": False,
        }
    if tool_id == "ledger.cycle_context_lookup":
        return {
            "type": "object",
            "properties": {
                "artifact_key": {
                    "type": "string",
                    "enum": list(_PHASE_1_CYCLE_CONTEXT_ARTIFACT_KEYS),
                }
            },
            "required": ["artifact_key"],
            "additionalProperties": False,
        }
    raise ValueError(f"Unknown seeded tool id {tool_id!r}")


def _build_connector_config_schema(connector_id: str) -> dict[str, Any]:
    if connector_id in {"ledger.mcp.market_data", "ledger.mcp.company_filings"}:
        return {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        }
    raise ValueError(f"Unknown seeded connector id {connector_id!r}")


_AGENT_FIELDS = (
    "key",
    "version",
    "origin",
    "status",
    "name",
    "instructions",
    "model_policy",
    "final_output_contract",
    "default_capability_bundle_keys",
    "default_persona_profile_keys",
)
_PERSONA_FIELDS = (
    "key",
    "version",
    "origin",
    "status",
    "kind",
    "display_name",
    "enabled",
    "handle",
    "canonical_target_id",
    "parent_profile_key",
    "parent_profile_version",
    "legacy_entity_type",
    "legacy_entity_key",
    "legacy_source_version",
    "system_prompt_fragment",
    "prompt_append_fragment",
    "default_capability_bundle_keys",
)
_CAPABILITY_FIELDS = (
    "key",
    "version",
    "origin",
    "status",
    "type",
    "display_name",
    "description",
    "approval_mode",
    "adapter_key",
    "config_schema",
    "bundle_members",
    "transport",
    "lifecycle",
)

_AGENT_TABLE_SPEC = _SeedMirrorTableSpec(
    entity_name="agent_specs",
    model=AgentSpec,
    fields=_AGENT_FIELDS,
    build_expected=_build_expected_agent_payloads,
)
_PERSONA_TABLE_SPEC = _SeedMirrorTableSpec(
    entity_name="persona_profiles",
    model=PersonaProfile,
    fields=_PERSONA_FIELDS,
    build_expected=_build_expected_persona_payloads,
)
_CAPABILITY_TABLE_SPEC = _SeedMirrorTableSpec(
    entity_name="capability_registry_entries",
    model=CapabilityRegistryEntry,
    fields=_CAPABILITY_FIELDS,
    build_expected=_build_expected_capability_payloads,
)


__all__ = [
    "RuntimeSeedBootstrapDriftError",
    "RuntimeSeedBootstrapResult",
    "bootstrap_runtime_seed_mirrors",
]
