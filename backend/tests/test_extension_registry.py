from __future__ import annotations

import subprocess
import sys
import textwrap
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import pytest

from app.extensions.registry import BundledExtensionRegistry, get_bundled_extension_registry
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)


class _DigitalOracleOwnershipModule(Protocol):
    DIGITAL_ORACLE_DEFAULT_ENABLED: bool
    DIGITAL_ORACLE_EXTENSION_KEY: str
    DIGITAL_ORACLE_LABEL: str
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS: tuple[str, ...]


class _DigitalOracleConfigModule(Protocol):
    DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE: bool
    DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE: bool

    def get_digital_oracle_provider_config(self) -> object: ...


_digital_oracle_ownership = cast(
    _DigitalOracleOwnershipModule,
    cast(object, import_module("app.extensions.signaldeck_digital_oracle.ownership")),
)
_digital_oracle_config = cast(
    _DigitalOracleConfigModule,
    cast(object, import_module("app.extensions.signaldeck_digital_oracle.config")),
)
DIGITAL_ORACLE_EXTENSION_KEY = _digital_oracle_ownership.DIGITAL_ORACLE_EXTENSION_KEY
DIGITAL_ORACLE_LABEL = _digital_oracle_ownership.DIGITAL_ORACLE_LABEL
DIGITAL_ORACLE_DEFAULT_ENABLED = _digital_oracle_ownership.DIGITAL_ORACLE_DEFAULT_ENABLED
DIGITAL_ORACLE_RUNTIME_TOOL_KEYS = _digital_oracle_ownership.DIGITAL_ORACLE_RUNTIME_TOOL_KEYS

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_optional_dependency_import_smoke() -> subprocess.CompletedProcess[str]:
    script = textwrap.dedent(
        """
        import builtins

        blocked_roots = {"digital_oracle", "yfinance"}
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".", 1)[0]
            if root in blocked_roots:
                raise AssertionError(f"unexpected import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from app.extensions.signaldeck_digital_oracle import config as digital_oracle_config
        from app.main import create_app

        assert digital_oracle_config.DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE is False
        assert digital_oracle_config.DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE is False
        app = create_app(init_database=False)
        assert app.title == "SignalDeck Backend"
        print("ok")
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
    )


def test_digital_oracle_provider_config_disables_optional_dependencies() -> None:
    assert _digital_oracle_config.DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE is False
    assert _digital_oracle_config.DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE is False


def test_digital_oracle_app_startup_and_imports_do_not_require_optional_dependencies() -> None:
    result = _run_optional_dependency_import_smoke()

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip().endswith("ok")


def test_bundled_extension_registry_discovers_default_enabled_extensions() -> None:
    registry = get_bundled_extension_registry()

    extensions = registry.list_extensions()
    assert [extension.key for extension in extensions] == [
        FINANCE_WORKSPACE_EXTENSION_KEY,
        DIGITAL_ORACLE_EXTENSION_KEY,
    ]
    extensions_by_key = {extension.key: extension for extension in extensions}
    assert extensions_by_key[FINANCE_WORKSPACE_EXTENSION_KEY].label == "Finance Workspace"
    assert extensions_by_key[FINANCE_WORKSPACE_EXTENSION_KEY].default_enabled is True
    assert extensions_by_key[DIGITAL_ORACLE_EXTENSION_KEY].label == DIGITAL_ORACLE_LABEL
    assert (
        extensions_by_key[DIGITAL_ORACLE_EXTENSION_KEY].default_enabled
        is DIGITAL_ORACLE_DEFAULT_ENABLED
    )
    assert (
        registry.get_extension(FINANCE_WORKSPACE_EXTENSION_KEY)
        is extensions_by_key[FINANCE_WORKSPACE_EXTENSION_KEY]
    )
    assert (
        registry.get_extension(DIGITAL_ORACLE_EXTENSION_KEY)
        is extensions_by_key[DIGITAL_ORACLE_EXTENSION_KEY]
    )
    assert (
        registry.runtime_dependency_surfaces_for_extensions((DIGITAL_ORACLE_EXTENSION_KEY,)) == ()
    )
    assert (
        registry.build_execution_provider_bundle((DIGITAL_ORACLE_EXTENSION_KEY,)).contributions
        == ()
    )
    assert DIGITAL_ORACLE_EXTENSION_KEY not in registry.package_private_mcp_tool_owners().values()
    assert {contribution.surface for contribution in registry.list_api_router_contributions()} == {
        "/api/v1/templates",
        "/api/v1/reports",
    }
    expected_tool_keys = set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) | set(
        DIGITAL_ORACLE_RUNTIME_TOOL_KEYS
    )
    server_tool_contributions = registry.list_server_declared_tool_contributions()
    runtime_tool_contributions = registry.list_runtime_tool_contributions()
    server_tool_keys_by_owner = {
        owner_key: {
            contribution.key
            for contribution in server_tool_contributions
            if contribution.owner_extension_key == owner_key
        }
        for owner_key in (FINANCE_WORKSPACE_EXTENSION_KEY, DIGITAL_ORACLE_EXTENSION_KEY)
    }
    runtime_tool_keys_by_owner = {
        owner_key: {
            contribution.key
            for contribution in runtime_tool_contributions
            if contribution.owner_extension_key == owner_key
        }
        for owner_key in (FINANCE_WORKSPACE_EXTENSION_KEY, DIGITAL_ORACLE_EXTENSION_KEY)
    }
    assert {contribution.key for contribution in server_tool_contributions} == expected_tool_keys
    assert {contribution.key for contribution in runtime_tool_contributions} == expected_tool_keys
    assert server_tool_keys_by_owner[FINANCE_WORKSPACE_EXTENSION_KEY] == set(
        FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS
    )
    assert runtime_tool_keys_by_owner[FINANCE_WORKSPACE_EXTENSION_KEY] == set(
        FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS
    )
    assert server_tool_keys_by_owner[DIGITAL_ORACLE_EXTENSION_KEY] == set(
        DIGITAL_ORACLE_RUNTIME_TOOL_KEYS
    )
    assert runtime_tool_keys_by_owner[DIGITAL_ORACLE_EXTENSION_KEY] == set(
        DIGITAL_ORACLE_RUNTIME_TOOL_KEYS
    )
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS).isdisjoint(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS)


def test_bundled_extension_registry_rejects_duplicate_keys() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    with pytest.raises(ValueError, match="Duplicate bundled extension key"):
        _ = BundledExtensionRegistry((extension, extension))
