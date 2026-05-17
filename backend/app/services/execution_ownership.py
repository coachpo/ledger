from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageExecutionOwnership:
    package_id: int
    package_key: str
    package_version_id: int
    package_version: int
    manifest_hash: str
    compiled_hash: str
    workflow_key: str


__all__ = ["PackageExecutionOwnership"]
