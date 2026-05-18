from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.run import Run
from app.repositories.workflow import WorkflowRepository
from app.services.execution_plan import ExecutionPlan
from app.services.legacy_authoring import (
    LEGACY_AUTHORING_RUNTIME_BLOCKED,
    raise_legacy_global_authoring_runtime_blocked,
)

LEGACY_AUTHORING_CLASSIFICATION = LEGACY_AUTHORING_RUNTIME_BLOCKED


@dataclass(frozen=True)
class ExecutionPlanBuilderError(Exception):
    code: str
    message: str
    details: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


class ExecutionPlanBuilder:
    def __init__(self, session: Session) -> None:
        self.workflow_repository = WorkflowRepository(session)

    def build_target_plan(
        self,
        target_kind: str,
        target_id: int,
        *,
        version: int | None = None,
    ) -> ExecutionPlan:
        del target_id, version
        raise_legacy_global_authoring_runtime_blocked(target_kind)

    def build_plan_for_run(self, run: Run) -> ExecutionPlan:
        raise_legacy_global_authoring_runtime_blocked(run.target_kind)


__all__ = [
    "ExecutionPlanBuilder",
    "ExecutionPlanBuilderError",
    "LEGACY_AUTHORING_CLASSIFICATION",
]
