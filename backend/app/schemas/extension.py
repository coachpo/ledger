from __future__ import annotations

from app.schemas.common import CamelModel


class ExtensionToggleRequest(CamelModel):
    enabled: bool


class ExtensionRead(CamelModel):
    key: str
    label: str
    enabled: bool


class ExtensionListRead(CamelModel):
    items: list[ExtensionRead]


__all__ = [
    "ExtensionListRead",
    "ExtensionRead",
    "ExtensionToggleRequest",
]
