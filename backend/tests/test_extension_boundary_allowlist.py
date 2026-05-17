from __future__ import annotations

import ast
from pathlib import Path

from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FINANCE_EXTENSION_IMPORT_PREFIX = "app.extensions.signaldeck_finance"
APPROVED_STATIC_SCAN_EXCLUSIONS = ("app/extensions/registry.py",)
FINANCE_DEPENDENCIES_MODULE = "app.extensions.signaldeck_finance.dependencies"
APPROVED_FINANCE_ROUTE_IMPORTS = {
    "app/api/balances.py": (f"{FINANCE_DEPENDENCIES_MODULE}:get_balance_service",),
    "app/api/market_data.py": (f"{FINANCE_DEPENDENCIES_MODULE}:get_market_data_service",),
    "app/api/portfolios.py": (f"{FINANCE_DEPENDENCIES_MODULE}:get_portfolio_service",),
    "app/api/positions.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:get_csv_import_service",
        f"{FINANCE_DEPENDENCIES_MODULE}:get_position_service",
    ),
    "app/api/reports.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:get_report_service",
        f"{FINANCE_DEPENDENCIES_MODULE}:get_template_compiler_service",
        f"{FINANCE_DEPENDENCIES_MODULE}:get_text_template_service",
    ),
    "app/api/templates.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:get_template_compiler_service",
        f"{FINANCE_DEPENDENCIES_MODULE}:get_text_template_service",
    ),
    "app/api/trading_operations.py": (
        f"{FINANCE_DEPENDENCIES_MODULE}:get_trading_operation_service",
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


def collect_shared_finance_imports() -> dict[str, tuple[str, ...]]:
    actual: dict[str, tuple[str, ...]] = {}
    for path in _iter_scanned_app_python_files():
        relative_path = path.relative_to(BACKEND_ROOT).as_posix()
        entries = _unapproved_finance_import_entries(relative_path, path)
        if entries:
            actual[relative_path] = entries
    return actual


def collect_approved_finance_route_imports() -> dict[str, tuple[str, ...]]:
    actual: dict[str, tuple[str, ...]] = {}
    for relative_path in APPROVED_FINANCE_ROUTE_IMPORTS:
        path = BACKEND_ROOT / relative_path
        entries = tuple(sorted(set(_finance_import_entries(path))))
        if entries:
            actual[relative_path] = entries
    return actual


def _iter_scanned_app_python_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted((BACKEND_ROOT / "app").rglob("*.py"))
        if _is_scanned_shared_app_file(path)
    )


def _is_scanned_shared_app_file(path: Path) -> bool:
    relative = path.relative_to(BACKEND_ROOT)
    if relative.as_posix() in APPROVED_STATIC_SCAN_EXCLUSIONS:
        return False
    return relative.parts[:3] != ("app", "extensions", "signaldeck_finance")


def _unapproved_finance_import_entries(relative_path: str, path: Path) -> tuple[str, ...]:
    approved_entries = set(APPROVED_FINANCE_ROUTE_IMPORTS.get(relative_path, ()))
    entries = set(_finance_import_entries(path)) - approved_entries
    return tuple(sorted(entries))


def _finance_import_entries(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entries: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            entries.extend(_import_from_entries(node))
        elif isinstance(node, ast.Import):
            entries.extend(
                alias.name
                for alias in node.names
                if alias.name.startswith(FINANCE_EXTENSION_IMPORT_PREFIX)
            )
    return entries


def _import_from_entries(node: ast.ImportFrom) -> list[str]:
    module = node.module or ""
    if not module.startswith(FINANCE_EXTENSION_IMPORT_PREFIX):
        return []
    return [f"{module}:{alias.name}" for alias in node.names]


def test_shared_backend_has_no_finance_extension_imports_outside_private_registry() -> None:
    assert collect_shared_finance_imports() == {}


def test_preserved_finance_routes_use_only_approved_finance_dependencies() -> None:
    assert collect_approved_finance_route_imports() == APPROVED_FINANCE_ROUTE_IMPORTS


def test_private_registry_seam_is_the_only_static_scan_exclusion() -> None:
    assert APPROVED_STATIC_SCAN_EXCLUSIONS == ("app/extensions/registry.py",)
    registry_source = (BACKEND_ROOT / APPROVED_STATIC_SCAN_EXCLUSIONS[0]).read_text(
        encoding="utf-8"
    )

    for registrar in _APPROVED_REGISTRY_REGISTRARS:
        assert registrar in registry_source
    assert 'import_module("app.extensions.signaldeck_finance' not in registry_source
    assert "from importlib import import_module" not in registry_source


def test_api_tools_module_leakage_allowlist_is_retired() -> None:
    private_modules = {
        spec.key: spec.module
        for spec in SERVER_DECLARED_TOOL_SPECS
        if spec.module.startswith(FINANCE_EXTENSION_IMPORT_PREFIX)
    }

    assert private_modules
    assert all(
        module == "app.extensions.signaldeck_finance.tool_specs"
        for module in private_modules.values()
    )


def test_transition_boundary_allowlist_is_removed() -> None:
    source = Path(__file__).read_text(encoding="utf-8")

    assert "TRANSITION" + "_BOUNDARY_ALLOWLIST" not in source
    assert "SharedFinance" + "ImportDebt" not in source
