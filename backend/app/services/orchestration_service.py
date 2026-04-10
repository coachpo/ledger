from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error
from app.langgraph.seeds import SEEDED_BUILTIN_RESERVED_TARGETS, SEEDED_BUILTIN_SPECS
from app.models.orchestration_character import OrchestrationCharacter
from app.models.orchestration_role import OrchestrationRole
from app.repositories.orchestration_character import OrchestrationCharacterRepository
from app.repositories.orchestration_role import OrchestrationRoleRepository
from app.schemas.orchestration import (
    MentionCatalogItem,
    MentionCatalogRead,
    OrchestrationCharacterCreate,
    OrchestrationCharacterRead,
    OrchestrationCharacterUpdate,
    OrchestrationRoleCreate,
    OrchestrationRoleRead,
    OrchestrationRoleUpdate,
)


class OrchestrationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.role_repo = OrchestrationRoleRepository(session)
        self.character_repo = OrchestrationCharacterRepository(session)

    def list_roles(self) -> list[OrchestrationRoleRead]:
        return [OrchestrationRoleRead.model_validate(role) for role in self.role_repo.list_all()]

    def get_role(self, role_id: int) -> OrchestrationRoleRead:
        return OrchestrationRoleRead.model_validate(self._get_role_model(role_id))

    def create_role(self, payload: OrchestrationRoleCreate) -> OrchestrationRoleRead:
        if self.role_repo.get_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="duplicate_role_key",
                message="Role key already exists",
            )
        if self.role_repo.get_by_name(payload.name) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="duplicate_role_name",
                message="Role name already exists",
            )
        role = OrchestrationRole(
            key=payload.key,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            enabled=payload.enabled,
        )
        self.role_repo.add(role)
        self.session.commit()
        self.session.refresh(role)
        return OrchestrationRoleRead.model_validate(role)

    def update_role(self, role_id: int, payload: OrchestrationRoleUpdate) -> OrchestrationRoleRead:
        role = self._get_role_model(role_id)
        updated = False
        if payload.name is not None:
            duplicate_role = self.role_repo.get_by_name(payload.name)
            if duplicate_role is not None and duplicate_role.id != role.id:
                raise ApiError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="duplicate_role_name",
                    message="Role name already exists",
                )
            role.name = payload.name
            updated = True
        if payload.description is not None or "description" in payload.model_fields_set:
            role.description = payload.description
            updated = True
        if payload.system_prompt is not None:
            role.system_prompt = payload.system_prompt
            updated = True
        if payload.enabled is not None:
            role.enabled = payload.enabled
            updated = True
        if updated:
            role.version += 1
        self.session.commit()
        self.session.refresh(role)
        return OrchestrationRoleRead.model_validate(role)

    def delete_role(self, role_id: int) -> None:
        role = self._get_role_model(role_id)
        if role.characters:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="role_in_use",
                message="Role is in use",
            )
        self.role_repo.delete(role)
        self.session.commit()

    def list_characters(self) -> list[OrchestrationCharacterRead]:
        return [
            OrchestrationCharacterRead.model_validate(character)
            for character in self.character_repo.list_all()
        ]

    def get_character(self, character_id: int) -> OrchestrationCharacterRead:
        return OrchestrationCharacterRead.model_validate(self._get_character_model(character_id))

    def create_character(self, payload: OrchestrationCharacterCreate) -> OrchestrationCharacterRead:
        self._validate_character_handle(payload.handle)
        role = self._get_role_model(payload.role_id)
        self._ensure_role_enabled(role)
        if self.character_repo.get_by_handle(payload.handle) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="duplicate_character_handle",
                message="Character handle already exists",
            )
        character = OrchestrationCharacter(
            handle=payload.handle,
            display_name=payload.display_name,
            description=payload.description,
            role_id=payload.role_id,
            prompt_append=payload.prompt_append,
            enabled=payload.enabled,
        )
        self.character_repo.add(character)
        self.session.commit()
        self.session.refresh(character)
        return OrchestrationCharacterRead.model_validate(character)

    def update_character(
        self, character_id: int, payload: OrchestrationCharacterUpdate
    ) -> OrchestrationCharacterRead:
        character = self._get_character_model(character_id)
        updated = False
        if payload.role_id is not None:
            role = self._get_role_model(payload.role_id)
            self._ensure_role_enabled(role)
            character.role_id = payload.role_id
            updated = True
        if payload.display_name is not None:
            character.display_name = payload.display_name
            updated = True
        if payload.description is not None or "description" in payload.model_fields_set:
            character.description = payload.description
            updated = True
        if payload.prompt_append is not None or "prompt_append" in payload.model_fields_set:
            character.prompt_append = payload.prompt_append
            updated = True
        if payload.enabled is not None:
            character.enabled = payload.enabled
            updated = True
        if updated:
            character.version += 1
        self.session.commit()
        self.session.refresh(character)
        return OrchestrationCharacterRead.model_validate(character)

    def delete_character(self, character_id: int) -> None:
        character = self._get_character_model(character_id)
        self.character_repo.delete(character)
        self.session.commit()

    def list_mention_catalog(self) -> MentionCatalogRead:
        catalog = [
            MentionCatalogItem(
                handle=builtin.handle,
                canonical_target_id=builtin.canonical_target_id,
                kind="builtin",
                display_name=builtin.display_name,
                description=builtin.description,
            )
            for builtin in SEEDED_BUILTIN_SPECS
        ]
        for character in self.character_repo.list_enabled_for_catalog():
            catalog.append(
                MentionCatalogItem(
                    handle=character.handle,
                    canonical_target_id=f"character:{character.handle}",
                    kind="character",
                    display_name=character.display_name,
                    description=character.description,
                    role_key=character.role.key,
                )
            )
        return MentionCatalogRead(targets=catalog)

    def _get_role_model(self, role_id: int) -> OrchestrationRole:
        role = self.role_repo.get(role_id)
        if role is None:
            raise not_found_error("Role")
        return role

    def _get_character_model(self, character_id: int) -> OrchestrationCharacter:
        character = self.character_repo.get(character_id)
        if character is None:
            raise not_found_error("Character")
        return character

    @staticmethod
    def _ensure_role_enabled(role: OrchestrationRole) -> None:
        if not role.enabled:
            raise business_rule_error("disabled_role", "Selected role is disabled")

    @staticmethod
    def _validate_character_handle(handle: str) -> None:
        if handle in SEEDED_BUILTIN_RESERVED_TARGETS:
            raise business_rule_error("reserved_character_handle", "Character handle is reserved")
