from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.formatting import to_utc
from app.extensions.signaldeck_finance.hooks import (
    MEMORY_FOLLOW_UP_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.repositories.report import ReportRepository
from app.schemas.memory import MemoryEntryRead, MemoryLifecycleStatus
from app.schemas.memory_report import AGENT_MEMORY_REVIEW_TYPE
from app.services.market_data_service import MarketDataService
from app.services.memory_service import MemoryService
from app.services.reflection_service import ReflectionService
from app.services.report_backed_memory_store import ReportBackedMemoryStore
from app.services.return_resolution_service import ReturnResolutionService, ReturnResolutionStatus

_MEMORY_REPORT_SOURCE = "agent"


@dataclass(frozen=True, slots=True)
class MemoryFollowUpItem:
    memory_id: str
    status: ReturnResolutionStatus
    reason: str | None
    reflected: bool


@dataclass(frozen=True, slots=True)
class MemoryFollowUpRunResult:
    checked: int
    resolved: int
    expired: int
    pending: int
    reflected: int
    items: tuple[MemoryFollowUpItem, ...]


class MemoryFollowUpService:
    def __init__(
        self,
        session: Session,
        market_data_service: MarketDataService,
    ) -> None:
        self.session: Session = session
        self.repository: ReportRepository = ReportRepository(session)
        self.memory_service: MemoryService = MemoryService(session)
        self.return_resolution_service: ReturnResolutionService = ReturnResolutionService(
            session,
            market_data_service,
        )
        self.reflection_service: ReflectionService = ReflectionService(session)

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(
            self.session,
            surface=MEMORY_FOLLOW_UP_SERVICE_SURFACE,
        )

    def run_due(self, now: datetime) -> MemoryFollowUpRunResult:
        self._require_enabled()
        reflected_at = to_utc(now)
        items: list[MemoryFollowUpItem] = []

        try:
            for memory in self._pending_memories():
                resolution = self.return_resolution_service.resolve_memory(
                    memory.memory_id,
                    end_date=reflected_at,
                    benchmark_symbol=memory.benchmark_symbol,
                    commit=False,
                )
                reflected = False
                if resolution.status != "pending" and not resolution.memory.reflections:
                    _ = self.reflection_service.generate_and_append_reflection(
                        memory.memory_id,
                        reflected_at=reflected_at,
                        commit=False,
                    )
                    reflected = True
                items.append(
                    MemoryFollowUpItem(
                        memory_id=memory.memory_id,
                        status=resolution.status,
                        reason=resolution.reason,
                        reflected=reflected,
                    )
                )
            if any(item.status != "pending" or item.reflected for item in items):
                self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return self._result(items)

    def _pending_memories(self) -> list[MemoryEntryRead]:
        reports = self.repository.list_all(
            review_type=AGENT_MEMORY_REVIEW_TYPE,
            source=_MEMORY_REPORT_SOURCE,
        )
        pending: list[MemoryEntryRead] = []
        for report in sorted(reports, key=lambda item: (item.created_at, item.id)):
            memory_id = ReportBackedMemoryStore.memory_id_from_report_id(report.id)
            try:
                memory = self.memory_service.get_memory(memory_id)
            except ApiError:
                continue
            if memory.status == MemoryLifecycleStatus.PENDING:
                pending.append(memory)
        return pending

    @staticmethod
    def _result(items: list[MemoryFollowUpItem]) -> MemoryFollowUpRunResult:
        return MemoryFollowUpRunResult(
            checked=len(items),
            resolved=sum(item.status == "resolved" for item in items),
            expired=sum(item.status == "expired" for item in items),
            pending=sum(item.status == "pending" for item in items),
            reflected=sum(item.reflected for item in items),
            items=tuple(items),
        )


__all__ = [
    "MemoryFollowUpItem",
    "MemoryFollowUpRunResult",
    "MemoryFollowUpService",
]
