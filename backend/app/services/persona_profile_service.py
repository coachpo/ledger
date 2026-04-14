from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error
from app.models.persona_profile import PersonaProfile
from app.repositories.persona_profile import PersonaProfileRepository
from app.schemas.runtime import PersonaProfileKind, SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    PersonaProfileDraftCreate,
    PersonaProfileDraftUpdate,
    PersonaProfileListRead,
    PersonaProfileRead,
    StudioVersionHistoryItem,
    StudioVersionHistoryRead,
)


class PersonaProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PersonaProfileRepository(session)

    def list_profiles(
        self,
        *,
        origin: SpecOrigin | None = None,
        status_filter: SpecLifecycleStatus | None = None,
        kind: PersonaProfileKind | None = None,
        enabled: bool | None = None,
    ) -> PersonaProfileListRead:
        items = self.repository.list_latest_versions(
            origin=origin.value if origin is not None else None,
            status=status_filter.value if status_filter is not None else None,
            kind=kind.value if kind is not None else None,
            enabled=enabled,
        )
        return PersonaProfileListRead(
            items=[PersonaProfileRead.model_validate(item) for item in items]
        )

    def get_profile(self, persona_key: str) -> PersonaProfileRead:
        return PersonaProfileRead.model_validate(self._get_latest_model(persona_key))

    def list_versions(self, persona_key: str) -> StudioVersionHistoryRead:
        versions = self.repository.list_versions(persona_key)
        if not versions:
            raise not_found_error("Persona profile")
        return StudioVersionHistoryRead(
            items=[StudioVersionHistoryItem.model_validate(item) for item in versions]
        )

    def get_version(self, persona_key: str, version: int) -> PersonaProfileRead:
        return PersonaProfileRead.model_validate(self._get_model(persona_key, version))

    def create_draft(self, payload: PersonaProfileDraftCreate) -> PersonaProfileRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="persona_profile_duplicate_draft",
                message="A draft persona profile already exists for this key",
            )

        self._ensure_key_editable(payload.key)
        self._ensure_handle_available(payload.handle, key=payload.key)

        profile = PersonaProfile(
            key=payload.key,
            version=self._next_version(payload.key),
            origin="managed",
            status="DRAFT",
            kind="managed_persona",
            display_name=payload.display_name,
            enabled=payload.enabled,
            handle=payload.handle,
            canonical_target_id=self._canonical_target_id(payload.key),
            parent_profile_key=None,
            parent_profile_version=None,
            legacy_entity_type=None,
            legacy_entity_key=None,
            legacy_source_version=None,
            system_prompt_fragment=payload.system_prompt_fragment,
            prompt_append_fragment=payload.prompt_append_fragment,
            default_capability_bundle_keys=payload.default_capability_bundle_keys,
        )
        try:
            self.repository.add(profile)
            self.session.commit()
            self.session.refresh(profile)
        except Exception:
            self.session.rollback()
            raise
        return PersonaProfileRead.model_validate(profile)

    def update_draft(
        self,
        persona_key: str,
        version: int,
        payload: PersonaProfileDraftUpdate,
    ) -> PersonaProfileRead:
        profile = self._get_managed_model(persona_key, version)
        self._ensure_status(profile, "DRAFT", action="patch")

        if payload.display_name is not None:
            profile.display_name = payload.display_name
        if payload.enabled is not None:
            profile.enabled = payload.enabled
        if "handle" in payload.model_fields_set:
            self._ensure_handle_available(payload.handle, key=profile.key, current_id=profile.id)
            profile.handle = payload.handle
        if "system_prompt_fragment" in payload.model_fields_set:
            profile.system_prompt_fragment = payload.system_prompt_fragment or ""
        if "prompt_append_fragment" in payload.model_fields_set:
            profile.prompt_append_fragment = payload.prompt_append_fragment or ""
        if payload.default_capability_bundle_keys is not None:
            profile.default_capability_bundle_keys = payload.default_capability_bundle_keys

        try:
            self.session.commit()
            self.session.refresh(profile)
        except Exception:
            self.session.rollback()
            raise
        return PersonaProfileRead.model_validate(profile)

    def activate(self, persona_key: str, version: int) -> PersonaProfileRead:
        profile = self._get_managed_model(persona_key, version)
        self._ensure_status(profile, "DRAFT", action="activate")

        current_active = self.repository.get_active_by_key(profile.key)
        try:
            if current_active is not None and current_active.id != profile.id:
                current_active.status = "DEPRECATED"
                self.session.flush()
            profile.status = "ACTIVE"
            self.session.commit()
            self.session.refresh(profile)
        except Exception:
            self.session.rollback()
            raise
        return PersonaProfileRead.model_validate(profile)

    def deprecate(self, persona_key: str, version: int) -> PersonaProfileRead:
        profile = self._get_managed_model(persona_key, version)
        self._ensure_status(profile, "ACTIVE", action="deprecate")

        try:
            profile.status = "DEPRECATED"
            self.session.commit()
            self.session.refresh(profile)
        except Exception:
            self.session.rollback()
            raise
        return PersonaProfileRead.model_validate(profile)

    def archive(self, persona_key: str, version: int) -> PersonaProfileRead:
        profile = self._get_managed_model(persona_key, version)
        if profile.status not in {
            "DRAFT",
            "DEPRECATED",
        }:
            raise business_rule_error(
                "persona_profile_invalid_archive_transition",
                "Only draft or deprecated persona profiles can be archived",
            )

        try:
            profile.status = "ARCHIVED"
            self.session.commit()
            self.session.refresh(profile)
        except Exception:
            self.session.rollback()
            raise
        return PersonaProfileRead.model_validate(profile)

    def _get_latest_model(self, persona_key: str) -> PersonaProfile:
        profiles = self.repository.list_versions(persona_key)
        if not profiles:
            raise not_found_error("Persona profile")
        return profiles[0]

    def _get_model(self, persona_key: str, version: int) -> PersonaProfile:
        profile = self.repository.get_by_key_version(persona_key, version)
        if profile is None:
            raise not_found_error("Persona profile")
        return profile

    def _get_managed_model(self, persona_key: str, version: int) -> PersonaProfile:
        profile = self._get_model(persona_key, version)
        if profile.origin != "managed":
            raise business_rule_error(
                "persona_profile_origin_immutable",
                "Only managed persona profiles can be changed through Studio APIs",
            )
        return profile

    def _ensure_key_editable(self, key: str) -> None:
        versions = self.repository.list_versions(key)
        if not versions:
            return
        if any(profile.origin != "managed" for profile in versions):
            raise business_rule_error(
                "persona_profile_origin_immutable",
                "Imported and seeded persona profile keys are read-only through Studio APIs",
            )

    def _ensure_handle_available(
        self,
        handle: str | None,
        *,
        key: str,
        current_id: int | None = None,
    ) -> None:
        if handle is None:
            return
        for conflict in (
            self.repository.get_active_by_handle(handle),
            self.repository.get_draft_by_handle(handle),
        ):
            if conflict is None:
                continue
            if conflict.key == key or conflict.id == current_id:
                continue
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="persona_profile_duplicate_handle",
                message="Persona handle already exists",
            )

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    @staticmethod
    def _canonical_target_id(key: str) -> str:
        return f"persona:{key}"

    @staticmethod
    def _ensure_status(
        profile: PersonaProfile,
        expected: str,
        *,
        action: str,
    ) -> None:
        if profile.status != expected:
            raise business_rule_error(
                f"persona_profile_invalid_{action}_transition",
                f"Only {expected} persona profiles can be used for this action",
            )


__all__ = ["PersonaProfileService"]
