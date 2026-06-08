from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.services.extension_service import ExtensionService, ResolvedExtensionState


class ExtensionGate(Protocol):
    def require_enabled(
        self,
        extension_key: str,
        *,
        surface: str,
    ) -> ResolvedExtensionState: ...


def require_extension_enabled(
    session: Session,
    *,
    extension_key: str,
    surface: str,
) -> ResolvedExtensionState:
    return ExtensionService(session).require_enabled(extension_key, surface=surface)


__all__ = [
    "ExtensionGate",
    "require_extension_enabled",
]
