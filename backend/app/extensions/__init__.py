"""Bundled extension ownership and registry metadata."""

from app.extensions.registry import (
    BundledExtensionDefinition,
    BundledExtensionRegistry,
    ExtensionContribution,
    get_bundled_extension_registry,
)

__all__ = [
    "BundledExtensionDefinition",
    "BundledExtensionRegistry",
    "ExtensionContribution",
    "get_bundled_extension_registry",
]
