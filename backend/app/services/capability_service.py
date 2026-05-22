from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    ResolvedCapabilityToolset,
    ResolvedTool,
    ToolCatalog,
    ToolCatalogValidationError,
)
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.agent import Agent
from app.models.capability import Capability
from app.models.platform_reference import AgentCapabilityRef
from app.repositories.capability import CapabilityRepository
from app.schemas.capability import (
    CapabilityDraftCreate,
    CapabilityDraftUpdate,
    CapabilityListRead,
    CapabilityRead,
    CapabilityStatus,
    CapabilityToolListRead,
)


@dataclass(frozen=True, slots=True)
class RuntimeToolGrantPolicy:
    tool_key: str
    denied_code: str
    denied_message: str


class RuntimeToolGrantError(Exception):
    code: str
    message: str
    details: list[dict[str, str]]

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
    session: Session
    repository: CapabilityRepository
    tool_catalog: ToolCatalog

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

    def list_available_tools(self) -> CapabilityToolListRead:
        tools = sorted(self.tool_catalog.list_registered_tools(), key=lambda item: item.key)
        return CapabilityToolListRead.model_validate(
            {
                "items": [
                    {
                        "key": tool.key,
                        "displayName": tool.display_name,
                        "description": tool.description,
                    }
                    for tool in tools
                ]
            }
        )

    def get_capability(self, capability_id: int) -> CapabilityRead:
        return self._to_read_model(self._get_model(capability_id))

    def create_draft(self, payload: CapabilityDraftCreate) -> CapabilityRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="capability_duplicate_draft",
                message="A draft capability already exists for this key",
            )

        resolved_tools = self._resolve_tool_keys(payload.tool_keys)
        tool_keys = [tool.key for tool in resolved_tools]
        capability = Capability(
            key=payload.key,
            version=self._next_version(payload.key),
            status=CapabilityStatus.DRAFT.value,
            name=payload.name,
            description=payload.description,
            tool_keys=tool_keys,
        )
        try:
            _ = self.repository.add(capability)
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

        tool_keys = list(source.tool_keys)
        if payload.tool_keys is not None:
            resolved_tools = self._resolve_tool_keys(payload.tool_keys)
            tool_keys = [tool.key for tool in resolved_tools]
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
            tool_keys=tool_keys,
        )

        try:
            self.repository.delete(source)
            self.session.flush()
            _ = self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(updated)

    def activate(self, capability_id: int) -> CapabilityRead:
        capability = self._get_model(capability_id)
        self._ensure_status(capability, CapabilityStatus.DRAFT, action="activate")
        _ = self._resolve_toolset_model(capability)

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

    def delete_capability(self, capability_id: int) -> None:
        capability = self._get_model(capability_id)
        agent_refs = self._agent_reference_details(capability.id)
        if agent_refs:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="capability_delete_blocked",
                message="Capability is referenced by agents",
                details=agent_refs,
            )

        try:
            self.repository.delete(capability)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _agent_reference_details(self, capability_id: int) -> list[dict[str, object]]:
        statement = (
            select(Agent)
            .join(AgentCapabilityRef, Agent.id == AgentCapabilityRef.agent_id)
            .where(AgentCapabilityRef.capability_id == capability_id)
            .order_by(Agent.key.asc(), Agent.version.desc(), Agent.id.asc())
        )
        return [
            {
                "field": "agentId",
                "issue": "Capability is referenced by agent",
                "agentId": agent.id,
                "agentKey": agent.key,
                "agentVersion": agent.version,
            }
            for agent in self.session.scalars(statement)
        ]

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
            package_tool_keys = reference.get("toolKeys")
            if isinstance(package_tool_keys, list):
                for package_tool_key in package_tool_keys:
                    if isinstance(package_tool_key, str):
                        granted_tool_keys.add(package_tool_key)
                continue
            try:
                resolved = self.resolve_toolset_version(
                    str(reference["capabilityKey"]),
                    int(str(reference["capabilityVersion"])),
                )
            except ApiError as exc:
                if exc.code == "validation_error":
                    details: list[dict[str, str]] = []
                    for detail in exc.details:
                        field = detail.get("field")
                        issue = detail.get("issue")
                        details.append(
                            {
                                "field": field if isinstance(field, str) else "toolKeys",
                                "issue": issue if isinstance(issue, str) else "Invalid tool key",
                            }
                        )
                    raise RuntimeToolGrantError(
                        code="capability_tool_keys_invalid",
                        message="Capability contains stale or invalid tool keys.",
                        details=details,
                    ) from exc
                raise
            granted_tool_keys.update(tool.key for tool in resolved.tools)
        return granted_tool_keys

    def require_runtime_tool_grant(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
    ) -> None:
        granted_tool_keys = self.resolve_granted_tool_keys(capability_references)
        if grant_policy.tool_key not in granted_tool_keys:
            raise RuntimeToolGrantError(
                code=grant_policy.denied_code,
                message=grant_policy.denied_message,
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

    def _resolve_tool_keys(
        self,
        tool_keys: Sequence[object],
    ) -> tuple[ResolvedTool, ...]:
        try:
            return self.tool_catalog.resolve_tool_keys(tool_keys)
        except ToolCatalogValidationError as exc:
            raise validation_error("Capability validation failed", list(exc.details)) from exc

    def _resolve_toolset_model(self, capability: Capability) -> ResolvedCapabilityToolset:
        return ResolvedCapabilityToolset(
            capability_id=capability.id,
            capability_key=capability.key,
            capability_version=capability.version,
            name=capability.name,
            description=capability.description,
            tools=self._resolve_tool_keys(capability.tool_keys),
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
                "toolKeys": [tool.key for tool in resolved_toolset.tools],
                "tools": [
                    {
                        "key": tool.key,
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
    "RuntimeToolGrantError",
    "RuntimeToolGrantPolicy",
]
