from __future__ import annotations

from collections.abc import Sequence

from fastapi import status
from sqlalchemy.orm import Session

from app.agents import (
    ResolvedCapabilityToolset,
    ResolvedTool,
    ToolCatalog,
    ToolCatalogValidationError,
)
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.capability import Capability
from app.repositories.capability import CapabilityRepository
from app.schemas.capability import (
    CapabilityDraftCreate,
    CapabilityDraftUpdate,
    CapabilityListRead,
    CapabilityRead,
    CapabilityStatus,
    CapabilityToolGrantWrite,
)

REPORT_LOOKUP_TOOL_KEY = "ledger.reports.lookup"
REPORT_LOOKUP_ACCESS_DENIED_CODE = "agent_execution_access_denied"
REPORT_LOOKUP_ACCESS_DENIED_MESSAGE = "Agent is not authorized to use ledger.reports.lookup."
POSITION_LOOKUP_TOOL_KEY = "ledger.positions.lookup"
POSITION_LOOKUP_ACCESS_DENIED_CODE = "agent_execution_access_denied"
POSITION_LOOKUP_ACCESS_DENIED_MESSAGE = "Agent is not authorized to use ledger.positions.lookup."


class RuntimeToolGrantError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])


class CapabilityService:
    def __init__(self, session: Session, tool_catalog: ToolCatalog) -> None:
        self.session = session
        self.repository = CapabilityRepository(session)
        self.tool_catalog = tool_catalog

    def list_capabilities(
        self,
        *,
        status_filter: CapabilityStatus | None = None,
    ) -> CapabilityListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None
        )
        return CapabilityListRead(items=[self._to_read_model(item) for item in items])

    def get_capability(self, capability_id: int) -> CapabilityRead:
        return self._to_read_model(self._get_model(capability_id))

    def create_draft(self, payload: CapabilityDraftCreate) -> CapabilityRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="capability_duplicate_draft",
                message="A draft capability already exists for this key",
            )

        tool_grants = self._normalize_tool_grants(payload.tool_grants)
        self._resolve_tool_grants(tool_grants)
        capability = Capability(
            key=payload.key,
            version=self._next_version(payload.key),
            status=CapabilityStatus.DRAFT.value,
            name=payload.name,
            description=payload.description,
            tool_grants=tool_grants,
        )
        try:
            self.repository.add(capability)
            self.session.commit()
            self.session.refresh(capability)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(capability)

    def update_draft(
        self,
        capability_id: int,
        payload: CapabilityDraftUpdate,
    ) -> CapabilityRead:
        source = self._get_model(capability_id)
        self._ensure_status(source, CapabilityStatus.DRAFT, action="patch")

        tool_grants = (
            self._normalize_tool_grants(payload.tool_grants)
            if payload.tool_grants is not None
            else list(source.tool_grants)
        )
        self._resolve_tool_grants(tool_grants)
        updated = Capability(
            key=source.key,
            version=self._next_version(source.key),
            status=CapabilityStatus.DRAFT.value,
            name=payload.name if payload.name is not None else source.name,
            description=(
                payload.description or ""
                if payload.description is not None or "description" in payload.model_fields_set
                else source.description
            ),
            tool_grants=tool_grants,
        )

        try:
            source.status = CapabilityStatus.ARCHIVED.value
            self.session.flush()
            self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(updated)

    def activate(self, capability_id: int) -> CapabilityRead:
        capability = self._get_model(capability_id)
        self._ensure_status(capability, CapabilityStatus.DRAFT, action="activate")
        self._resolve_toolset_model(capability)

        current_published = self.repository.get_published_by_key(capability.key)
        try:
            if current_published is not None and current_published.id != capability.id:
                current_published.status = CapabilityStatus.DEPRECATED.value
                self.session.flush()
            capability.status = CapabilityStatus.PUBLISHED.value
            self.session.commit()
            self.session.refresh(capability)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(capability)

    def archive(self, capability_id: int) -> CapabilityRead:
        capability = self._get_model(capability_id)
        if capability.status == CapabilityStatus.ARCHIVED.value:
            return self._to_read_model(capability)

        try:
            capability.status = CapabilityStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(capability)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(capability)

    def resolve_toolset(self, capability_id: int) -> ResolvedCapabilityToolset:
        return self._resolve_toolset_model(self._get_model(capability_id))

    def resolve_toolset_version(
        self,
        key: str,
        version: int | None,
    ) -> ResolvedCapabilityToolset:
        capability = self.repository.resolve_version(key, version)
        if capability is None:
            raise not_found_error("Capability")
        return self._resolve_toolset_model(capability)

    def resolve_granted_tool_keys(
        self,
        capability_references: Sequence[dict[str, object]],
    ) -> set[str]:
        granted_tool_keys: set[str] = set()
        for reference in capability_references:
            resolved = self.resolve_toolset_version(
                str(reference["capabilityKey"]),
                int(str(reference["capabilityVersion"])),
            )
            granted_tool_keys.update(tool.key for tool in resolved.tools)
        return granted_tool_keys

    def require_runtime_tool_grant(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        tool_key: str,
        denied_code: str,
        denied_message: str,
    ) -> None:
        granted_tool_keys = self.resolve_granted_tool_keys(capability_references)
        if tool_key not in granted_tool_keys:
            raise RuntimeToolGrantError(code=denied_code, message=denied_message)

    def require_report_lookup_grant(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
    ) -> None:
        self.require_runtime_tool_grant(
            capability_references=capability_references,
            tool_key=REPORT_LOOKUP_TOOL_KEY,
            denied_code=REPORT_LOOKUP_ACCESS_DENIED_CODE,
            denied_message=REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
        )

    def require_position_lookup_grant(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
    ) -> None:
        self.require_runtime_tool_grant(
            capability_references=capability_references,
            tool_key=POSITION_LOOKUP_TOOL_KEY,
            denied_code=POSITION_LOOKUP_ACCESS_DENIED_CODE,
            denied_message=POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
        )

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, capability_id: int) -> Capability:
        capability = self.repository.get(capability_id)
        if capability is None:
            raise not_found_error("Capability")
        return capability

    @staticmethod
    def _ensure_status(capability: Capability, expected: CapabilityStatus, *, action: str) -> None:
        if capability.status != expected.value:
            raise validation_error(
                "Capability validation failed",
                [
                    {
                        "field": "status",
                        "issue": f"Only {expected.value} capabilities can be used for {action}",
                    }
                ],
            )

    @staticmethod
    def _normalize_tool_grants(
        tool_grants: Sequence[CapabilityToolGrantWrite],
    ) -> list[dict[str, str]]:
        return [CapabilityService._normalize_tool_grant(item) for item in tool_grants]

    @staticmethod
    def _normalize_tool_grant(raw_grant: CapabilityToolGrantWrite) -> dict[str, str]:
        return {"tool": raw_grant.tool.strip().lower()}

    def _resolve_tool_grants(
        self,
        tool_grants: Sequence[dict[str, str]],
    ) -> tuple[ResolvedTool, ...]:
        try:
            return self.tool_catalog.resolve_tool_grants(tool_grants)
        except ToolCatalogValidationError as exc:
            raise validation_error("Capability validation failed", list(exc.details)) from exc

    def _resolve_toolset_model(self, capability: Capability) -> ResolvedCapabilityToolset:
        return ResolvedCapabilityToolset(
            capability_id=capability.id,
            capability_key=capability.key,
            capability_version=capability.version,
            name=capability.name,
            description=capability.description,
            tools=self._resolve_tool_grants(capability.tool_grants),
        )

    def _to_read_model(self, capability: Capability) -> CapabilityRead:
        resolved_toolset = self._resolve_toolset_model(capability)
        return CapabilityRead.model_validate(
            {
                "id": capability.id,
                "key": capability.key,
                "version": capability.version,
                "status": capability.status,
                "name": capability.name,
                "description": capability.description,
                "toolGrants": [
                    {
                        "tool": tool.key,
                        "displayName": tool.display_name,
                        "description": tool.description,
                    }
                    for tool in resolved_toolset.tools
                ],
                "createdAt": capability.created_at,
                "updatedAt": capability.updated_at,
            }
        )


__all__ = [
    "CapabilityService",
    "POSITION_LOOKUP_ACCESS_DENIED_CODE",
    "POSITION_LOOKUP_ACCESS_DENIED_MESSAGE",
    "POSITION_LOOKUP_TOOL_KEY",
    "REPORT_LOOKUP_ACCESS_DENIED_CODE",
    "REPORT_LOOKUP_ACCESS_DENIED_MESSAGE",
    "REPORT_LOOKUP_TOOL_KEY",
    "RuntimeToolGrantError",
]
