from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services.execution_providers import ExecutionProviderBundle

if TYPE_CHECKING:
    from app.services.memory_follow_up_service import MemoryFollowUpEvaluator


@dataclass(frozen=True, slots=True)
class WorkflowPackageStartContext:
    session: Session
    provider_bundle: ExecutionProviderBundle
    now: datetime


WorkflowPackageStartHook = Callable[[WorkflowPackageStartContext], None]
MemoryFollowUpEvaluatorFactory = Callable[
    [WorkflowPackageStartContext],
    Sequence["MemoryFollowUpEvaluator"],
]


@dataclass(frozen=True, slots=True)
class ExtensionRunLifecycleHooks:
    extension_key: str
    on_workflow_package_start: WorkflowPackageStartHook | None = None
    memory_follow_up_evaluators: MemoryFollowUpEvaluatorFactory | None = None


__all__ = [
    "ExtensionRunLifecycleHooks",
    "MemoryFollowUpEvaluatorFactory",
    "WorkflowPackageStartContext",
    "WorkflowPackageStartHook",
]
