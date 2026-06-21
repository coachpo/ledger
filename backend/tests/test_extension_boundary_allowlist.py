from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FINANCE_EXTENSION_IMPORT_PREFIX = "app.extensions.signaldeck_finance"
APPROVED_STATIC_SCAN_EXCLUSIONS = ("app/extensions/registry.py",)
CORE_RUNTIME_PROVIDER_MODULES = {
    "app/agents/runtime_tools/types.py",
    "app/api/dependencies.py",
    "app/services/agent_execution_service.py",
    "app/services/execution_providers.py",
    "app/services/run_queue_service.py",
    "app/services/run_service.py",
    "app/services/workflow_package_service.py",
}
FINANCE_PROVIDER_PROTOCOL_MODULES = {
    "app.services.quote_provider",
    "app.services.social_sentiment_provider",
}
FORBIDDEN_CORE_SETTING_PREFIXES = (
    "digital_oracle_",
    "finance_",
    "quote_provider_",
    "quote_stale_",
)
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
    return _import_entries_matching(path, prefix=FINANCE_EXTENSION_IMPORT_PREFIX)


def _provider_protocol_import_entries(path: Path) -> list[str]:
    return _import_entries_matching(path, exact_modules=FINANCE_PROVIDER_PROTOCOL_MODULES)


def _import_entries_matching(
    path: Path,
    *,
    prefix: str | None = None,
    exact_modules: set[str] | None = None,
) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entries: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            entries.extend(_import_from_entries_matching(node, prefix, exact_modules))
        elif isinstance(node, ast.Import):
            entries.extend(
                alias.name
                for alias in node.names
                if _module_matches(alias.name, prefix, exact_modules)
            )
    return entries


def _import_from_entries_matching(
    node: ast.ImportFrom,
    prefix: str | None,
    exact_modules: set[str] | None,
) -> list[str]:
    module = node.module or ""
    if not _module_matches(module, prefix, exact_modules):
        return []
    return [f"{module}:{alias.name}" for alias in node.names]


def _module_matches(
    module: str,
    prefix: str | None,
    exact_modules: set[str] | None,
) -> bool:
    if prefix is not None and module.startswith(prefix):
        return True
    if exact_modules is not None and module in exact_modules:
        return True
    return False


def _core_settings_fields() -> tuple[str, ...]:
    path = BACKEND_ROOT / "app/core/config.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fields: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Settings":
            continue
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                fields.append(statement.target.id)
    return tuple(sorted(fields))


def test_shared_backend_has_no_finance_extension_imports_outside_private_registry() -> None:
    assert collect_shared_finance_imports() == {}


def test_core_runtime_provider_modules_do_not_import_finance_provider_protocols() -> None:
    actual: dict[str, tuple[str, ...]] = {}
    for relative_path in CORE_RUNTIME_PROVIDER_MODULES:
        path = BACKEND_ROOT / relative_path
        entries = tuple(sorted(set(_provider_protocol_import_entries(path))))
        if entries:
            actual[relative_path] = entries

    assert actual == {}


def test_preserved_finance_routes_use_only_approved_finance_dependencies() -> None:
    assert collect_approved_finance_route_imports() == APPROVED_FINANCE_ROUTE_IMPORTS


def test_private_registry_seam_is_the_only_static_scan_exclusion() -> None:
    assert APPROVED_STATIC_SCAN_EXCLUSIONS == ("app/extensions/registry.py",)
    registry_source = (BACKEND_ROOT / APPROVED_STATIC_SCAN_EXCLUSIONS[0]).read_text(
        encoding="utf-8"
    )

    for registrar in _APPROVED_REGISTRY_REGISTRARS:
        assert registrar in registry_source


def test_core_settings_do_not_own_extension_runtime_fields() -> None:
    forbidden_fields = tuple(
        field
        for field in _core_settings_fields()
        if field.startswith(FORBIDDEN_CORE_SETTING_PREFIXES)
    )

    assert forbidden_fields == ()


def test_core_config_does_not_own_finance_provider_constants() -> None:
    core_config_source = (BACKEND_ROOT / "app/core/config.py").read_text(encoding="utf-8")

    assert "_FINANCE_NEWS_PROVIDER_KEYS" not in core_config_source
