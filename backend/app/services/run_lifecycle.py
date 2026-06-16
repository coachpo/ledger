from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.services.execution_providers import ExecutionProviderBundle


@dataclass(frozen=True, slots=True)
class WorkflowPackageStartContext:
    session: Session
    provider_bundle: ExecutionProviderBundle
    now: datetime


WorkflowPackageStartHook = Callable[[WorkflowPackageStartContext], None]


@dataclass(frozen=True, slots=True)
class ExtensionRunLifecycleHooks:
    extension_key: str
    on_workflow_package_start: WorkflowPackageStartHook | None = None


__all__ = [
    "ExtensionRunLifecycleHooks",
    "WorkflowPackageStartContext",
    "WorkflowPackageStartHook",
]
