from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error
from app.models.agent_spec import AgentSpec
from app.repositories.agent_spec import AgentSpecRepository
from app.schemas.runtime import SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    AgentSpecDraftCreate,
    AgentSpecDraftUpdate,
    AgentSpecListRead,
    AgentSpecRead,
)


class AgentSpecService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AgentSpecRepository(session)

    def list_specs(
        self,
        *,
        origin: SpecOrigin | None = None,
        status_filter: SpecLifecycleStatus | None = None,
    ) -> AgentSpecListRead:
        items = self.repository.list_latest_versions(
            origin=origin.value if origin is not None else None,
            status=status_filter.value if status_filter is not None else None,
        )
        return AgentSpecListRead(items=[AgentSpecRead.model_validate(item) for item in items])

    def get_spec(self, spec_id: int) -> AgentSpecRead:
        return AgentSpecRead.model_validate(self._get_model(spec_id))

    def create_draft(self, payload: AgentSpecDraftCreate) -> AgentSpecRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="agent_spec_duplicate_draft",
                message="A draft agent spec already exists for this key",
            )

        next_version = self._next_version(payload.key)
        spec = AgentSpec(
            key=payload.key,
            version=next_version,
            origin=SpecOrigin.MANAGED.value,
            status=SpecLifecycleStatus.DRAFT.value,
            name=payload.name,
            instructions=payload.instructions,
            model_policy=payload.model_policy,
            final_output_contract=(
                payload.final_output_contract.model_dump(by_alias=True)
                if payload.final_output_contract is not None
                else None
            ),
            default_capability_bundle_keys=payload.default_capability_bundle_keys,
            default_persona_profile_keys=payload.default_persona_profile_keys,
        )
        try:
            self.repository.add(spec)
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return AgentSpecRead.model_validate(spec)

    def update_draft(self, spec_id: int, payload: AgentSpecDraftUpdate) -> AgentSpecRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.DRAFT, action="patch")

        if payload.name is not None:
            spec.name = payload.name
        if payload.instructions is not None:
            spec.instructions = payload.instructions
        if payload.model_policy is not None:
            spec.model_policy = payload.model_policy
        if "final_output_contract" in payload.model_fields_set:
            spec.final_output_contract = (
                payload.final_output_contract.model_dump(by_alias=True)
                if payload.final_output_contract is not None
                else None
            )
        if payload.default_capability_bundle_keys is not None:
            spec.default_capability_bundle_keys = payload.default_capability_bundle_keys
        if payload.default_persona_profile_keys is not None:
            spec.default_persona_profile_keys = payload.default_persona_profile_keys

        try:
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return AgentSpecRead.model_validate(spec)

    def activate(self, spec_id: int) -> AgentSpecRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.DRAFT, action="activate")

        current_active = self.repository.get_active_by_key(spec.key)
        try:
            if current_active is not None and current_active.id != spec.id:
                current_active.status = SpecLifecycleStatus.DEPRECATED.value
                self.session.flush()
            spec.status = SpecLifecycleStatus.ACTIVE.value
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return AgentSpecRead.model_validate(spec)

    def deprecate(self, spec_id: int) -> AgentSpecRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.ACTIVE, action="deprecate")

        try:
            spec.status = SpecLifecycleStatus.DEPRECATED.value
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return AgentSpecRead.model_validate(spec)

    def archive(self, spec_id: int) -> AgentSpecRead:
        spec = self._get_managed_model(spec_id)
        if spec.status not in {
            SpecLifecycleStatus.DRAFT.value,
            SpecLifecycleStatus.DEPRECATED.value,
        }:
            raise business_rule_error(
                "agent_spec_invalid_archive_transition",
                "Only draft or deprecated agent specs can be archived",
            )

        try:
            spec.status = SpecLifecycleStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return AgentSpecRead.model_validate(spec)

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, spec_id: int) -> AgentSpec:
        spec = self.repository.get(spec_id)
        if spec is None:
            raise not_found_error("Agent spec")
        return spec

    def _get_managed_model(self, spec_id: int) -> AgentSpec:
        spec = self._get_model(spec_id)
        if spec.origin != SpecOrigin.MANAGED.value:
            raise business_rule_error(
                "agent_spec_origin_immutable",
                "Only managed agent specs can be changed through /api/v2",
            )
        return spec

    @staticmethod
    def _ensure_status(spec: AgentSpec, expected: SpecLifecycleStatus, *, action: str) -> None:
        if spec.status != expected.value:
            raise business_rule_error(
                f"agent_spec_invalid_{action}_transition",
                f"Only {expected.value} agent specs can be used for this action",
            )


__all__ = ["AgentSpecService"]
