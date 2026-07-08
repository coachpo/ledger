from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from app.extensions import signaldeck_digital_oracle, signaldeck_finance
from app.extensions.contract import Extension
from app.services.execution_providers import (
    ExecutionProviderBundle,
    merge_execution_provider_bundles,
)

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"
DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle"

FINANCE: Extension = signaldeck_finance.EXTENSION
DIGITAL_ORACLE: Extension = signaldeck_digital_oracle.EXTENSION

INSTALLED_EXTENSIONS: tuple[Extension, ...] = (FINANCE, DIGITAL_ORACLE)


def build_execution_provider_bundle() -> ExecutionProviderBundle:
    bundles: list[ExecutionProviderBundle] = []
    for extension in INSTALLED_EXTENSIONS:
        factory = extension.provider_factories.get("execution_provider_bundle")
        if factory is not None:
            bundles.append(cast(ExecutionProviderBundle, factory()))
    return merge_execution_provider_bundles(bundles)


def runtime_dependency_surfaces_for_extensions(extension_keys: Iterable[str]) -> tuple[str, ...]:
    selected_keys = set(extension_keys)
    surfaces: set[str] = set()
    for extension in INSTALLED_EXTENSIONS:
        if extension.key in selected_keys:
            surfaces.update(extension.runtime_dependency_surfaces)
    return tuple(sorted(surfaces))


def package_private_mcp_tool_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for extension in INSTALLED_EXTENSIONS:
        for tool_key in extension.package_private_mcp_tool_keys:
            owners[tool_key.strip().lower()] = extension.key
    return owners


def _assert_unique_extension_and_tool_keys() -> None:
    extension_keys: set[str] = set()
    tool_keys: set[str] = set()
    for extension in INSTALLED_EXTENSIONS:
        if extension.key in extension_keys:
            raise RuntimeError(f"duplicate extension key: {extension.key}")
        extension_keys.add(extension.key)
        for declaration in extension.tool_declarations:
            if declaration.key in tool_keys:
                raise RuntimeError(f"duplicate tool key: {declaration.key}")
            tool_keys.add(declaration.key)


_assert_unique_extension_and_tool_keys()


__all__ = [
    "DIGITAL_ORACLE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "INSTALLED_EXTENSIONS",
    "build_execution_provider_bundle",
    "package_private_mcp_tool_owners",
    "runtime_dependency_surfaces_for_extensions",
]
