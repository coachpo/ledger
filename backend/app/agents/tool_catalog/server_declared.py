from __future__ import annotations

from dataclasses import dataclass

from app.extensions.registry import get_bundled_extension_registry, load_extension_registrar


@dataclass(frozen=True)
class ServerDeclaredToolSpec:
    key: str
    display_name: str
    description: str
    module: str
    owner_extension_key: str | None = None


def _load_server_declared_tool_specs() -> tuple[ServerDeclaredToolSpec, ...]:
    specs: list[ServerDeclaredToolSpec] = []
    for extension in get_bundled_extension_registry().list_extensions():
        for registrar in extension.tool_spec_registrars:
            for tool_spec in load_extension_registrar(registrar):
                if not isinstance(tool_spec, ServerDeclaredToolSpec):
                    message = (
                        f"Tool spec registrar {registrar!r} returned "
                        + f"unsupported item {type(tool_spec).__name__!r}"
                    )
                    raise ValueError(message)
                specs.append(tool_spec)
    return tuple(specs)


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
