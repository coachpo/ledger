from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error
from app.models.workflow_spec import WorkflowSpec
from app.repositories.workflow_spec import WorkflowSpecRepository
from app.schemas.runtime import SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    WorkflowSpecDraftCreate,
    WorkflowSpecDraftUpdate,
    WorkflowSpecListRead,
    WorkflowSpecRead,
)


class WorkflowSpecService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = WorkflowSpecRepository(session)

    def list_specs(
        self,
        *,
        origin: SpecOrigin | None = None,
        status_filter: SpecLifecycleStatus | None = None,
    ) -> WorkflowSpecListRead:
        items = self.repository.list_latest_versions(
            origin=origin.value if origin is not None else SpecOrigin.MANAGED.value,
            status=status_filter.value if status_filter is not None else None,
        )
        return WorkflowSpecListRead(items=[WorkflowSpecRead.model_validate(item) for item in items])

    def get_spec(self, spec_id: int) -> WorkflowSpecRead:
        return WorkflowSpecRead.model_validate(self._get_model(spec_id))

    def create_draft(self, payload: WorkflowSpecDraftCreate) -> WorkflowSpecRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_spec_duplicate_draft",
                message="A draft workflow spec already exists for this key",
            )

        next_version = self._next_version(payload.key)
        spec = WorkflowSpec(
            key=payload.key,
            version=next_version,
            origin=SpecOrigin.MANAGED.value,
            status=SpecLifecycleStatus.DRAFT.value,
            name=payload.name,
            graph_definition=payload.graph_definition,
            final_output_contract=payload.final_output_contract.model_dump(by_alias=True),
            mention_policy=payload.mention_policy.model_dump(by_alias=True),
            execution_mode=payload.execution_mode,
            default_tool_ids=payload.default_tool_ids,
            allowed_capability_bundle_keys=payload.allowed_capability_bundle_keys,
            connector_ids=payload.connector_ids,
            review_mode=payload.review_mode,
            approval_policy_overrides=[
                override.model_dump(by_alias=True) for override in payload.approval_policy_overrides
            ],
        )
        try:
            self.repository.add(spec)
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return WorkflowSpecRead.model_validate(spec)

    def update_draft(self, spec_id: int, payload: WorkflowSpecDraftUpdate) -> WorkflowSpecRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.DRAFT, action="patch")

        if payload.name is not None:
            spec.name = payload.name
        if payload.graph_definition is not None:
            spec.graph_definition = payload.graph_definition
        if payload.final_output_contract is not None:
            spec.final_output_contract = payload.final_output_contract.model_dump(by_alias=True)
        if payload.mention_policy is not None:
            spec.mention_policy = payload.mention_policy.model_dump(by_alias=True)
        if "execution_mode" in payload.model_fields_set:
            spec.execution_mode = payload.execution_mode
        if payload.default_tool_ids is not None:
            spec.default_tool_ids = payload.default_tool_ids
        if payload.allowed_capability_bundle_keys is not None:
            spec.allowed_capability_bundle_keys = payload.allowed_capability_bundle_keys
        if payload.connector_ids is not None:
            spec.connector_ids = payload.connector_ids
        if "review_mode" in payload.model_fields_set:
            spec.review_mode = payload.review_mode
        if payload.approval_policy_overrides is not None:
            spec.approval_policy_overrides = [
                override.model_dump(by_alias=True) for override in payload.approval_policy_overrides
            ]

        try:
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return WorkflowSpecRead.model_validate(spec)

    def activate(self, spec_id: int) -> WorkflowSpecRead:
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
        return WorkflowSpecRead.model_validate(spec)

    def deprecate(self, spec_id: int) -> WorkflowSpecRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.ACTIVE, action="deprecate")

        try:
            spec.status = SpecLifecycleStatus.DEPRECATED.value
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return WorkflowSpecRead.model_validate(spec)

    def archive(self, spec_id: int) -> WorkflowSpecRead:
        spec = self._get_managed_model(spec_id)
        if spec.status not in {
            SpecLifecycleStatus.DRAFT.value,
            SpecLifecycleStatus.DEPRECATED.value,
        }:
            raise business_rule_error(
                "workflow_spec_invalid_archive_transition",
                "Only draft or deprecated workflow specs can be archived",
            )

        try:
            spec.status = SpecLifecycleStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return WorkflowSpecRead.model_validate(spec)

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, spec_id: int) -> WorkflowSpec:
        spec = self.repository.get(spec_id)
        if spec is None:
            raise not_found_error("Workflow spec")
        return spec

    def _get_managed_model(self, spec_id: int) -> WorkflowSpec:
        spec = self._get_model(spec_id)
        if spec.origin != SpecOrigin.MANAGED.value:
            raise business_rule_error(
                "workflow_spec_origin_immutable",
                "Only managed workflow specs can be changed through /api/v2",
            )
        return spec

    @staticmethod
    def _ensure_status(spec: WorkflowSpec, expected: SpecLifecycleStatus, *, action: str) -> None:
        if spec.status != expected.value:
            raise business_rule_error(
                f"workflow_spec_invalid_{action}_transition",
                f"Only {expected.value} workflow specs can be used for this action",
            )


__all__ = ["WorkflowSpecService"]
