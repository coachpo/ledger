from __future__ import annotations

from app.extensions.registry import (
    FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS,
    ExtensionContributionRegistrar,
    FinanceWorkspaceExtensionScaffold,
    get_finance_workspace_extension_scaffold,
)

__all__ = [
    "ExtensionContributionRegistrar",
    "FinanceWorkspaceExtensionScaffold",
    "FINANCE_WORKSPACE_EXTENSIBLE_CONTRIBUTIONS",
    "get_finance_workspace_extension_scaffold",
]
