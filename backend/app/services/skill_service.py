from __future__ import annotations

from collections.abc import Sequence

from fastapi import status
from sqlalchemy.orm import Session

from app.agents.skill_registry import (
    ResolvedSkillTool,
    ResolvedSkillToolset,
    SkillRegistry,
    SkillRegistryValidationError,
)
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.skill import Skill
from app.repositories.skill import SkillRepository
from app.schemas.skill import (
    SkillDraftCreate,
    SkillDraftUpdate,
    SkillListRead,
    SkillRead,
    SkillStatus,
    SkillToolDefinitionWrite,
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


class SkillService:
    def __init__(self, session: Session, skill_registry: SkillRegistry) -> None:
        self.session = session
        self.repository = SkillRepository(session)
        self.skill_registry = skill_registry

    def list_skills(self, *, status_filter: SkillStatus | None = None) -> SkillListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None
        )
        return SkillListRead(items=[self._to_read_model(item) for item in items])

    def get_skill(self, skill_id: int) -> SkillRead:
        return self._to_read_model(self._get_model(skill_id))

    def create_draft(self, payload: SkillDraftCreate) -> SkillRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="skill_duplicate_draft",
                message="A draft skill already exists for this key",
            )

        tool_definitions = self._normalize_tool_definitions(payload.tool_definitions)
        self._resolve_tool_definitions(tool_definitions)
        skill = Skill(
            key=payload.key,
            version=self._next_version(payload.key),
            status=SkillStatus.DRAFT.value,
            name=payload.name,
            description=payload.description,
            tool_definitions=tool_definitions,
        )
        try:
            self.repository.add(skill)
            self.session.commit()
            self.session.refresh(skill)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(skill)

    def update_draft(self, skill_id: int, payload: SkillDraftUpdate) -> SkillRead:
        source = self._get_model(skill_id)
        self._ensure_status(source, SkillStatus.DRAFT, action="patch")

        tool_definitions = (
            self._normalize_tool_definitions(payload.tool_definitions)
            if payload.tool_definitions is not None
            else list(source.tool_definitions)
        )
        self._resolve_tool_definitions(tool_definitions)
        updated = Skill(
            key=source.key,
            version=self._next_version(source.key),
            status=SkillStatus.DRAFT.value,
            name=payload.name if payload.name is not None else source.name,
            description=(
                payload.description or ""
                if payload.description is not None or "description" in payload.model_fields_set
                else source.description
            ),
            tool_definitions=tool_definitions,
        )

        try:
            source.status = SkillStatus.ARCHIVED.value
            self.session.flush()
            self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(updated)

    def activate(self, skill_id: int) -> SkillRead:
        skill = self._get_model(skill_id)
        self._ensure_status(skill, SkillStatus.DRAFT, action="activate")
        self._resolve_toolset_model(skill)

        current_published = self.repository.get_published_by_key(skill.key)
        try:
            if current_published is not None and current_published.id != skill.id:
                current_published.status = SkillStatus.DEPRECATED.value
                self.session.flush()
            skill.status = SkillStatus.PUBLISHED.value
            self.session.commit()
            self.session.refresh(skill)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(skill)

    def archive(self, skill_id: int) -> SkillRead:
        skill = self._get_model(skill_id)
        if skill.status == SkillStatus.ARCHIVED.value:
            return self._to_read_model(skill)

        try:
            skill.status = SkillStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(skill)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(skill)

    def resolve_toolset(self, skill_id: int) -> ResolvedSkillToolset:
        return self._resolve_toolset_model(self._get_model(skill_id))

    def resolve_toolset_version(self, key: str, version: int | None) -> ResolvedSkillToolset:
        skill = self.repository.resolve_version(key, version)
        if skill is None:
            raise not_found_error("Skill")
        return self._resolve_toolset_model(skill)

    def resolve_granted_tool_keys(
        self,
        skill_references: Sequence[dict[str, object]],
    ) -> set[str]:
        granted_tool_keys: set[str] = set()
        for reference in skill_references:
            resolved = self.resolve_toolset_version(
                str(reference["skillKey"]),
                int(str(reference["skillVersion"])),
            )
            granted_tool_keys.update(tool.key for tool in resolved.tools)
        return granted_tool_keys

    def require_runtime_tool_grant(
        self,
        *,
        skill_references: Sequence[dict[str, object]],
        tool_key: str,
        denied_code: str,
        denied_message: str,
    ) -> None:
        granted_tool_keys = self.resolve_granted_tool_keys(skill_references)
        if tool_key not in granted_tool_keys:
            raise RuntimeToolGrantError(code=denied_code, message=denied_message)

    def require_report_lookup_grant(
        self,
        *,
        skill_references: Sequence[dict[str, object]],
    ) -> None:
        self.require_runtime_tool_grant(
            skill_references=skill_references,
            tool_key=REPORT_LOOKUP_TOOL_KEY,
            denied_code=REPORT_LOOKUP_ACCESS_DENIED_CODE,
            denied_message=REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
        )

    def require_position_lookup_grant(
        self,
        *,
        skill_references: Sequence[dict[str, object]],
    ) -> None:
        self.require_runtime_tool_grant(
            skill_references=skill_references,
            tool_key=POSITION_LOOKUP_TOOL_KEY,
            denied_code=POSITION_LOOKUP_ACCESS_DENIED_CODE,
            denied_message=POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
        )

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, skill_id: int) -> Skill:
        skill = self.repository.get(skill_id)
        if skill is None:
            raise not_found_error("Skill")
        return skill

    @staticmethod
    def _ensure_status(skill: Skill, expected: SkillStatus, *, action: str) -> None:
        if skill.status != expected.value:
            raise validation_error(
                "Skill validation failed",
                [
                    {
                        "field": "status",
                        "issue": f"Only {expected.value} skills can be used for {action}",
                    }
                ],
            )

    @staticmethod
    def _normalize_tool_definitions(
        tool_definitions: Sequence[SkillToolDefinitionWrite],
    ) -> list[dict[str, str]]:
        return [SkillService._normalize_tool_definition(item) for item in tool_definitions]

    @staticmethod
    def _normalize_tool_definition(raw_definition: SkillToolDefinitionWrite) -> dict[str, str]:
        return {"tool": raw_definition.tool.strip().lower()}

    def _resolve_tool_definitions(
        self,
        tool_definitions: Sequence[dict[str, str]],
    ) -> tuple[ResolvedSkillTool, ...]:
        try:
            return self.skill_registry.resolve_tool_definitions(tool_definitions)
        except SkillRegistryValidationError as exc:
            raise validation_error("Skill validation failed", exc.details) from exc

    def _resolve_toolset_model(self, skill: Skill) -> ResolvedSkillToolset:
        return ResolvedSkillToolset(
            skill_id=skill.id,
            skill_key=skill.key,
            skill_version=skill.version,
            name=skill.name,
            description=skill.description,
            tools=self._resolve_tool_definitions(skill.tool_definitions),
        )

    def _to_read_model(self, skill: Skill) -> SkillRead:
        resolved_toolset = self._resolve_toolset_model(skill)
        return SkillRead.model_validate(
            {
                "id": skill.id,
                "key": skill.key,
                "version": skill.version,
                "status": skill.status,
                "name": skill.name,
                "description": skill.description,
                "toolDefinitions": [
                    {
                        "tool": tool.key,
                        "displayName": tool.display_name,
                        "description": tool.description,
                    }
                    for tool in resolved_toolset.tools
                ],
                "createdAt": skill.created_at,
                "updatedAt": skill.updated_at,
            }
        )


__all__ = [
    "POSITION_LOOKUP_ACCESS_DENIED_CODE",
    "POSITION_LOOKUP_ACCESS_DENIED_MESSAGE",
    "POSITION_LOOKUP_TOOL_KEY",
    "REPORT_LOOKUP_ACCESS_DENIED_CODE",
    "REPORT_LOOKUP_ACCESS_DENIED_MESSAGE",
    "REPORT_LOOKUP_TOOL_KEY",
    "RuntimeToolGrantError",
    "SkillService",
]
