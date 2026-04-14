from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error
from app.langgraph.seeds import (
    PatternMentionPolicy,
    get_backtest_pattern_spec,
    get_seeded_builtin_spec_for_handle,
)
from app.repositories.orchestration_character import OrchestrationCharacterRepository
from app.repositories.persona_profile import PersonaProfileRepository
from app.schemas.runtime import PersonaProfileRef

_MENTION_RE = re.compile(r"(?<![@A-Za-z0-9_])@(?P<handle>[A-Za-z][A-Za-z0-9_]*)\b")
SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class BacktestRuntimeMentionCompilation:
    raw_mention_handles: tuple[str, ...]
    resolved_mentions: tuple[dict[str, Any], ...]
    persona_profile_refs: tuple[PersonaProfileRef, ...]
    resolved_builtin_versions: tuple[dict[str, Any], ...]
    resolved_role_versions: tuple[dict[str, Any], ...]
    resolved_character_versions: tuple[dict[str, Any], ...]


def resolve_runtime_pattern_mention_policy(pattern_key: str) -> PatternMentionPolicy:
    pattern_spec = get_backtest_pattern_spec(pattern_key)
    if pattern_spec is None:
        raise business_rule_error(
            "invalid_orchestration_pattern",
            f"Unknown orchestration pattern: {pattern_key}",
        )
    return pattern_spec.mention_policy


def build_runtime_full_user_prompt(
    *, execution_context_body: str, compiled_entry_prompt_body: str
) -> str:
    return "\n\n".join(
        [part for part in (execution_context_body, compiled_entry_prompt_body) if part]
    )


def append_mentioned_target_outputs(
    execution_context_body: str, mentioned_target_outputs: list[dict[str, Any]]
) -> str:
    if not mentioned_target_outputs:
        return execution_context_body
    lines = ["## Mentioned Target Outputs"]
    for mention in mentioned_target_outputs:
        lines.append(f"- {mention['handle']}: {mention['output_markdown']}")
    mentioned_outputs = "\n".join(lines)
    normalized_execution_context_body = execution_context_body.rstrip("\n")
    if not normalized_execution_context_body:
        return mentioned_outputs
    return f"{normalized_execution_context_body}\n\n{mentioned_outputs}"


def serialize_resolved_mentions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "original_text": target["original_text"],
            "handle": target["handle"],
            "canonical_target_id": target["canonical_target_id"],
            "target_type": target["target_type"],
            "role_id": target["role_id"],
            "role_version": target["role_version"],
            "character_id": target["character_id"],
            "character_version": target["character_version"],
            "mention_order": target["mention_order"],
        }
        for target in resolved_targets
    ]


def serialize_mentioned_target_outputs(
    mentioned_target_outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "handle": target["handle"],
            "canonical_target_id": target["canonical_target_id"],
            "target_type": target["target_type"],
            "output_markdown": target["output_markdown"],
        }
        for target in mentioned_target_outputs
    ]


def serialize_builtin_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_target_id": target["canonical_target_id"],
            "handle": target["handle"],
            "revision": target["builtin_revision"],
        }
        for target in resolved_targets
        if target["target_type"] == "builtin"
    ]


def serialize_role_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_target_id": f"role:{target['role_key']}",
            "role_id": target["role_id"],
            "version": target["role_version"],
        }
        for target in resolved_targets
        if target["target_type"] == "character"
    ]


def serialize_character_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_target_id": target["canonical_target_id"],
            "character_id": target["character_id"],
            "version": target["character_version"],
        }
        for target in resolved_targets
        if target["target_type"] == "character"
    ]


class BacktestRuntimeMentionResolver:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def resolve_targets(
        self,
        *,
        authored_entry_prompt_body: str,
        orchestration_pattern_key: str,
        pattern_policy: PatternMentionPolicy | None = None,
    ) -> list[dict[str, Any]]:
        if not authored_entry_prompt_body:
            return []
        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()
        effective_pattern_policy = pattern_policy or resolve_runtime_pattern_mention_policy(
            orchestration_pattern_key
        )

        for match in _MENTION_RE.finditer(authored_entry_prompt_body):
            original_text = match.group(0)
            handle = match.group("handle").lower()
            builtin_spec = get_seeded_builtin_spec_for_handle(handle)
            if builtin_spec is not None:
                canonical_target_id = builtin_spec.canonical_target_id
                if canonical_target_id in seen:
                    continue
                if handle not in effective_pattern_policy.allowed_builtin_handles:
                    self._raise_mention_not_allowed(handle, orchestration_pattern_key)
                resolved.append(
                    {
                        "original_text": original_text,
                        "handle": handle,
                        "canonical_target_id": canonical_target_id,
                        "target_type": "builtin",
                        "role_id": None,
                        "role_version": None,
                        "character_id": None,
                        "character_version": None,
                        "mention_order": len(resolved),
                        "builtin_revision": builtin_spec.revision,
                        "capability_bundle_keys": tuple(builtin_spec.capability_bundle_keys),
                    }
                )
                seen.add(canonical_target_id)
                continue

            canonical_target_id = f"character:{handle}"
            if canonical_target_id in seen:
                continue
            if not effective_pattern_policy.allow_characters:
                self._raise_mention_not_allowed(handle, orchestration_pattern_key)

            character_record = self._resolve_orchestration_character(handle)
            character_spec = character_record["character"]
            role_spec = character_record["role"]
            if not character_spec.enabled:
                raise business_rule_error(
                    "mention_target_disabled",
                    f"Mention target @{handle} is disabled",
                )
            if not role_spec.enabled:
                raise business_rule_error(
                    "character_role_disabled",
                    f"Character role for @{handle} is disabled",
                )
            resolved.append(
                {
                    "original_text": original_text,
                    "handle": handle,
                    "canonical_target_id": canonical_target_id,
                    "target_type": "character",
                    "role_id": role_spec.id,
                    "role_version": role_spec.version,
                    "character_id": character_spec.id,
                    "character_version": character_spec.version,
                    "mention_order": len(resolved),
                    "role_name": role_spec.name,
                    "role_key": role_spec.key,
                    "role_system_prompt": role_spec.system_prompt,
                    "character_prompt_append": character_spec.prompt_append,
                    "role_capability_bundle_keys": tuple(role_spec.capability_bundle_keys),
                    "character_capability_bundle_keys": tuple(
                        character_spec.capability_bundle_keys
                    ),
                }
            )
            seen.add(canonical_target_id)

        return resolved

    def build_mentioned_target_outputs(
        self,
        *,
        resolved_targets: list[dict[str, Any]],
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> list[dict[str, Any]]:
        mentioned_target_outputs: list[dict[str, Any]] = []
        for target in resolved_targets:
            if target["target_type"] == "builtin":
                output_markdown = self._run_builtin_pre_run_step(
                    handle=str(target["handle"]),
                    compiled_entry_prompt_body=compiled_entry_prompt_body,
                    execution_context_body=execution_context_body,
                )
            else:
                output_markdown = self._run_character_pre_run_step(
                    target=target,
                    compiled_entry_prompt_body=compiled_entry_prompt_body,
                    execution_context_body=execution_context_body,
                )
            mentioned_target_outputs.append(
                {
                    "handle": target["handle"],
                    "canonical_target_id": target["canonical_target_id"],
                    "target_type": target["target_type"],
                    "output_markdown": output_markdown,
                }
            )
        return mentioned_target_outputs

    def _resolve_orchestration_character(self, handle: str) -> Any:
        with self.session_factory() as session:
            character = OrchestrationCharacterRepository(session).get_by_handle(handle)
            if character is None:
                raise business_rule_error(
                    "mention_target_not_found",
                    f"Mention target @{handle} was not found",
                )
            session.refresh(character)
            role = character.role
            if role is None:
                raise business_rule_error(
                    "mention_target_not_found",
                    f"Mention target @{handle} was not found",
                )
            session.refresh(role)
            return {"character": character, "role": role}

    @staticmethod
    def _run_builtin_pre_run_step(
        *,
        handle: str,
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> str:
        builtin_spec = get_seeded_builtin_spec_for_handle(handle)
        if builtin_spec is None:
            raise business_rule_error(
                "mention_target_not_found",
                f"Mention target @{handle} was not found",
            )
        return (
            f"{builtin_spec.description} Entry prompt focus: "
            f"{_compact_runtime_artifact_text(compiled_entry_prompt_body)}. "
            f"Execution context focus: {_compact_runtime_artifact_text(execution_context_body)}."
        )

    @staticmethod
    def _run_character_pre_run_step(
        *,
        target: dict[str, Any],
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> str:
        character_guidance = str(target.get("character_prompt_append") or "").strip()
        guidance_summary = (
            _compact_runtime_artifact_text(character_guidance)
            if character_guidance
            else "No character-specific guidance provided"
        )
        return (
            f"{target['role_name']} execution brief. "
            f"System prompt: {_compact_runtime_artifact_text(str(target['role_system_prompt']))}. "
            f"Character guidance: {guidance_summary}. "
            f"Entry prompt focus: {_compact_runtime_artifact_text(compiled_entry_prompt_body)}. "
            f"Execution context focus: {_compact_runtime_artifact_text(execution_context_body)}."
        )

    @staticmethod
    def _raise_mention_not_allowed(handle: str, orchestration_pattern_key: str) -> None:
        raise business_rule_error(
            "mention_target_not_allowed_by_pattern",
            (
                f"Mention target @{handle} is not allowed by orchestration pattern "
                f"{orchestration_pattern_key}"
            ),
        )


def _compact_runtime_artifact_text(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized or "none"


class BacktestRuntimeMentionCompiler:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.persona_repository = PersonaProfileRepository(session)

    def compile(
        self,
        *,
        authored_entry_prompt_body: str,
        resolved_targets: Sequence[dict[str, Any]],
    ) -> BacktestRuntimeMentionCompilation:
        raw_mention_handles = tuple(self._scan_raw_mention_handles(authored_entry_prompt_body))
        resolved_mentions: list[dict[str, Any]] = []
        persona_profile_refs: list[PersonaProfileRef] = []
        resolved_builtin_versions: list[dict[str, Any]] = []
        resolved_role_versions: list[dict[str, Any]] = []
        resolved_character_versions: list[dict[str, Any]] = []
        seen_persona_refs: set[tuple[str, int]] = set()

        for target in resolved_targets:
            profile = self._resolve_persona_profile(target)
            resolved_mentions.append(
                {
                    "originalText": str(target["original_text"]),
                    "sourceHandle": str(target["handle"]),
                    "canonicalTargetId": str(target["canonical_target_id"]),
                    "targetType": str(target["target_type"]),
                    "mentionOrder": int(target["mention_order"]),
                    "personaProfileKey": str(profile.key),
                    "personaProfileVersion": int(profile.version),
                    "legacyRoleId": self._optional_int(target.get("role_id")),
                    "legacyRoleVersion": self._optional_int(target.get("role_version")),
                    "legacyCharacterId": self._optional_int(target.get("character_id")),
                    "legacyCharacterVersion": self._optional_int(target.get("character_version")),
                }
            )
            self._append_persona_ref(
                persona_profile_refs,
                seen_persona_refs,
                key=str(profile.key),
                version=int(profile.version),
                selection_source="mention_resolution",
            )
            parent_profile_key = profile.parent_profile_key
            parent_profile_version = profile.parent_profile_version
            if parent_profile_key is not None and parent_profile_version is not None:
                self._append_persona_ref(
                    persona_profile_refs,
                    seen_persona_refs,
                    key=str(parent_profile_key),
                    version=int(parent_profile_version),
                    selection_source="mention_parent_resolution",
                )

            if target["target_type"] == "builtin":
                resolved_builtin_versions.append(
                    {
                        "canonical_target_id": str(target["canonical_target_id"]),
                        "handle": str(target["handle"]),
                        "revision": int(target["builtin_revision"]),
                    }
                )
                continue

            resolved_role_versions.append(
                {
                    "canonical_target_id": f"role:{target['role_key']}",
                    "role_id": int(target["role_id"]),
                    "version": int(target["role_version"]),
                }
            )
            resolved_character_versions.append(
                {
                    "canonical_target_id": str(target["canonical_target_id"]),
                    "character_id": int(target["character_id"]),
                    "version": int(target["character_version"]),
                }
            )

        return BacktestRuntimeMentionCompilation(
            raw_mention_handles=raw_mention_handles,
            resolved_mentions=tuple(resolved_mentions),
            persona_profile_refs=tuple(persona_profile_refs),
            resolved_builtin_versions=tuple(resolved_builtin_versions),
            resolved_role_versions=tuple(resolved_role_versions),
            resolved_character_versions=tuple(resolved_character_versions),
        )

    @staticmethod
    def _scan_raw_mention_handles(authored_entry_prompt_body: str) -> list[str]:
        return [
            match.group("handle").lower()
            for match in _MENTION_RE.finditer(authored_entry_prompt_body)
        ]

    def _resolve_persona_profile(self, target: dict[str, Any]) -> Any:
        canonical_target_id = str(target["canonical_target_id"])
        profile = self.persona_repository.get_active_by_canonical_target_id(canonical_target_id)
        if profile is None:
            raise business_rule_error(
                "runtime_persona_not_found",
                f"Persona profile for mention target {canonical_target_id!r} was not found",
            )
        return profile

    @staticmethod
    def _append_persona_ref(
        target: list[PersonaProfileRef],
        seen: set[tuple[str, int]],
        *,
        key: str,
        version: int,
        selection_source: str,
    ) -> None:
        identity = (key, version)
        if identity in seen:
            return
        seen.add(identity)
        target.append(
            PersonaProfileRef(
                persona_profile_key=key,
                persona_profile_version=version,
                selection_source=selection_source,
            )
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None:
            return None
        return int(cast(Any, value))
