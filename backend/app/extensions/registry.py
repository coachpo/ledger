from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from typing import cast

from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_DEFAULT_ENABLED,
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_LABEL,
)

_FINANCE_WORKSPACE_TOOL_SPEC_REGISTRARS = ("app.extensions.signaldeck_finance.tool_specs:register",)
_FINANCE_WORKSPACE_RUNTIME_TOOL_REGISTRARS = (
    "app.extensions.signaldeck_finance.runtime_executors:register",
)


@dataclass(frozen=True, slots=True)
class BundledExtensionDefinition:
    key: str
    label: str
    default_enabled: bool
    tool_spec_registrars: tuple[str, ...] = ()
    runtime_tool_registrars: tuple[str, ...] = ()


def load_extension_registrar(registrar: str) -> tuple[object, ...]:
    module_name, separator, attribute_name = registrar.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError(f"Invalid extension registrar {registrar!r}")
    module = import_module(module_name)
    raw_registrar = cast(object, getattr(module, attribute_name, None))
    if not callable(raw_registrar):
        raise ValueError(f"Extension registrar {registrar!r} is not callable")
    loaded_registrar = cast(Callable[[], Iterable[object]], raw_registrar)
    return tuple(loaded_registrar())


class BundledExtensionRegistry:
    def __init__(self, extensions: Iterable[BundledExtensionDefinition]) -> None:
        extensions_by_key: dict[str, BundledExtensionDefinition] = {}
        for extension in extensions:
            if extension.key in extensions_by_key:
                raise ValueError(f"Duplicate bundled extension key {extension.key!r}")
            extensions_by_key[extension.key] = extension
        self._extensions_by_key: dict[str, BundledExtensionDefinition] = extensions_by_key

    def list_extensions(self) -> tuple[BundledExtensionDefinition, ...]:
        return tuple(self._extensions_by_key.values())

    def get_extension(self, extension_key: str) -> BundledExtensionDefinition | None:
        return self._extensions_by_key.get(extension_key)

    def require_extension(self, extension_key: str) -> BundledExtensionDefinition:
        extension = self.get_extension(extension_key)
        if extension is None:
            raise KeyError(extension_key)
        return extension


@lru_cache(maxsize=1)
def get_bundled_extension_registry() -> BundledExtensionRegistry:
    return BundledExtensionRegistry(
        (
            BundledExtensionDefinition(
                key=FINANCE_WORKSPACE_EXTENSION_KEY,
                label=FINANCE_WORKSPACE_LABEL,
                default_enabled=FINANCE_WORKSPACE_DEFAULT_ENABLED,
                tool_spec_registrars=_FINANCE_WORKSPACE_TOOL_SPEC_REGISTRARS,
                runtime_tool_registrars=_FINANCE_WORKSPACE_RUNTIME_TOOL_REGISTRARS,
            ),
        )
    )


__all__ = [
    "BundledExtensionDefinition",
    "BundledExtensionRegistry",
    "get_bundled_extension_registry",
    "load_extension_registrar",
]
