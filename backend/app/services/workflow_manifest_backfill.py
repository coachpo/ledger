# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import WORKFLOW_MANIFEST_API_VERSION, Workflow
from app.services.workflow_manifest_decompiler import (
    WorkflowManifestDecompilerError,
    decompile_workflow_model,
)


@dataclass(frozen=True)
class WorkflowManifestBackfillFailure:
    key: str
    version: int
    message: str


@dataclass(frozen=True)
class WorkflowManifestBackfillReport:
    total: int
    converted: int
    failed: int
    persisted: int
    failures: list[WorkflowManifestBackfillFailure] = field(default_factory=list)


class WorkflowManifestBackfillError(RuntimeError):
    def __init__(self, report: WorkflowManifestBackfillReport) -> None:
        super().__init__("Workflow manifest backfill encountered lossy conversions")
        self.report = report


class WorkflowManifestBackfillService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def audit(
        self,
        *,
        persist: bool = False,
        fail_on_lossy: bool = False,
    ) -> WorkflowManifestBackfillReport:
        workflows = self._list_workflows()
        failures: list[WorkflowManifestBackfillFailure] = []
        converted_rows: list[tuple[Workflow, str]] = []

        for workflow in workflows:
            try:
                result = decompile_workflow_model(workflow)
            except (WorkflowManifestDecompilerError, ValueError, KeyError, TypeError) as exc:
                failures.append(
                    WorkflowManifestBackfillFailure(
                        key=workflow.key,
                        version=workflow.version,
                        message=str(exc),
                    )
                )
                continue
            converted_rows.append((workflow, result.source))

        report = WorkflowManifestBackfillReport(
            total=len(workflows),
            converted=len(converted_rows),
            failed=len(failures),
            persisted=0,
            failures=failures,
        )
        if failures and fail_on_lossy:
            self.session.rollback()
            raise WorkflowManifestBackfillError(report)
        if not persist:
            self.session.rollback()
            return report

        try:
            for workflow, manifest_source in converted_rows:
                workflow.manifest_api_version = WORKFLOW_MANIFEST_API_VERSION
                workflow.manifest_source = manifest_source
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return WorkflowManifestBackfillReport(
            total=report.total,
            converted=report.converted,
            failed=report.failed,
            persisted=len(converted_rows),
            failures=report.failures,
        )

    def _list_workflows(self) -> list[Workflow]:
        statement = select(Workflow).order_by(
            Workflow.key.asc(),
            Workflow.version.asc(),
            Workflow.id.asc(),
        )
        return list(self.session.scalars(statement))


__all__ = [
    "WorkflowManifestBackfillError",
    "WorkflowManifestBackfillFailure",
    "WorkflowManifestBackfillReport",
    "WorkflowManifestBackfillService",
]
