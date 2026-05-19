from __future__ import annotations

from fastapi import status

from app.core.errors import ApiError
from app.schemas.memory import (
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryEntryRead,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
    MemoryWriteResult,
)

_RETIRED_MESSAGE = (
    "Report-backed memory has been retired; canonical memory now lives in "
    "platform core memory tables. Legacy agent_memory reports are report-domain "
    "artifacts only."
)


def report_backed_memory_retired_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_410_GONE,
        code="report_backed_memory_retired",
        message=_RETIRED_MESSAGE,
    )


class ReportBackedMemoryStore:
    """Retired adapter kept as a fail-closed boundary for stale imports."""

    def __init__(self, session: object) -> None:
        self.session = session

    @staticmethod
    def memory_id_from_report_id(report_id: int) -> str:
        del report_id
        raise report_backed_memory_retired_error()

    def create_pending(
        self,
        payload: MemoryWriteRequest,
        *,
        event_context: object | None = None,
    ) -> MemoryWriteResult:
        del payload, event_context
        raise report_backed_memory_retired_error()

    def get(self, memory_id: str) -> MemoryEntryRead:
        del memory_id
        raise report_backed_memory_retired_error()

    def query(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        del query
        raise report_backed_memory_retired_error()

    def resolve(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        del memory_id, outcome
        raise report_backed_memory_retired_error()

    def append_reflection(self, memory_id: str, reflection: MemoryReflection) -> MemoryEntryRead:
        del memory_id, reflection
        raise report_backed_memory_retired_error()

    def record_review(self, memory_id: str, **kwargs: object) -> MemoryEntryRead:
        del memory_id, kwargs
        raise report_backed_memory_retired_error()

    def list_artifacts_for_run(self, run_id: int) -> list[MemoryArtifactRead]:
        del run_id
        raise report_backed_memory_retired_error()

    def audit_links(self, memory_id: str) -> MemoryAuditLinks:
        del memory_id
        raise report_backed_memory_retired_error()


__all__ = ["ReportBackedMemoryStore", "report_backed_memory_retired_error"]
