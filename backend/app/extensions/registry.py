from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from app.extensions import BundledApiRouterContribution, BundledServerDeclaredToolContribution
from app.services.execution_providers import (
    ExecutionProviderBundle,
    merge_execution_provider_bundles,
)

if TYPE_CHECKING:
    from app.agents.runtime_tools.types import RuntimeToolSpec


FINANCE_WORKSPACE_DEFAULT_ENABLED = True
FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"
FINANCE_WORKSPACE_LABEL = "Finance Workspace"
DIGITAL_ORACLE_DEFAULT_ENABLED = True
DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle"
DIGITAL_ORACLE_LABEL = "Digital Oracle Runtime"


@dataclass(frozen=True, slots=True)
class BundledExtensionDefinition:
    key: str
    label: str
    default_enabled: bool


type ApiRouterContributionLoader = Callable[[], tuple[BundledApiRouterContribution, ...]]
type ServerDeclaredToolContributionLoader = Callable[
    [], tuple[BundledServerDeclaredToolContribution, ...]
]
type RuntimeToolContributionLoader = Callable[[], tuple[RuntimeToolSpec, ...]]
type ExecutionProviderBundleLoader = Callable[[], ExecutionProviderBundle]


class _FinanceRegistrarsModule(Protocol):
    def load_api_router_contributions(self) -> tuple[BundledApiRouterContribution, ...]: ...

    def load_server_declared_tool_contributions(
        self,
    ) -> tuple[BundledServerDeclaredToolContribution, ...]: ...

    def load_runtime_tool_contributions(self) -> tuple[RuntimeToolSpec, ...]: ...

    def load_execution_provider_bundle(self) -> ExecutionProviderBundle: ...


class _DigitalOracleRegistrarsModule(Protocol):
    def load_server_declared_tool_contributions(
        self,
    ) -> tuple[BundledServerDeclaredToolContribution, ...]: ...

    def load_runtime_tool_contributions(self) -> tuple[RuntimeToolSpec, ...]: ...


def _finance_registrars() -> _FinanceRegistrarsModule:
    return cast(
        _FinanceRegistrarsModule,
        cast(object, import_module("app.extensions.signaldeck_finance.registrars")),
    )


def _digital_oracle_registrars() -> _DigitalOracleRegistrarsModule:
    return cast(
        _DigitalOracleRegistrarsModule,
        cast(object, import_module("app.extensions.signaldeck_digital_oracle.registrars")),
    )


def _load_finance_api_router_contributions() -> tuple[BundledApiRouterContribution, ...]:
    return _finance_registrars().load_api_router_contributions()


def _load_finance_server_declared_tool_contributions() -> (
    tuple[BundledServerDeclaredToolContribution, ...]
):
    return _finance_registrars().load_server_declared_tool_contributions()


def _load_finance_runtime_tool_contributions() -> tuple[RuntimeToolSpec, ...]:
    return _finance_registrars().load_runtime_tool_contributions()


def _load_digital_oracle_server_declared_tool_contributions() -> (
    tuple[BundledServerDeclaredToolContribution, ...]
):
    return _digital_oracle_registrars().load_server_declared_tool_contributions()


def _load_digital_oracle_runtime_tool_contributions() -> tuple[RuntimeToolSpec, ...]:
    return _digital_oracle_registrars().load_runtime_tool_contributions()


def _load_finance_execution_provider_bundle() -> ExecutionProviderBundle:
    return _finance_registrars().load_execution_provider_bundle()


@dataclass(frozen=True, slots=True)
class BundledExtensionContributionLoaders:
    api_routers: ApiRouterContributionLoader | None = None
    server_declared_tools: ServerDeclaredToolContributionLoader | None = None
    runtime_tools: RuntimeToolContributionLoader | None = None
    execution_provider_bundle: ExecutionProviderBundleLoader | None = None
    runtime_dependency_surfaces: tuple[str, ...] = ()
    package_private_mcp_tool_keys: tuple[str, ...] = ()


_T = TypeVar("_T")


class BundledExtensionRegistry:
    def __init__(
        self,
        extensions: Iterable[BundledExtensionDefinition],
        contribution_loaders: Mapping[str, BundledExtensionContributionLoaders] | None = None,
    ) -> None:
        extensions_by_key: dict[str, BundledExtensionDefinition] = {}
        for extension in extensions:
            if extension.key in extensions_by_key:
                raise ValueError(f"Duplicate bundled extension key {extension.key!r}")
            extensions_by_key[extension.key] = extension
        contribution_loaders_by_key = dict(contribution_loaders or {})
        unknown_loader_keys = set(contribution_loaders_by_key) - set(extensions_by_key)
        if unknown_loader_keys:
            unknown = ", ".join(sorted(unknown_loader_keys))
            raise ValueError(f"Contribution loaders reference unknown extension keys: {unknown}")
        self._extensions_by_key: dict[str, BundledExtensionDefinition] = extensions_by_key
        self._contribution_loaders_by_key: dict[str, BundledExtensionContributionLoaders] = (
            contribution_loaders_by_key
        )
        self._api_router_contributions: tuple[BundledApiRouterContribution, ...] | None = None
        self._server_declared_tool_contributions: (
            tuple[BundledServerDeclaredToolContribution, ...] | None
        ) = None
        self._runtime_tool_contributions: tuple[RuntimeToolSpec, ...] | None = None

    def list_extensions(self) -> tuple[BundledExtensionDefinition, ...]:
        return tuple(self._extensions_by_key.values())

    def get_extension(self, extension_key: str) -> BundledExtensionDefinition | None:
        return self._extensions_by_key.get(extension_key)

    def require_extension(self, extension_key: str) -> BundledExtensionDefinition:
        extension = self.get_extension(extension_key)
        if extension is None:
            raise KeyError(extension_key)
        return extension

    def list_api_router_contributions(self) -> tuple[BundledApiRouterContribution, ...]:
        contributions = self._api_router_contributions
        if contributions is None:
            contributions = self._materialize_contributions(lambda loaders: loaders.api_routers)
            self._api_router_contributions = contributions
        return contributions

    def list_server_declared_tool_contributions(
        self,
    ) -> tuple[BundledServerDeclaredToolContribution, ...]:
        contributions = self._server_declared_tool_contributions
        if contributions is None:
            contributions = self._materialize_contributions(
                lambda loaders: loaders.server_declared_tools
            )
            self._server_declared_tool_contributions = contributions
        return contributions

    def list_runtime_tool_contributions(self) -> tuple[RuntimeToolSpec, ...]:
        contributions = self._runtime_tool_contributions
        if contributions is None:
            contributions = self._materialize_contributions(lambda loaders: loaders.runtime_tools)
            self._runtime_tool_contributions = contributions
        return contributions

    def build_execution_provider_bundle(
        self,
        extension_keys: Iterable[str],
    ) -> ExecutionProviderBundle:
        bundles: list[ExecutionProviderBundle] = []
        for extension in self._selected_extensions(extension_keys):
            loaders = self._contribution_loaders_by_key.get(extension.key)
            if loaders is None or loaders.execution_provider_bundle is None:
                continue
            bundles.append(loaders.execution_provider_bundle())
        return merge_execution_provider_bundles(bundles)

    def runtime_dependency_surfaces_for_extensions(
        self,
        extension_keys: Iterable[str],
    ) -> tuple[str, ...]:
        surfaces: set[str] = set()
        for extension in self._selected_extensions(extension_keys):
            loaders = self._contribution_loaders_by_key.get(extension.key)
            if loaders is None:
                continue
            surfaces.update(loaders.runtime_dependency_surfaces)
        return tuple(sorted(surfaces))

    def package_private_mcp_tool_owners(self) -> dict[str, str]:
        owners: dict[str, str] = {}
        for extension in self.list_extensions():
            loaders = self._contribution_loaders_by_key.get(extension.key)
            if loaders is None:
                continue
            for tool_key in loaders.package_private_mcp_tool_keys:
                owners[tool_key.strip().lower()] = extension.key
        return owners

    def _selected_extensions(
        self,
        extension_keys: Iterable[str],
    ) -> tuple[BundledExtensionDefinition, ...]:
        selected_keys = set(extension_keys)
        return tuple(
            extension for extension in self.list_extensions() if extension.key in selected_keys
        )

    def _materialize_contributions(
        self,
        select_loader: Callable[
            [BundledExtensionContributionLoaders], Callable[[], tuple[_T, ...]] | None
        ],
    ) -> tuple[_T, ...]:
        contributions: list[_T] = []
        for extension in self.list_extensions():
            loaders = self._contribution_loaders_by_key.get(extension.key)
            if loaders is None:
                continue
            loader = select_loader(loaders)
            if loader is None:
                continue
            contributions.extend(loader())
        return tuple(contributions)


@lru_cache(maxsize=1)
def get_bundled_extension_registry() -> BundledExtensionRegistry:
    return BundledExtensionRegistry(
        (
            BundledExtensionDefinition(
                key=FINANCE_WORKSPACE_EXTENSION_KEY,
                label=FINANCE_WORKSPACE_LABEL,
                default_enabled=FINANCE_WORKSPACE_DEFAULT_ENABLED,
            ),
            BundledExtensionDefinition(
                key=DIGITAL_ORACLE_EXTENSION_KEY,
                label=DIGITAL_ORACLE_LABEL,
                default_enabled=DIGITAL_ORACLE_DEFAULT_ENABLED,
            ),
        ),
        contribution_loaders={
            FINANCE_WORKSPACE_EXTENSION_KEY: BundledExtensionContributionLoaders(
                api_routers=_load_finance_api_router_contributions,
                server_declared_tools=_load_finance_server_declared_tool_contributions,
                runtime_tools=_load_finance_runtime_tool_contributions,
                execution_provider_bundle=_load_finance_execution_provider_bundle,
                runtime_dependency_surfaces=(
                    "provider.fallbackQuote",
                    "provider.quote",
                    "provider.socialSentiment",
                ),
                package_private_mcp_tool_keys=("web_search_exa",),
            ),
            DIGITAL_ORACLE_EXTENSION_KEY: BundledExtensionContributionLoaders(
                server_declared_tools=_load_digital_oracle_server_declared_tool_contributions,
                runtime_tools=_load_digital_oracle_runtime_tool_contributions,
            ),
        },
    )


__all__ = [
    "BundledApiRouterContribution",
    "BundledServerDeclaredToolContribution",
    "BundledExtensionDefinition",
    "BundledExtensionRegistry",
    "get_bundled_extension_registry",
]
