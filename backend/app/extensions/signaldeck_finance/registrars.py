from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from app.extensions import BundledApiRouterContribution, BundledServerDeclaredToolContribution
from app.services.execution_providers import ExecutionProviderBundle

if TYPE_CHECKING:
    from app.agents.runtime_tools.types import RuntimeToolSpec


class _ApiRouterRegistrarModule(Protocol):
    def register(self) -> tuple[BundledApiRouterContribution, ...]: ...


def load_api_router_contributions() -> tuple[BundledApiRouterContribution, ...]:
    module = cast(
        _ApiRouterRegistrarModule,
        __import__(
            "app.extensions.signaldeck_finance.api_routers",
            fromlist=("register",),
        ),
    )
    return module.register()


def load_server_declared_tool_contributions() -> tuple[BundledServerDeclaredToolContribution, ...]:
    from app.extensions.signaldeck_finance.tool_specs import register

    return register()


def load_runtime_tool_contributions() -> tuple[RuntimeToolSpec, ...]:
    from app.extensions.signaldeck_finance.runtime_executors import register

    runtime_tool_contributions = register()
    return runtime_tool_contributions


def load_execution_provider_bundle() -> ExecutionProviderBundle:
    from app.extensions.signaldeck_finance.provider_factories import (
        create_execution_provider_bundle,
    )

    return create_execution_provider_bundle()


__all__ = [
    "load_api_router_contributions",
    "load_execution_provider_bundle",
    "load_runtime_tool_contributions",
    "load_server_declared_tool_contributions",
]
