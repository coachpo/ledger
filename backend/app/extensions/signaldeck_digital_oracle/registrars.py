from __future__ import annotations

from typing import TYPE_CHECKING

from app.extensions import BundledServerDeclaredToolContribution

if TYPE_CHECKING:
    from app.agents.runtime_tools.types import RuntimeToolSpec


def load_server_declared_tool_contributions() -> tuple[BundledServerDeclaredToolContribution, ...]:
    from app.extensions.signaldeck_digital_oracle.tool_specs import register

    return register()


def load_runtime_tool_contributions() -> tuple[RuntimeToolSpec, ...]:
    from app.extensions.signaldeck_digital_oracle.runtime_executors import register

    return register()


__all__ = [
    "load_runtime_tool_contributions",
    "load_server_declared_tool_contributions",
]
