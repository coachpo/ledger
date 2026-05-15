from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.agents.runtime_tools import RUNTIME_TOOL_SPECS, RuntimeToolRegistry
from app.core.errors import extension_disabled_error, not_found_error
from app.core.formatting import utcnow
from app.extensions.registry import (
    BundledExtensionDefinition,
    BundledExtensionRegistry,
    ExtensionContribution,
    get_bundled_extension_registry,
)
from app.models.extension import ExtensionState
from app.schemas.extension import (
    ExtensionContributionRead,
    ExtensionListRead,
    ExtensionRead,
    ExtensionToggleRequest,
)


@dataclass(frozen=True, slots=True)
class ExtensionStateSnapshot:
    extension_key: str
    enabled: bool
    default_enabled: bool
    state_version: int
    enabled_at: datetime | None
    disabled_at: datetime | None
    disabled_reason: str | None

    def require_enabled(self, *, surface: str) -> ExtensionStateSnapshot:
        if not self.enabled:
            raise extension_disabled_error(extension_key=self.extension_key, surface=surface)
        return self


class ExtensionService:
    session: Session
    registry: BundledExtensionRegistry

    def __init__(
        self,
        session: Session,
        registry: BundledExtensionRegistry | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or get_bundled_extension_registry()

    def list_extensions(self) -> ExtensionListRead:
        states_by_key = self._states_by_key()
        return ExtensionListRead(
            items=[
                self._to_read_model(extension, states_by_key.get(extension.key))
                for extension in self.registry.list_extensions()
            ]
        )

    def get_extension(self, extension_key: str) -> ExtensionRead:
        extension = self._get_extension_definition(extension_key)
        return self._to_read_model(extension, self._get_state(extension.key))

    def set_extension_enabled(
        self,
        extension_key: str,
        payload: ExtensionToggleRequest,
    ) -> ExtensionRead:
        extension = self._get_extension_definition(extension_key)
        state = self._get_state(extension.key)
        if state is None:
            state = self._new_default_state(extension)
            self.session.add(state)
            self.session.flush()

        disabled_reason = None if payload.enabled else payload.disabled_reason
        if state.enabled != payload.enabled or state.disabled_reason != disabled_reason:
            self._apply_state_transition(state, enabled=payload.enabled, reason=disabled_reason)

        try:
            self.session.commit()
            self.session.refresh(state)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(extension, state)

    def resolve_state(self, extension_key: str) -> ExtensionStateSnapshot:
        extension = self._get_extension_definition(extension_key)
        return self._snapshot(extension, self._get_state(extension.key))

    def require_enabled(
        self,
        extension_key: str,
        *,
        surface: str,
    ) -> ExtensionStateSnapshot:
        return self.resolve_state(extension_key).require_enabled(surface=surface)

    def list_all_contributions(self) -> list[ExtensionContributionRead]:
        return self._contribution_reads(self.registry.list_contributions())

    def list_enabled_discovery_contributions(self) -> list[ExtensionContributionRead]:
        enabled_keys = self._enabled_extension_keys()
        return self._contribution_reads(
            self.registry.list_discovery_contributions(enabled_extension_keys=enabled_keys)
        )

    def list_enabled_execution_contributions(self) -> list[ExtensionContributionRead]:
        enabled_keys = self._enabled_extension_keys()
        return self._contribution_reads(
            self.registry.list_execution_contributions(enabled_extension_keys=enabled_keys)
        )

    def get_tool_catalog(self) -> ToolCatalog:
        return ToolCatalog(enabled_extension_keys=self._enabled_extension_keys())

    def get_runtime_tool_registry(self) -> RuntimeToolRegistry:
        return RuntimeToolRegistry(
            RUNTIME_TOOL_SPECS,
            enabled_extension_keys=self._enabled_extension_keys(),
        )

    def _enabled_extension_keys(self) -> set[str]:
        states_by_key = self._states_by_key()
        return {
            extension.key
            for extension in self.registry.list_extensions()
            if self._snapshot(extension, states_by_key.get(extension.key)).enabled
        }

    def _get_extension_definition(self, extension_key: str) -> BundledExtensionDefinition:
        extension = self.registry.get_extension(extension_key)
        if extension is None:
            raise not_found_error("Extension")
        return extension

    def _states_by_key(self) -> dict[str, ExtensionState]:
        keys = [extension.key for extension in self.registry.list_extensions()]
        if not keys:
            return {}
        statement = select(ExtensionState).where(ExtensionState.extension_key.in_(keys))
        return {state.extension_key: state for state in self.session.scalars(statement)}

    def _get_state(self, extension_key: str) -> ExtensionState | None:
        statement = select(ExtensionState).where(ExtensionState.extension_key == extension_key)
        return self.session.scalar(statement)

    @staticmethod
    def _new_default_state(extension: BundledExtensionDefinition) -> ExtensionState:
        now = utcnow()
        return ExtensionState(
            extension_key=extension.key,
            enabled=extension.default_enabled,
            enabled_at=now if extension.default_enabled else None,
            disabled_at=None if extension.default_enabled else now,
            disabled_reason=None,
            state_version=1,
        )

    @staticmethod
    def _apply_state_transition(
        state: ExtensionState,
        *,
        enabled: bool,
        reason: str | None,
    ) -> None:
        now = utcnow()
        state.enabled = enabled
        state.state_version += 1
        if enabled:
            state.enabled_at = now
            state.disabled_at = None
            state.disabled_reason = None
            return
        state.disabled_at = now
        state.disabled_reason = reason

    @staticmethod
    def _snapshot(
        extension: BundledExtensionDefinition,
        state: ExtensionState | None,
    ) -> ExtensionStateSnapshot:
        if state is None:
            return ExtensionStateSnapshot(
                extension_key=extension.key,
                enabled=extension.default_enabled,
                default_enabled=extension.default_enabled,
                state_version=1,
                enabled_at=None,
                disabled_at=None,
                disabled_reason=None,
            )
        return ExtensionStateSnapshot(
            extension_key=extension.key,
            enabled=state.enabled,
            default_enabled=extension.default_enabled,
            state_version=state.state_version,
            enabled_at=state.enabled_at,
            disabled_at=state.disabled_at,
            disabled_reason=state.disabled_reason,
        )

    def _to_read_model(
        self,
        extension: BundledExtensionDefinition,
        state: ExtensionState | None,
    ) -> ExtensionRead:
        snapshot = self._snapshot(extension, state)
        return ExtensionRead.model_validate(
            {
                "key": extension.key,
                "label": extension.label,
                "enabled": snapshot.enabled,
                "defaultEnabled": extension.default_enabled,
                "phase": extension.phase,
                "versioningRule": extension.versioning_rule,
                "contributionCategories": list(extension.contribution_categories),
                "dependencies": list(extension.dependencies),
                "contributions": self._contribution_reads(extension.contributions),
                "stateVersion": snapshot.state_version,
                "enabledAt": snapshot.enabled_at,
                "disabledAt": snapshot.disabled_at,
                "disabledReason": snapshot.disabled_reason,
                "createdAt": state.created_at if state is not None else None,
                "updatedAt": state.updated_at if state is not None else None,
            }
        )

    @staticmethod
    def _contribution_reads(
        contributions: tuple[ExtensionContribution, ...],
    ) -> list[ExtensionContributionRead]:
        return [
            ExtensionContributionRead.model_validate(contribution.as_dict())
            for contribution in contributions
        ]


__all__ = ["ExtensionService", "ExtensionStateSnapshot"]
