from __future__ import annotations

from collections.abc import ItemsView, Iterator, ValuesView
from functools import lru_cache

from app.extensions import BundledServerDeclaredToolContribution as ServerDeclaredToolSpec
from app.extensions.registry import INSTALLED_EXTENSIONS

CORE_SERVER_DECLARED_TOOL_SPECS: tuple[ServerDeclaredToolSpec, ...] = ()


def _load_server_declared_tool_specs() -> tuple[ServerDeclaredToolSpec, ...]:
    return (
        *CORE_SERVER_DECLARED_TOOL_SPECS,
        *(
            declaration
            for extension in INSTALLED_EXTENSIONS
            for declaration in extension.tool_declarations
        ),
    )


def _registry_by_key(
    specs: tuple[ServerDeclaredToolSpec, ...],
) -> dict[str, ServerDeclaredToolSpec]:
    registry: dict[str, ServerDeclaredToolSpec] = {}
    for spec in specs:
        if spec.key in registry:
            raise ValueError(f"Duplicate server-declared tool key {spec.key!r}")
        registry[spec.key] = spec
    return registry


@lru_cache(maxsize=1)
def get_server_declared_tool_specs() -> tuple[ServerDeclaredToolSpec, ...]:
    return _load_server_declared_tool_specs()


@lru_cache(maxsize=1)
def get_server_declared_tool_registry() -> dict[str, ServerDeclaredToolSpec]:
    return _registry_by_key(get_server_declared_tool_specs())


class _LazyServerDeclaredToolSpecs:
    def __iter__(self) -> Iterator[ServerDeclaredToolSpec]:
        return iter(get_server_declared_tool_specs())

    def __len__(self) -> int:
        return len(get_server_declared_tool_specs())

    def __getitem__(self, index: int) -> ServerDeclaredToolSpec:
        return get_server_declared_tool_specs()[index]


class _LazyServerDeclaredToolRegistry:
    def items(self) -> ItemsView[str, ServerDeclaredToolSpec]:
        return get_server_declared_tool_registry().items()

    def values(self) -> ValuesView[ServerDeclaredToolSpec]:
        return get_server_declared_tool_registry().values()

    def get(self, key: str) -> ServerDeclaredToolSpec | None:
        return get_server_declared_tool_registry().get(key)

    def __getitem__(self, key: str) -> ServerDeclaredToolSpec:
        return get_server_declared_tool_registry()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(get_server_declared_tool_registry())

    def __len__(self) -> int:
        return len(get_server_declared_tool_registry())


SERVER_DECLARED_TOOL_SPECS = _LazyServerDeclaredToolSpecs()
SERVER_DECLARED_TOOL_REGISTRY = _LazyServerDeclaredToolRegistry()

__all__ = [
    "CORE_SERVER_DECLARED_TOOL_SPECS",
    "SERVER_DECLARED_TOOL_REGISTRY",
    "SERVER_DECLARED_TOOL_SPECS",
    "ServerDeclaredToolSpec",
    "get_server_declared_tool_registry",
    "get_server_declared_tool_specs",
]
