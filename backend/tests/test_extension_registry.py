from __future__ import annotations

import pytest

from app.extensions.registry import (
    BundledExtensionDefinition,
    BundledExtensionRegistry,
    get_bundled_extension_registry,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


def test_bundled_extension_registry_discovers_finance_workspace_once() -> None:
    registry = get_bundled_extension_registry()

    extensions = registry.list_extensions()
    assert len(extensions) == 1
    extension = extensions[0]
    assert extension.key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert extension.label == "Finance Workspace"
    assert extension.default_enabled is True
    assert registry.get_extension(FINANCE_WORKSPACE_EXTENSION_KEY) is extension
    assert extension.tool_spec_registrars == (
        "app.extensions.signaldeck_finance.tool_specs:register",
    )
    assert extension.runtime_tool_registrars == (
        "app.extensions.signaldeck_finance.runtime_executors:register",
    )


def test_bundled_extension_registry_rejects_duplicate_keys() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    with pytest.raises(ValueError, match="Duplicate bundled extension key"):
        _ = BundledExtensionRegistry((extension, extension))


def test_bundled_extension_definition_keeps_only_operational_fields() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    assert isinstance(extension, BundledExtensionDefinition)
    assert set(BundledExtensionDefinition.__dataclass_fields__) == {
        "key",
        "label",
        "default_enabled",
        "tool_spec_registrars",
        "runtime_tool_registrars",
    }
    for removed_attribute in (
        "phase",
        "versioning_rule",
        "contribution_categories",
        "contributions",
        "scaffold",
    ):
        assert not hasattr(extension, removed_attribute)
