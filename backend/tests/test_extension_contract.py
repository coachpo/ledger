import subprocess
import sys

import pytest

from app.agents.runtime_tools.types import RuntimeToolSpec
from app.extensions import registry
from app.extensions.contract import Extension
from app.extensions.registry import INSTALLED_EXTENSIONS


def _runtime_tool_spec(key: str) -> RuntimeToolSpec:
    return RuntimeToolSpec(
        key=key,
        openai_function_name=key.replace(".", "_"),
        display_name=key,
        description=key,
        parameters_schema={"type": "object", "properties": {}},
        guidance="",
        sort_order=0,
        denied_code="denied",
        denied_message="Denied",
        parser=lambda _arguments_json: {},
        executor=lambda _context, _arguments: {},
    )


def test_installed_extensions_import_cleanly_in_fresh_interpreter() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.extensions.registry import INSTALLED_EXTENSIONS; "
                "print(','.join(extension.key for extension in INSTALLED_EXTENSIONS))"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "signaldeck.finance" in result.stdout
    assert "signaldeck.digital_oracle" in result.stdout


def test_installed_extensions_expose_unique_owner_qualified_tool_keys() -> None:
    keys = [
        declaration.key
        for extension in INSTALLED_EXTENSIONS
        for declaration in extension.tool_declarations
    ]

    assert keys
    assert len(keys) == len(set(keys))
    assert all(
        declaration.key.startswith(f"{extension.key}.")
        for extension in INSTALLED_EXTENSIONS
        for declaration in extension.tool_declarations
    )


def test_every_extension_declares_key() -> None:
    assert all(extension.key for extension in INSTALLED_EXTENSIONS)


def test_extension_registry_rejects_duplicate_runtime_tool_spec_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_key = "signaldeck.test.lookup"
    monkeypatch.setattr(
        registry,
        "INSTALLED_EXTENSIONS",
        (
            Extension(
                key="signaldeck.alpha", runtime_tool_specs=(_runtime_tool_spec(duplicate_key),)
            ),
            Extension(
                key="signaldeck.beta", runtime_tool_specs=(_runtime_tool_spec(duplicate_key),)
            ),
        ),
    )

    with pytest.raises(RuntimeError, match=f"duplicate runtime tool spec key: {duplicate_key}"):
        registry._assert_unique_extension_and_tool_keys()


def test_extension_registry_rejects_duplicate_package_private_mcp_tool_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        registry,
        "INSTALLED_EXTENSIONS",
        (
            Extension(key="signaldeck.alpha", package_private_mcp_tool_keys=("web_search_exa",)),
            Extension(key="signaldeck.beta", package_private_mcp_tool_keys=(" WEB_SEARCH_EXA ",)),
        ),
    )

    with pytest.raises(
        RuntimeError, match="duplicate package-private MCP tool key: web_search_exa"
    ):
        registry._assert_unique_extension_and_tool_keys()


def test_finance_extension_declares_static_api_routers() -> None:
    finance = next(
        extension for extension in INSTALLED_EXTENSIONS if extension.key == "signaldeck.finance"
    )

    assert {router.prefix for router in finance.api_routers} == {
        "/reports",
        "/templates",
    }


def test_extension_management_api_is_not_mounted(client) -> None:
    response = client.get("/api/extensions")

    assert response.status_code == 404
