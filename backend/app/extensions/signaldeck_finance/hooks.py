from __future__ import annotations

from app.services.run_lifecycle import ExtensionRunLifecycleHooks


def register_run_lifecycle_hooks() -> tuple[ExtensionRunLifecycleHooks, ...]:
    return ()


__all__ = ["register_run_lifecycle_hooks"]
