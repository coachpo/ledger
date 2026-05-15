from __future__ import annotations

import pytest

from app.extensions.ledger_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.extensions.registry import (
    BundledExtensionDefinition,
    BundledExtensionRegistry,
    get_bundled_extension_registry,
)


def test_bundled_extension_registry_discovers_finance_workspace_once() -> None:
    registry = get_bundled_extension_registry()

    extensions = registry.list_extensions()
    assert len(extensions) == 1
    assert extensions[0].key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert registry.get_extension(FINANCE_WORKSPACE_EXTENSION_KEY) is extensions[0]
    assert registry.list_discovery_contributions(
        enabled_extension_keys={FINANCE_WORKSPACE_EXTENSION_KEY}
    )
    assert registry.list_execution_contributions(
        enabled_extension_keys={FINANCE_WORKSPACE_EXTENSION_KEY}
    )
    assert extensions[0].scaffold is not None
    assert len(extensions[0].scaffold.tool_specs) == 1


def test_bundled_extension_registry_rejects_duplicate_keys() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    with pytest.raises(ValueError, match="Duplicate bundled extension key"):
        BundledExtensionRegistry((extension, extension))


def test_bundled_extension_definition_scaffold_is_accessible() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    assert isinstance(extension, BundledExtensionDefinition)
    assert extension.scaffold is not None
    assert extension.scaffold.docs_metadata[0].category == "docs_metadata"
