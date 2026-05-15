from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from typing import cast

from app.extensions.ledger_finance.ownership import (
    FINANCE_WORKSPACE_OWNERSHIP,
    ExtensionOwnershipArtifact,
)

DISCOVERY_CONTRIBUTION_CATEGORIES = frozenset(
    {
        "backend_api_routes",
        "native_runtime_tools",
        "frontend_finance_routes",
        "frontend_finance_navigation",
        "frontend_api_hooks_query_keys",
        "frontend_tool_discovery_contributions",
    }
)

EXECUTION_CONTRIBUTION_CATEGORIES = frozenset(
    {
        "backend_domain_services",
        "native_runtime_tools",
        "provider_integrations",
        "report_backed_memory_automation",
    }
)


@dataclass(frozen=True, slots=True)
class ExtensionContribution:
    extension_key: str
    category: str
    summary: str
    surface: str
    owner_extension_key: str
    dependencies: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "extensionKey": self.extension_key,
            "category": self.category,
            "summary": self.summary,
            "surface": self.surface,
            "ownerExtensionKey": self.owner_extension_key,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class BundledExtensionDefinition:
    key: str
    label: str
    default_enabled: bool
    phase: str
    versioning_rule: str
    contribution_categories: tuple[str, ...]
    dependencies: tuple[str, ...]
    contributions: tuple[ExtensionContribution, ...]
    scaffold: FinanceWorkspaceExtensionScaffold | None = None

    @classmethod
    def from_ownership_artifact(
        cls,
        artifact: ExtensionOwnershipArtifact,
        *,
        dependencies: Iterable[str] = (),
    ) -> BundledExtensionDefinition:
        dependency_tuple = tuple(dependencies)
        contributions = tuple(
            ExtensionContribution(
                extension_key=artifact.extension_key,
                category=group.category,
                summary=group.summary,
                surface=surface,
                owner_extension_key=artifact.extension_key,
                dependencies=dependency_tuple,
            )
            for group in artifact.extension_owned_public_surfaces
            for surface in group.surfaces
        )
        return cls(
            key=artifact.extension_key,
            label=artifact.label,
            default_enabled=artifact.default_enabled,
            phase=artifact.phase,
            versioning_rule=artifact.versioning_rule,
            contribution_categories=artifact.contribution_categories,
            dependencies=dependency_tuple,
            contributions=contributions,
            scaffold=get_finance_workspace_extension_scaffold(),
        )


@dataclass(frozen=True, slots=True)
class ExtensionContributionRegistrar:
    category: str
    summary: str
    registrar: str


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceExtensionScaffold:
    tool_specs: tuple[ExtensionContributionRegistrar, ...]
    runtime_executors: tuple[ExtensionContributionRegistrar, ...]
    provider_factories: tuple[ExtensionContributionRegistrar, ...]
    api_routers: tuple[ExtensionContributionRegistrar, ...]
    template_report_memory_hooks: tuple[ExtensionContributionRegistrar, ...]
    docs_metadata: tuple[ExtensionContributionRegistrar, ...]


FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS = (
    ExtensionContributionRegistrar(
        category="tool_specs",
        summary="Finance workspace server-declared tool metadata is registered here.",
        registrar="app.extensions.ledger_finance.tool_specs:register",
    ),
    ExtensionContributionRegistrar(
        category="runtime_executors",
        summary="Finance workspace runtime tool specs and executors are registered here.",
        registrar="app.extensions.ledger_finance.runtime_executors:register",
    ),
    ExtensionContributionRegistrar(
        category="provider_factories",
        summary="Finance workspace owns quote and social sentiment provider factories here.",
        registrar="app.extensions.ledger_finance.provider_factories:register",
    ),
    ExtensionContributionRegistrar(
        category="api_routers",
        summary="Finance workspace owns preserved `/api/v1` router registrations here.",
        registrar="app.extensions.ledger_finance.api_routers:register",
    ),
    ExtensionContributionRegistrar(
        category="template_report_memory_hooks",
        summary="Template, report, memory, return-resolution, and follow-up hooks register here.",
        registrar="app.extensions.ledger_finance.hooks:register",
    ),
    ExtensionContributionRegistrar(
        category="docs_metadata",
        summary="Docs metadata is scaffolded here for the bundled extension contract.",
        registrar="app.extensions.ledger_finance.docs:register",
    ),
)


def load_extension_contribution_registrar(registrar: str) -> tuple[object, ...]:
    module_name, separator, attribute_name = registrar.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError(f"Invalid extension contribution registrar {registrar!r}")
    module = import_module(module_name)
    raw_registrar = getattr(module, attribute_name)
    if not callable(raw_registrar):
        raise ValueError(f"Extension contribution registrar {registrar!r} is not callable")
    contribution_registrar = cast(Callable[[], Iterable[object]], raw_registrar)
    return tuple(contribution_registrar())


def get_finance_workspace_extension_scaffold() -> FinanceWorkspaceExtensionScaffold:
    return FinanceWorkspaceExtensionScaffold(
        tool_specs=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[0],),
        runtime_executors=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[1],),
        provider_factories=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[2],),
        api_routers=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[3],),
        template_report_memory_hooks=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[4],),
        docs_metadata=(FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS[5],),
    )


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

    def list_contributions(
        self,
        *,
        extension_keys: set[str] | None = None,
        categories: set[str] | frozenset[str] | None = None,
    ) -> tuple[ExtensionContribution, ...]:
        contributions: list[ExtensionContribution] = []
        for extension in self.list_extensions():
            if extension_keys is not None and extension.key not in extension_keys:
                continue
            contributions.extend(
                contribution
                for contribution in extension.contributions
                if categories is None or contribution.category in categories
            )
        return tuple(contributions)

    def list_discovery_contributions(
        self,
        *,
        enabled_extension_keys: set[str],
    ) -> tuple[ExtensionContribution, ...]:
        return self.list_contributions(
            extension_keys=enabled_extension_keys,
            categories=DISCOVERY_CONTRIBUTION_CATEGORIES,
        )

    def list_execution_contributions(
        self,
        *,
        enabled_extension_keys: set[str],
    ) -> tuple[ExtensionContribution, ...]:
        return self.list_contributions(
            extension_keys=enabled_extension_keys,
            categories=EXECUTION_CONTRIBUTION_CATEGORIES,
        )


@lru_cache(maxsize=1)
def get_bundled_extension_registry() -> BundledExtensionRegistry:
    return BundledExtensionRegistry(
        (
            BundledExtensionDefinition.from_ownership_artifact(
                FINANCE_WORKSPACE_OWNERSHIP,
            ),
        )
    )


__all__ = [
    "BundledExtensionDefinition",
    "BundledExtensionRegistry",
    "DISCOVERY_CONTRIBUTION_CATEGORIES",
    "EXECUTION_CONTRIBUTION_CATEGORIES",
    "ExtensionContribution",
    "ExtensionContributionRegistrar",
    "FinanceWorkspaceExtensionScaffold",
    "FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS",
    "get_bundled_extension_registry",
    "get_finance_workspace_extension_scaffold",
    "load_extension_contribution_registrar",
]
