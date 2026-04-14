from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.orchestration_character import OrchestrationCharacter
from app.models.orchestration_role import OrchestrationRole
from app.models.persona_profile import PersonaProfile
from app.models.persona_projection_event import PersonaProjectionEvent
from app.repositories.persona_profile import PersonaProfileRepository

_IMPORTED_ORIGIN = "imported"
_ACTIVE_STATUS = "ACTIVE"
_DEPRECATED_STATUS = "DEPRECATED"
_ARCHIVED_STATUS = "ARCHIVED"
_ROLE_PROFILE_KIND = "role_template"
_CHARACTER_PROFILE_KIND = "character_profile"
_PROJECTION_ACTOR = "legacy_orchestration_write_through"


class PersonaProjectionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.persona_repo = PersonaProfileRepository(session)

    def project_role(self, role: OrchestrationRole) -> PersonaProfile:
        profile_key = self._role_profile_key(role.key)
        canonical_target_id = self._role_canonical_target_id(role.key)
        return self._project_imported_profile(
            legacy_entity_type="role",
            legacy_entity_key=role.key,
            profile_key=profile_key,
            kind=_ROLE_PROFILE_KIND,
            display_name=role.name,
            enabled=role.enabled,
            handle=None,
            canonical_target_id=canonical_target_id,
            parent_profile=None,
            legacy_source_version=role.version,
            system_prompt_fragment=role.system_prompt,
            prompt_append_fragment="",
            default_capability_bundle_keys=list(role.capability_bundle_keys),
        )

    def archive_role(self, role: OrchestrationRole) -> PersonaProfile | None:
        return self._archive_imported_profile(
            legacy_entity_type="role",
            legacy_entity_key=role.key,
            profile_key=self._role_profile_key(role.key),
        )

    def project_character(
        self,
        character: OrchestrationCharacter,
        *,
        role: OrchestrationRole | None = None,
    ) -> PersonaProfile:
        resolved_role = role or character.role
        if resolved_role is None:
            resolved_role = self.session.get(OrchestrationRole, character.role_id)
        if resolved_role is None:
            raise RuntimeError(
                f"Missing legacy role {character.role_id} "
                f"for character @{character.handle} projection"
            )

        parent_profile = self._resolve_role_parent_profile(resolved_role)
        profile_key = self._character_profile_key(character.handle)
        canonical_target_id = self._character_canonical_target_id(character.handle)
        return self._project_imported_profile(
            legacy_entity_type="character",
            legacy_entity_key=character.handle,
            profile_key=profile_key,
            kind=_CHARACTER_PROFILE_KIND,
            display_name=character.display_name,
            enabled=character.enabled,
            handle=character.handle,
            canonical_target_id=canonical_target_id,
            parent_profile=parent_profile,
            legacy_source_version=character.version,
            system_prompt_fragment="",
            prompt_append_fragment=character.prompt_append or "",
            default_capability_bundle_keys=list(character.capability_bundle_keys),
        )

    def archive_character(self, character: OrchestrationCharacter) -> PersonaProfile | None:
        return self._archive_imported_profile(
            legacy_entity_type="character",
            legacy_entity_key=character.handle,
            profile_key=self._character_profile_key(character.handle),
        )

    def _resolve_role_parent_profile(self, role: OrchestrationRole) -> PersonaProfile:
        profile_key = self._role_profile_key(role.key)
        role_profile = self.persona_repo.get_active_by_key(profile_key, origin=_IMPORTED_ORIGIN)
        if role_profile is None or role_profile.legacy_source_version != role.version:
            role_profile = self.project_role(role)
        return role_profile

    def _project_imported_profile(
        self,
        *,
        legacy_entity_type: str,
        legacy_entity_key: str,
        profile_key: str,
        kind: str,
        display_name: str,
        enabled: bool,
        handle: str | None,
        canonical_target_id: str,
        parent_profile: PersonaProfile | None,
        legacy_source_version: int,
        system_prompt_fragment: str,
        prompt_append_fragment: str,
        default_capability_bundle_keys: list[str],
    ) -> PersonaProfile:
        existing_versions = self.persona_repo.list_versions(profile_key, origin=_IMPORTED_ORIGIN)
        active_profile = next(
            (profile for profile in existing_versions if profile.status == _ACTIVE_STATUS), None
        )
        if active_profile is not None and self._profile_matches_projection(
            active_profile,
            display_name=display_name,
            enabled=enabled,
            handle=handle,
            canonical_target_id=canonical_target_id,
            parent_profile=parent_profile,
            legacy_entity_type=legacy_entity_type,
            legacy_entity_key=legacy_entity_key,
            legacy_source_version=legacy_source_version,
            system_prompt_fragment=system_prompt_fragment,
            prompt_append_fragment=prompt_append_fragment,
            default_capability_bundle_keys=default_capability_bundle_keys,
        ):
            return active_profile

        next_version = (existing_versions[0].version + 1) if existing_versions else 1
        if active_profile is not None:
            active_profile.status = _DEPRECATED_STATUS
            self.session.flush()
            self.session.add(
                PersonaProjectionEvent(
                    persona_profile_key=profile_key,
                    persona_profile_version=active_profile.version,
                    legacy_entity_type=legacy_entity_type,
                    legacy_entity_key=legacy_entity_key,
                    legacy_source_version=active_profile.legacy_source_version
                    or legacy_source_version,
                    operation="deprecate",
                    actor=_PROJECTION_ACTOR,
                    note=f"Superseded by imported persona profile version {next_version}",
                )
            )

        projected_profile = PersonaProfile(
            key=profile_key,
            version=next_version,
            origin=_IMPORTED_ORIGIN,
            status=_ACTIVE_STATUS,
            kind=kind,
            display_name=display_name,
            enabled=enabled,
            handle=handle,
            canonical_target_id=canonical_target_id,
            parent_profile_key=parent_profile.key if parent_profile is not None else None,
            parent_profile_version=parent_profile.version if parent_profile is not None else None,
            legacy_entity_type=legacy_entity_type,
            legacy_entity_key=legacy_entity_key,
            legacy_source_version=legacy_source_version,
            system_prompt_fragment=system_prompt_fragment,
            prompt_append_fragment=prompt_append_fragment,
            default_capability_bundle_keys=default_capability_bundle_keys,
        )
        self.persona_repo.add(projected_profile)
        self.session.flush()
        self.session.add(
            PersonaProjectionEvent(
                persona_profile_key=profile_key,
                persona_profile_version=projected_profile.version,
                legacy_entity_type=legacy_entity_type,
                legacy_entity_key=legacy_entity_key,
                legacy_source_version=legacy_source_version,
                operation="create" if not existing_versions else "reproject",
                actor=_PROJECTION_ACTOR,
                note=(
                    f"Projected imported persona profile from legacy {legacy_entity_type} "
                    f"{legacy_entity_key} version {legacy_source_version}"
                ),
            )
        )
        return projected_profile

    def _archive_imported_profile(
        self,
        *,
        legacy_entity_type: str,
        legacy_entity_key: str,
        profile_key: str,
    ) -> PersonaProfile | None:
        active_profile = self.persona_repo.get_active_by_key(profile_key, origin=_IMPORTED_ORIGIN)
        if active_profile is None:
            return None

        active_profile.status = _ARCHIVED_STATUS
        self.session.flush()
        self.session.add(
            PersonaProjectionEvent(
                persona_profile_key=profile_key,
                persona_profile_version=active_profile.version,
                legacy_entity_type=legacy_entity_type,
                legacy_entity_key=legacy_entity_key,
                legacy_source_version=active_profile.legacy_source_version or 1,
                operation="archive",
                actor=_PROJECTION_ACTOR,
                note=(
                    f"Archived imported persona profile due to legacy {legacy_entity_type} "
                    f"{legacy_entity_key} deletion"
                ),
            )
        )
        return active_profile

    @staticmethod
    def _profile_matches_projection(
        profile: PersonaProfile,
        *,
        display_name: str,
        enabled: bool,
        handle: str | None,
        canonical_target_id: str,
        parent_profile: PersonaProfile | None,
        legacy_entity_type: str,
        legacy_entity_key: str,
        legacy_source_version: int,
        system_prompt_fragment: str,
        prompt_append_fragment: str,
        default_capability_bundle_keys: list[str],
    ) -> bool:
        return (
            profile.display_name == display_name
            and profile.enabled == enabled
            and profile.handle == handle
            and profile.canonical_target_id == canonical_target_id
            and profile.parent_profile_key
            == (parent_profile.key if parent_profile is not None else None)
            and profile.parent_profile_version
            == (parent_profile.version if parent_profile is not None else None)
            and profile.legacy_entity_type == legacy_entity_type
            and profile.legacy_entity_key == legacy_entity_key
            and profile.legacy_source_version == legacy_source_version
            and profile.system_prompt_fragment == system_prompt_fragment
            and profile.prompt_append_fragment == prompt_append_fragment
            and profile.default_capability_bundle_keys == default_capability_bundle_keys
        )

    @staticmethod
    def _role_profile_key(role_key: str) -> str:
        return f"imported.role.{role_key}"

    @staticmethod
    def _role_canonical_target_id(role_key: str) -> str:
        return f"role:{role_key}"

    @staticmethod
    def _character_profile_key(handle: str) -> str:
        return f"imported.character.{handle}"

    @staticmethod
    def _character_canonical_target_id(handle: str) -> str:
        return f"character:{handle}"
