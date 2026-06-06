from __future__ import annotations

import os
import socket
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.formatting import utcnow
from app.db.engine import get_session_factory
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.repositories.run import RunRepository
from app.services.execution_providers import ExecutionProviderBundle

_STALE_LEASE_FAILURE_MESSAGE = (
    "Run marked as failed because its scheduler lease expired before the worker completed it."
)
_PENDING_LEASE_SKIP_MESSAGE = (
    "Runtime row skipped because the parent run's scheduler lease expired before execution "
    "reached it."
)


class RunExecutor(Protocol):
    def execute_claimed_run(self, run_id: int) -> None: ...


class RunQueueService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        provider_bundle: ExecutionProviderBundle | None = None,
        executor_factory: (
            Callable[[Session, sessionmaker[Session], ExecutionProviderBundle], RunExecutor] | None
        ) = None,
        lease_owner: str | None = None,
        lease_ttl_seconds: float | None = None,
    ) -> None:
        self.session: Session = session
        self.session_factory: sessionmaker[Session] = session_factory or get_session_factory()
        settings = get_settings()
        self.provider_bundle: ExecutionProviderBundle = provider_bundle or ExecutionProviderBundle()
        self.executor_factory: (
            Callable[[Session, sessionmaker[Session], ExecutionProviderBundle], RunExecutor] | None
        ) = executor_factory
        self.lease_owner = lease_owner or f"scheduler:{socket.gethostname()}:{os.getpid()}:0"
        self.lease_ttl_seconds = (
            lease_ttl_seconds
            if lease_ttl_seconds is not None
            else settings.run_scheduler_lease_ttl_seconds
        )
        self.run_repository: RunRepository = RunRepository(session)

    def claim_next_run(self, run_id: int | None = None) -> int | None:
        try:
            run = self.run_repository.claim_next_queued(run_id=run_id)
            if run is None:
                self.session.rollback()
                return None
            claimed_at = utcnow()
            self._refresh_run_lease(run, now=claimed_at)
            claimed_run_id = run.id
            self.session.commit()
            return claimed_run_id
        except Exception:
            self.session.rollback()
            raise

    def heartbeat_run(self, run_id: int, *, now: datetime | None = None) -> bool:
        heartbeat_at = now or utcnow()
        try:
            run = self.session.scalar(
                select(Run)
                .where(
                    Run.id == run_id,
                    Run.status == "running",
                    Run.lease_owner == self.lease_owner,
                )
                .with_for_update()
            )
            if run is None:
                self.session.rollback()
                return False
            self._refresh_run_lease(run, now=heartbeat_at)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise

    def release_run_lease(self, run_id: int) -> bool:
        try:
            run = self.session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run is None:
                self.session.rollback()
                return False
            if run.lease_owner not in {None, self.lease_owner}:
                self.session.rollback()
                return False
            run.lease_owner = None
            run.lease_expires_at = None
            run.heartbeat_at = None
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise

    def recover_stale_leases(self, *, now: datetime | None = None) -> int:
        recovered_at = now or utcnow()
        try:
            stale_runs = list(
                self.session.scalars(
                    select(Run)
                    .where(
                        Run.status == "running",
                        Run.lease_owner.is_not(None),
                        Run.lease_expires_at.is_not(None),
                        Run.lease_expires_at < recovered_at,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            if not stale_runs:
                self.session.rollback()
                return 0
            run_ids = [run.id for run in stale_runs]
            for run in stale_runs:
                run.status = "failed"
                run.error = run.error or _STALE_LEASE_FAILURE_MESSAGE
                run.finished_at = run.finished_at or recovered_at
                run.lease_owner = None
                run.lease_expires_at = None
                run.heartbeat_at = None
            self._mark_running_children_terminal(run_ids, now=recovered_at)
            self.session.commit()
            return len(stale_runs)
        except Exception:
            self.session.rollback()
            raise

    def drain_once(self, run_id: int | None = None) -> bool:
        run_id = self.claim_next_run(run_id=run_id)
        if run_id is None:
            return False

        try:
            with self.session_factory() as session:
                self._build_executor(session).execute_claimed_run(run_id)
        finally:
            with self.session_factory() as session:
                _ = RunQueueService(
                    session,
                    self.session_factory,
                    provider_bundle=self.provider_bundle,
                    executor_factory=self.executor_factory,
                    lease_owner=self.lease_owner,
                    lease_ttl_seconds=self.lease_ttl_seconds,
                ).release_run_lease(run_id)
        return True

    def _refresh_run_lease(self, run: Run, *, now: datetime) -> None:
        run.lease_owner = self.lease_owner
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=self.lease_ttl_seconds)

    def _mark_running_children_terminal(self, run_ids: list[int], *, now: datetime) -> None:
        _ = self.session.execute(
            update(RunStep)
            .where(RunStep.run_id.in_(run_ids), RunStep.status == "running")
            .values(status="failed", error=_STALE_LEASE_FAILURE_MESSAGE, finished_at=now)
        )
        _ = self.session.execute(
            update(RunStep)
            .where(RunStep.run_id.in_(run_ids), RunStep.status == "pending")
            .values(status="skipped", error=_PENDING_LEASE_SKIP_MESSAGE, finished_at=now)
        )
        for invocation_model in (RunAgentInvocation, RunOperationInvocation):
            _ = self.session.execute(
                update(invocation_model)
                .where(invocation_model.run_id.in_(run_ids), invocation_model.status == "running")
                .values(
                    status="failed",
                    error_code="scheduler_lease_expired",
                    error_message=_STALE_LEASE_FAILURE_MESSAGE,
                    finished_at=now,
                )
            )
            _ = self.session.execute(
                update(invocation_model)
                .where(invocation_model.run_id.in_(run_ids), invocation_model.status == "pending")
                .values(
                    status="skipped",
                    error_code="scheduler_lease_expired",
                    error_message=_PENDING_LEASE_SKIP_MESSAGE,
                    finished_at=now,
                )
            )

    def _build_executor(self, session: Session) -> RunExecutor:
        if self.executor_factory is not None:
            return self.executor_factory(session, self.session_factory, self.provider_bundle)

        import importlib

        run_service_module = importlib.import_module("app.services.run_service")
        return cast(
            RunExecutor,
            run_service_module.RunService(
                session,
                self.session_factory,
                provider_bundle=self.provider_bundle,
            ),
        )


__all__ = ["RunQueueService"]
