from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FINANCE_EXTENSION_IMPORT_PREFIX = "app.extensions.signaldeck_finance"
FINANCE_DEPENDENCIES_MODULE = "app.extensions.signaldeck_finance.dependencies"
APPROVED_FINANCE_ROUTE_IMPORTS = {
    "app/api/balances.py": (f"{FINANCE_DEPENDENCIES_MODULE}:BalanceServiceDependency",),
    "app/api/market_data.py": (f"{FINANCE_DEPENDENCIES_MODULE}:MarketDataServiceDependency",),
    "app/api/portfolios.py": (f"{FINANCE_DEPENDENCIES_MODULE}:PortfolioServiceDependency",),
    "app/api/positions.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:CsvImportServiceDependency",
        f"{FINANCE_DEPENDENCIES_MODULE}:PositionServiceDependency",
    ),
    "app/api/reports.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:ReportServiceDependency",
        f"{FINANCE_DEPENDENCIES_MODULE}:TemplateCompilerServiceDependency",
        f"{FINANCE_DEPENDENCIES_MODULE}:TextTemplateServiceDependency",
    ),
    "app/api/templates.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:TemplateCompilerServiceDependency",
        f"{FINANCE_DEPENDENCIES_MODULE}:TextTemplateServiceDependency",
    ),
    "app/api/trading_operations.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:TradingOperationServiceDependency",
    ),
}
_APPROVED_REGISTRY_REGISTRARS = (
    ".signaldeck_finance.registrars",
    "_load_finance_api_router_contributions",
    "_load_finance_execution_provider_bundle",
    "_load_finance_run_lifecycle_hooks",
    "_load_finance_runtime_tool_contributions",
    "_load_finance_server_declared_tool_contributions",
)


def collect_approved_finance_route_imports() -> dict[str, tuple[str, ...]]:
    actual: dict[str, tuple[str, ...]] = {}
    for relative_path in APPROVED_FINANCE_ROUTE_IMPORTS:
        path = BACKEND_ROOT / relative_path
        entries = tuple(sorted(set(_finance_import_entries(path))))
        if entries:
            actual[relative_path] = entries
    return actual


def _finance_import_entries(path: Path) -> list[str]:
    return _import_entries_matching(path, prefix=FINANCE_EXTENSION_IMPORT_PREFIX)


def _import_entries_matching(
    path: Path,
    *,
    prefix: str | None = None,
) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entries: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            entries.extend(_import_from_entries_matching(node, prefix))
        elif isinstance(node, ast.Import):
            entries.extend(
                alias.name for alias in node.names if _module_matches(alias.name, prefix)
            )
    return entries


def _import_from_entries_matching(
    node: ast.ImportFrom,
    prefix: str | None,
) -> list[str]:
    module = node.module or ""
    if not _module_matches(module, prefix):
        return []
    return [f"{module}:{alias.name}" for alias in node.names]


def _module_matches(
    module: str,
    prefix: str | None,
) -> bool:
    return prefix is not None and module.startswith(prefix)


def test_preserved_finance_routes_use_only_approved_finance_dependencies() -> None:
    assert collect_approved_finance_route_imports() == APPROVED_FINANCE_ROUTE_IMPORTS


def test_private_registry_declares_static_finance_registrars() -> None:
    registry_source = (BACKEND_ROOT / "app/extensions/registry.py").read_text(encoding="utf-8")

    for registrar in _APPROVED_REGISTRY_REGISTRARS:
        assert registrar in registry_source
