from __future__ import annotations

from app.extensions import BundledServerDeclaredToolContribution as ServerDeclaredToolSpec
from app.extensions.registry import get_bundled_extension_registry


def _load_server_declared_tool_specs() -> tuple[ServerDeclaredToolSpec, ...]:
    return get_bundled_extension_registry().list_server_declared_tool_contributions()


def _registry_by_key(
    specs: tuple[ServerDeclaredToolSpec, ...],
) -> dict[str, ServerDeclaredToolSpec]:
    registry: dict[str, ServerDeclaredToolSpec] = {}
    for spec in specs:
        if spec.key in registry:
            raise ValueError(f"Duplicate server-declared tool key {spec.key!r}")
        registry[spec.key] = spec
    return registry


def enabled_server_declared_tool_registry(
    *,
    enabled_extension_keys: set[str],
) -> dict[str, ServerDeclaredToolSpec]:
    return {
        key: spec
        for key, spec in SERVER_DECLARED_TOOL_REGISTRY.items()
        if spec.owner_extension_key is None or spec.owner_extension_key in enabled_extension_keys
    }


SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = _load_server_declared_tool_specs()
SERVER_DECLARED_TOOL_REGISTRY: dict[str, ServerDeclaredToolSpec] = _registry_by_key(
    SERVER_DECLARED_TOOL_SPECS
)

__all__ = [
    "SERVER_DECLARED_TOOL_REGISTRY",
    "SERVER_DECLARED_TOOL_SPECS",
    "ServerDeclaredToolSpec",
    "enabled_server_declared_tool_registry",
]
