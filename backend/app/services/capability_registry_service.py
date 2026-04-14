from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.repositories.capability_registry_entry import CapabilityRegistryEntryRepository
from app.schemas.runtime import ApprovalMode, CapabilityType, SpecLifecycleStatus, SpecOrigin
from app.schemas.studio import (
    CapabilityBundleMemberWrite,
    CapabilityRegistryEntryDraftCreate,
    CapabilityRegistryEntryDraftUpdate,
    CapabilityRegistryEntryListRead,
    CapabilityRegistryEntryRead,
)

_CONNECTOR_LIFECYCLES = {"placeholder", "approved"}


class CapabilityRegistryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CapabilityRegistryEntryRepository(session)

    def list_specs(
        self,
        *,
        origin: SpecOrigin | None = None,
        status_filter: SpecLifecycleStatus | None = None,
        capability_type: CapabilityType | None = None,
    ) -> CapabilityRegistryEntryListRead:
        items = self.repository.list_latest_versions(
            origin=origin.value if origin is not None else None,
            status=status_filter.value if status_filter is not None else None,
            capability_type=capability_type.value if capability_type is not None else None,
        )
        return CapabilityRegistryEntryListRead(
            items=[CapabilityRegistryEntryRead.model_validate(item) for item in items]
        )

    def get_spec(self, spec_id: int) -> CapabilityRegistryEntryRead:
        return CapabilityRegistryEntryRead.model_validate(self._get_model(spec_id))

    def create_draft(
        self, payload: CapabilityRegistryEntryDraftCreate
    ) -> CapabilityRegistryEntryRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="capability_duplicate_draft",
                message="A draft capability already exists for this key",
            )
        self._ensure_key_not_seeded(payload.key)

        state = self._build_create_state(payload)
        spec = CapabilityRegistryEntry(
            key=payload.key,
            version=self._next_version(payload.key),
            origin=SpecOrigin.MANAGED.value,
            status=SpecLifecycleStatus.DRAFT.value,
            **self._build_model_kwargs(state),
        )
        try:
            self.repository.add(spec)
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return CapabilityRegistryEntryRead.model_validate(spec)

    def update_draft(
        self,
        spec_id: int,
        payload: CapabilityRegistryEntryDraftUpdate,
    ) -> CapabilityRegistryEntryRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.DRAFT, action="patch")

        state = self._build_update_state(spec, payload)
        self._apply_state(spec, state)
        try:
            self.session.commit()
            self.session.refresh(spec)
        except Exception:
            self.session.rollback()
            raise
        return CapabilityRegistryEntryRead.model_validate(spec)

    def activate(self, spec_id: int) -> CapabilityRegistryEntryRead:
        spec = self._get_managed_model(spec_id)
        self._ensure_status(spec, SpecLifecycleStatus.DRAFT, action="activate")
        self._ensure_key_not_seeded(spec.key)
        self._validate_state(
            capability_type=CapabilityType(spec.type),
            display_name=spec.display_name,
            description=spec.description,
            approval_mode=ApprovalMode(spec.approval_mode),
            adapter_key=spec.adapter_key,
            config_schema=spec.config_schema,
            bundle_members=spec.bundle_members,
            transport=spec.transport,
            lifecycle=spec.lifecycle,
        )

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
        return CapabilityRegistryEntryRead.model_validate(spec)

    def _build_create_state(self, payload: CapabilityRegistryEntryDraftCreate) -> dict[str, Any]:
        return self._validate_state(
            capability_type=payload.type,
            display_name=payload.display_name,
            description=payload.description,
            approval_mode=payload.approval_mode,
            adapter_key=payload.adapter_key,
            config_schema=payload.config_schema,
            bundle_members=payload.bundle_members,
            transport=payload.transport,
            lifecycle=payload.lifecycle,
        )

    def _build_update_state(
        self,
        spec: CapabilityRegistryEntry,
        payload: CapabilityRegistryEntryDraftUpdate,
    ) -> dict[str, Any]:
        current_type = CapabilityType(spec.type)
        next_type = payload.type or current_type
        type_changed = next_type != current_type
        fields = payload.model_fields_set

        approval_mode: ApprovalMode | None
        if "approval_mode" in fields:
            approval_mode = payload.approval_mode
        elif type_changed:
            approval_mode = None
        else:
            approval_mode = ApprovalMode(spec.approval_mode)

        adapter_key = spec.adapter_key
        if "adapter_key" in fields:
            adapter_key = payload.adapter_key
        elif type_changed and next_type == CapabilityType.BUNDLE:
            adapter_key = None

        config_schema = spec.config_schema
        if "config_schema" in fields:
            config_schema = payload.config_schema
        elif type_changed and next_type == CapabilityType.BUNDLE:
            config_schema = None

        bundle_members: list[CapabilityBundleMemberWrite] | list[dict[str, Any]] | None = (
            spec.bundle_members
        )
        if "bundle_members" in fields:
            bundle_members = payload.bundle_members
        elif type_changed and next_type != CapabilityType.BUNDLE:
            bundle_members = None

        transport = spec.transport
        if "transport" in fields:
            transport = payload.transport
        elif type_changed and next_type != CapabilityType.CONNECTOR:
            transport = None

        lifecycle = spec.lifecycle
        if "lifecycle" in fields:
            lifecycle = payload.lifecycle
        elif type_changed and next_type != CapabilityType.CONNECTOR:
            lifecycle = None

        return self._validate_state(
            capability_type=next_type,
            display_name=payload.display_name or spec.display_name,
            description=payload.description or spec.description,
            approval_mode=approval_mode,
            adapter_key=adapter_key,
            config_schema=config_schema,
            bundle_members=bundle_members,
            transport=transport,
            lifecycle=lifecycle,
        )

    def _validate_state(
        self,
        *,
        capability_type: CapabilityType,
        display_name: str,
        description: str,
        approval_mode: ApprovalMode | None,
        adapter_key: str | None,
        config_schema: dict[str, Any] | None,
        bundle_members: list[CapabilityBundleMemberWrite] | list[dict[str, Any]] | None,
        transport: str | None,
        lifecycle: str | None,
    ) -> dict[str, Any]:
        resolved_approval_mode = self._resolve_approval_mode(
            capability_type=capability_type,
            approval_mode=approval_mode,
        )
        if capability_type == CapabilityType.BUNDLE:
            if adapter_key is not None or config_schema is not None:
                raise business_rule_error(
                    "capability_bundle_fields_invalid",
                    "Bundles cannot include adapter or config schema fields",
                )
            validated_members = self._validate_bundle_members(bundle_members)
            return {
                "type": capability_type.value,
                "display_name": display_name,
                "description": description,
                "approval_mode": resolved_approval_mode.value,
                "adapter_key": None,
                "config_schema": None,
                "bundle_members": validated_members,
                "transport": None,
                "lifecycle": None,
            }

        if bundle_members is not None:
            raise business_rule_error(
                "capability_bundle_members_invalid",
                "Only bundle capabilities can define bundle members",
            )
        if adapter_key is None or config_schema is None:
            raise business_rule_error(
                "capability_adapter_config_required",
                "Non-bundle capabilities require adapterKey and configSchema",
            )
        if capability_type == CapabilityType.CONNECTOR:
            if transport is None or lifecycle is None:
                raise business_rule_error(
                    "capability_connector_fields_required",
                    "Connector capabilities require transport and lifecycle",
                )
            if lifecycle not in _CONNECTOR_LIFECYCLES:
                raise business_rule_error(
                    "capability_connector_lifecycle_invalid",
                    "Connector lifecycle must be either 'placeholder' or 'approved'",
                )
        elif transport is not None or lifecycle is not None:
            raise business_rule_error(
                "capability_connector_fields_invalid",
                "Only connector capabilities can include transport or lifecycle",
            )

        return {
            "type": capability_type.value,
            "display_name": display_name,
            "description": description,
            "approval_mode": resolved_approval_mode.value,
            "adapter_key": adapter_key,
            "config_schema": config_schema,
            "bundle_members": None,
            "transport": transport if capability_type == CapabilityType.CONNECTOR else None,
            "lifecycle": lifecycle if capability_type == CapabilityType.CONNECTOR else None,
        }

    def _resolve_approval_mode(
        self,
        *,
        capability_type: CapabilityType,
        approval_mode: ApprovalMode | None,
    ) -> ApprovalMode:
        default_mode = (
            ApprovalMode.REQUIRED
            if capability_type == CapabilityType.CONNECTOR
            else ApprovalMode.NOT_REQUIRED
        )
        selected_mode = approval_mode or default_mode
        if capability_type == CapabilityType.CONNECTOR and selected_mode != ApprovalMode.REQUIRED:
            raise business_rule_error(
                "capability_invalid_approval_override",
                "Connector capabilities cannot relax required approval",
            )
        if capability_type == CapabilityType.BUNDLE and selected_mode != ApprovalMode.NOT_REQUIRED:
            raise business_rule_error(
                "capability_bundle_approval_mode_invalid",
                "Bundle capabilities cannot require approval",
            )
        return selected_mode

    def _validate_bundle_members(
        self,
        bundle_members: list[CapabilityBundleMemberWrite] | list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if bundle_members is None:
            raise business_rule_error(
                "capability_bundle_members_required",
                "Bundle capabilities require bundleMembers",
            )

        validated_members: list[dict[str, Any]] = []
        for raw_member in bundle_members:
            member = CapabilityBundleMemberWrite.model_validate(raw_member)
            entry = self.repository.get_by_key_version(
                member.capability_key, member.capability_version
            )
            if entry is None:
                raise business_rule_error(
                    "capability_bundle_member_not_found",
                    (
                        f"Bundle member {member.capability_key!r} v{member.capability_version} "
                        "was not found"
                    ),
                )
            if (
                entry.type == CapabilityType.BUNDLE.value
                or member.member_type == CapabilityType.BUNDLE
            ):
                raise business_rule_error(
                    "capability_nested_bundle_member",
                    "Bundle capabilities cannot contain other bundles",
                )
            if entry.type != member.member_type.value:
                raise business_rule_error(
                    "capability_bundle_member_type_mismatch",
                    (
                        f"Bundle member {member.capability_key!r} v{member.capability_version} "
                        f"is a {entry.type}, not a {member.member_type.value}"
                    ),
                )
            validated_members.append(
                {
                    "key": member.capability_key,
                    "type": member.member_type.value,
                    "version": member.capability_version,
                }
            )
        return validated_members

    @staticmethod
    def _build_model_kwargs(state: dict[str, Any]) -> dict[str, Any]:
        model_kwargs = dict(state)
        if model_kwargs.get("bundle_members") is None:
            model_kwargs.pop("bundle_members", None)
        return model_kwargs

    def _apply_state(self, spec: CapabilityRegistryEntry, state: dict[str, Any]) -> None:
        spec.type = str(state["type"])
        spec.display_name = str(state["display_name"])
        spec.description = str(state["description"])
        spec.approval_mode = str(state["approval_mode"])
        spec.adapter_key = state["adapter_key"]
        spec.config_schema = state["config_schema"]
        spec.bundle_members = state["bundle_members"]
        spec.transport = state["transport"]
        spec.lifecycle = state["lifecycle"]

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _ensure_key_not_seeded(self, key: str) -> None:
        if self.repository.has_origin(key, SpecOrigin.SEEDED.value):
            raise business_rule_error(
                "capability_seeded_key_reserved",
                "Seeded capability keys are reserved and cannot be managed through /api/v2",
            )

    def _get_model(self, spec_id: int) -> CapabilityRegistryEntry:
        spec = self.repository.get(spec_id)
        if spec is None:
            raise not_found_error("Capability")
        return spec

    def _get_managed_model(self, spec_id: int) -> CapabilityRegistryEntry:
        spec = self._get_model(spec_id)
        if spec.origin != SpecOrigin.MANAGED.value:
            raise business_rule_error(
                "capability_origin_immutable",
                "Only managed capabilities can be changed through /api/v2",
            )
        return spec

    @staticmethod
    def _ensure_status(
        spec: CapabilityRegistryEntry,
        expected: SpecLifecycleStatus,
        *,
        action: str,
    ) -> None:
        if spec.status != expected.value:
            raise business_rule_error(
                f"capability_invalid_{action}_transition",
                f"Only {expected.value} capabilities can be used for this action",
            )


__all__ = ["CapabilityRegistryService"]
