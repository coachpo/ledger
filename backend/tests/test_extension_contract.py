import subprocess
import sys

from app.extensions.registry import INSTALLED_EXTENSIONS


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


def test_finance_extension_declares_static_api_routers() -> None:
    finance = next(
        extension for extension in INSTALLED_EXTENSIONS if extension.key == "signaldeck.finance"
    )

    assert {router.prefix for router in finance.api_routers} == {
        "/reports",
        "/templates",
    }
