"""Bundled SignalDeck finance workspace extension identity."""

from __future__ import annotations

from app.api.reports import router as reports_router
from app.api.templates import router as templates_router
from app.extensions.contract import Extension
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_DENIED_CODE,
    FINANCE_WORKSPACE_DENIED_MESSAGES,
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_finance.provider_factories import (
    register as register_provider_factories,
)
from app.extensions.signaldeck_finance.tool_specs import (
    FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS,
)

EXTENSION = Extension(
    key=FINANCE_WORKSPACE_EXTENSION_KEY,
    api_routers=(templates_router, reports_router),
    tool_declarations=FINANCE_WORKSPACE_SERVER_DECLARED_TOOL_SPECS,
    provider_factories=dict(register_provider_factories()),
)

__all__ = [
    "EXTENSION",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_DENIED_CODE",
    "FINANCE_WORKSPACE_DENIED_MESSAGES",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
]
