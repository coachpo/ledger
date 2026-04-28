from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.agents.skills.server_declared import SERVER_DECLARED_TOOL_REGISTRY, ServerDeclaredToolSpec
from app.models.skill import Skill


@dataclass(frozen=True)
class ResolvedSkillTool:
    key: str
    display_name: str
    description: str
    module: str


@dataclass(frozen=True)
class ResolvedSkillToolset:
    skill_id: int
    skill_key: str
    skill_version: int
    name: str
    description: str
    tools: tuple[ResolvedSkillTool, ...]


class SkillRegistryValidationError(ValueError):
    def __init__(self, details: Sequence[dict[str, str]]) -> None:
        super().__init__("Skill registry validation failed")
        self.details = list(details)


class SkillRegistry:
    def __init__(self, tool_registry: dict[str, ServerDeclaredToolSpec] | None = None) -> None:
        self.tool_registry = dict(tool_registry or SERVER_DECLARED_TOOL_REGISTRY)

    def list_registered_tools(self) -> tuple[ResolvedSkillTool, ...]:
        return tuple(
            ResolvedSkillTool(
                key=tool.key,
                display_name=tool.display_name,
                description=tool.description,
                module=tool.module,
            )
            for tool in sorted(self.tool_registry.values(), key=lambda item: item.key)
        )

    def resolve_tool_definitions(
        self,
        tool_definitions: Sequence[dict[str, Any]],
    ) -> tuple[ResolvedSkillTool, ...]:
        resolved_tools: list[ResolvedSkillTool] = []
        seen_keys: set[str] = set()
        details: list[dict[str, str]] = []

        for index, raw_definition in enumerate(tool_definitions):
            tool_key = self._normalize_tool_key(raw_definition, index=index, details=details)
            if tool_key is None:
                continue
            if tool_key in seen_keys:
                details.append(
                    {
                        "field": f"toolDefinitions.{index}.tool",
                        "issue": f"Duplicate tool reference {tool_key!r} is not allowed",
                    }
                )
                continue
            tool_spec = self.tool_registry.get(tool_key)
            if tool_spec is None:
                details.append(
                    {
                        "field": f"toolDefinitions.{index}.tool",
                        "issue": f"Unknown server-declared tool {tool_key!r}",
                    }
                )
                continue
            resolved_tools.append(
                ResolvedSkillTool(
                    key=tool_spec.key,
                    display_name=tool_spec.display_name,
                    description=tool_spec.description,
                    module=tool_spec.module,
                )
            )
            seen_keys.add(tool_key)

        if details:
            raise SkillRegistryValidationError(details)
        return tuple(resolved_tools)

    def resolve_skill(self, skill: Skill) -> ResolvedSkillToolset:
        resolved_tools = self.resolve_tool_definitions(skill.tool_definitions)
        return ResolvedSkillToolset(
            skill_id=skill.id,
            skill_key=skill.key,
            skill_version=skill.version,
            name=skill.name,
            description=skill.description,
            tools=resolved_tools,
        )

    @staticmethod
    def _normalize_tool_key(
        raw_definition: dict[str, Any],
        *,
        index: int,
        details: list[dict[str, str]],
    ) -> str | None:
        if not isinstance(raw_definition, dict):
            details.append(
                {
                    "field": f"toolDefinitions.{index}",
                    "issue": "Tool definitions must be objects",
                }
            )
            return None
        raw_tool_key = raw_definition.get("tool")
        normalized_tool_key = str(raw_tool_key).strip().lower() if raw_tool_key is not None else ""
        if not normalized_tool_key:
            details.append(
                {
                    "field": f"toolDefinitions.{index}.tool",
                    "issue": "Tool key is required",
                }
            )
            return None
        return normalized_tool_key


@lru_cache
def get_default_skill_registry() -> SkillRegistry:
    return SkillRegistry()


__all__ = [
    "ResolvedSkillTool",
    "ResolvedSkillToolset",
    "SkillRegistry",
    "SkillRegistryValidationError",
    "get_default_skill_registry",
]
