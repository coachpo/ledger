from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.core.errors import extension_disabled_error, not_found_error
from app.extensions.registry import (
    BundledExtensionDefinition,
    BundledExtensionRegistry,
    get_bundled_extension_registry,
)
from app.models.extension import ExtensionState
from app.schemas.extension import ExtensionListRead, ExtensionRead, ExtensionToggleRequest
from app.services.execution_providers import ExecutionProviderBundle
from app.services.run_lifecycle import ExtensionRunLifecycleHooks


@dataclass(frozen=True, slots=True)
class ResolvedExtensionState:
    extension_key: str
    enabled: bool

    def require_enabled(self, *, surface: str) -> ResolvedExtensionState:
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

        if state.enabled != payload.enabled:
            self._apply_state_transition(state, enabled=payload.enabled)

        try:
            self.session.commit()
            self.session.refresh(state)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(extension, state)

    def resolve_state(self, extension_key: str) -> ResolvedExtensionState:
        extension = self._get_extension_definition(extension_key)
        return self._snapshot(extension, self._get_state(extension.key))

    def require_enabled(
        self,
        extension_key: str,
        *,
        surface: str,
    ) -> ResolvedExtensionState:
        return self.resolve_state(extension_key).require_enabled(surface=surface)

    def get_tool_catalog(self) -> ToolCatalog:
        return ToolCatalog(enabled_extension_keys=self._enabled_extension_keys())

    def get_runtime_tool_registry(self) -> RuntimeToolRegistry:
        from app.agents.runtime_tools import RUNTIME_TOOL_SPECS

        return RuntimeToolRegistry(
            RUNTIME_TOOL_SPECS,
            enabled_extension_keys=self._enabled_extension_keys(),
        )

    def get_execution_provider_bundle(self) -> ExecutionProviderBundle:
        return self.registry.build_execution_provider_bundle(self._enabled_extension_keys())

    def get_run_lifecycle_hooks(
        self,
        extension_keys: Iterable[str],
    ) -> tuple[ExtensionRunLifecycleHooks, ...]:
        selected_keys = set(extension_keys) & self._enabled_extension_keys()
        return self.registry.list_run_lifecycle_hooks(selected_keys)

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
        return ExtensionState(
            extension_key=extension.key,
            enabled=extension.default_enabled,
        )

    @staticmethod
    def _apply_state_transition(
        state: ExtensionState,
        *,
        enabled: bool,
    ) -> None:
        state.enabled = enabled

    @staticmethod
    def _snapshot(
        extension: BundledExtensionDefinition,
        state: ExtensionState | None,
    ) -> ResolvedExtensionState:
        return ResolvedExtensionState(
            extension_key=extension.key,
            enabled=extension.default_enabled if state is None else state.enabled,
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
            }
        )


__all__ = ["ExtensionService", "ResolvedExtensionState"]
