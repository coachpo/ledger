"""Bundled extension contribution contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BundledServerDeclaredToolContribution:
    key: str
    display_name: str
    description: str
    module: str
    owner_extension_key: str | None = None


__all__ = [
    "BundledServerDeclaredToolContribution",
]
