from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.engine import get_session_factory
from app.db.session import init_db
from app.services.extension_service import ExtensionService
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_package_schedule_materializer import WorkflowPackageScheduleMaterializer

logger = logging.getLogger(__name__)

_SCHEDULER_ADVISORY_LOCK_KEY = 772114523790049231


def scheduler_lease_owner(*, hostname: str, pid: int, slot: int) -> str:
    return f"scheduler:{hostname}:{pid}:{slot}"


@dataclass(frozen=True)
class ScheduledRun:
    run_id: int
    slot: int
    lease_owner: str


class RunSchedulerWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
        hostname: str | None = None,
        pid: int | None = None,
    ) -> None:
        self.session_factory: sessionmaker[Session] = session_factory or get_session_factory()
        self.settings: Settings = settings or get_settings()
        self.hostname: str = hostname or socket.gethostname()
        self.pid: int = pid or os.getpid()

    @property
    def worker_id(self) -> str:
        return f"scheduler:{self.hostname}:{self.pid}"

    def run_forever(self) -> None:
        with self._scheduler_lock() as acquired:
            if not acquired:
                logger.warning("Another SignalDeck run scheduler worker already holds the lock")
                return

            logger.info(
                "SignalDeck run scheduler worker %s started (max_active_runs=%d, "
                "max_active_per_package=%d)",
                self.worker_id,
                self.settings.run_scheduler_max_active_runs,
                self.settings.run_scheduler_max_active_per_package,
            )
            self._run_loop()

    def run_once(self) -> bool:
        self._recover_stale_leases()
        self._materialize_due_schedules()
        run_id = self._claim_next_run(slot=1)
        if run_id is None:
            return False
        self._execute_claimed_run(
            ScheduledRun(
                run_id=run_id,
                slot=1,
                lease_owner=self._lease_owner_for_slot(1),
            )
        )
        return True

    def _run_loop(self) -> None:
        in_flight: dict[Future[None], ScheduledRun] = {}
        executor = ThreadPoolExecutor(
            max_workers=self.settings.run_scheduler_max_active_runs,
            thread_name_prefix="signaldeck-run-scheduler",
        )
        try:
            while True:
                self._recover_stale_leases()
                self._materialize_due_schedules()
                self._collect_finished_runs(in_flight)
                claimed = self._submit_available_runs(executor, in_flight)
                if not claimed:
                    time.sleep(self.settings.run_scheduler_poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("SignalDeck run scheduler worker %s stopping", self.worker_id)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _materialize_due_schedules(self) -> int:
        result = WorkflowPackageScheduleMaterializer(self.session_factory).materialize_due()
        if result.changed_count:
            logger.info(
                "Materialized %d due schedule(s): queued=%d skipped=%d failed=%d",
                result.processed_count,
                result.queued_count,
                result.skipped_count,
                result.failed_count,
            )
        return result.changed_count

    def _submit_available_runs(
        self,
        executor: ThreadPoolExecutor,
        in_flight: dict[Future[None], ScheduledRun],
    ) -> bool:
        claimed = False
        for slot in self._available_slots(in_flight):
            run_id = self._claim_next_run(slot=slot)
            if run_id is None:
                break
            scheduled_run = ScheduledRun(
                run_id=run_id,
                slot=slot,
                lease_owner=self._lease_owner_for_slot(slot),
            )
            future = executor.submit(self._execute_claimed_run, scheduled_run)
            in_flight[future] = scheduled_run
            claimed = True
        return claimed

    def _available_slots(self, in_flight: dict[Future[None], ScheduledRun]) -> list[int]:
        active_slots = {scheduled_run.slot for scheduled_run in in_flight.values()}
        return [
            slot
            for slot in range(1, self.settings.run_scheduler_max_active_runs + 1)
            if slot not in active_slots
        ]

    @staticmethod
    def _collect_finished_runs(in_flight: dict[Future[None], ScheduledRun]) -> None:
        for future, scheduled_run in list(in_flight.items()):
            if not future.done():
                continue
            del in_flight[future]
            try:
                future.result()
            except Exception:
                logger.exception(
                    "SignalDeck run scheduler worker failed while executing run %d",
                    scheduled_run.run_id,
                )

    def _claim_next_run(self, *, slot: int) -> int | None:
        with self.session_factory() as session:
            return self._queue_service(session, slot=slot).claim_next_run()

    def _recover_stale_leases(self) -> int:
        with self.session_factory() as session:
            recovered_count = self._queue_service(session, slot=0).recover_stale_leases()
        if recovered_count:
            logger.warning("Recovered %d stale SignalDeck scheduler lease(s)", recovered_count)
        return recovered_count

    def _execute_claimed_run(self, scheduled_run: ScheduledRun) -> None:
        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_until_finished,
            args=(scheduled_run, stop_heartbeat),
            daemon=True,
            name=f"signaldeck-run-heartbeat-{scheduled_run.run_id}",
        )
        heartbeat.start()
        try:
            with self.session_factory() as session:
                provider_bundle = ExtensionService(session).get_execution_provider_bundle()
                RunService(
                    session,
                    self.session_factory,
                    provider_bundle=provider_bundle,
                ).execute_claimed_run(scheduled_run.run_id)
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=self.settings.run_scheduler_heartbeat_seconds)
            with self.session_factory() as session:
                _ = self._queue_service(session, slot=scheduled_run.slot).release_run_lease(
                    scheduled_run.run_id
                )

    def _heartbeat_until_finished(
        self,
        scheduled_run: ScheduledRun,
        stop_heartbeat: threading.Event,
    ) -> None:
        while not stop_heartbeat.wait(self.settings.run_scheduler_heartbeat_seconds):
            with self.session_factory() as session:
                heartbeat_kept = self._queue_service(
                    session,
                    slot=scheduled_run.slot,
                ).heartbeat_run(scheduled_run.run_id)
            if not heartbeat_kept:
                return

    def _lease_owner_for_slot(self, slot: int) -> str:
        return scheduler_lease_owner(hostname=self.hostname, pid=self.pid, slot=slot)

    def _queue_service(self, session: Session, *, slot: int) -> RunQueueService:
        return RunQueueService(
            session,
            self.session_factory,
            lease_owner=self._lease_owner_for_slot(slot),
            lease_ttl_seconds=self.settings.run_scheduler_lease_ttl_seconds,
        )

    @contextmanager
    def _scheduler_lock(self) -> Iterator[bool]:
        with self.session_factory() as session:
            acquired = bool(
                session.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": _SCHEDULER_ADVISORY_LOCK_KEY},
                ).scalar_one()
            )
            if not acquired:
                yield False
                return
            try:
                yield True
            finally:
                session.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _SCHEDULER_ADVISORY_LOCK_KEY},
                )
                session.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    RunSchedulerWorker().run_forever()


if __name__ == "__main__":
    main()


__all__ = ["RunSchedulerWorker", "main", "scheduler_lease_owner"]
