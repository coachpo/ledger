from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol, cast

from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_session_factory
from app.repositories.run import RunRepository
from app.services.quote_provider import QuoteProvider

logger = logging.getLogger(__name__)


class RunExecutor(Protocol):
    def execute_claimed_run(self, run_id: int) -> None: ...


class RunQueueService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        quote_provider: QuoteProvider | None = None,
        executor_factory: (
            Callable[[Session, sessionmaker[Session], QuoteProvider | None], RunExecutor] | None
        ) = None,
    ) -> None:
        self.session: Session = session
        self.session_factory: sessionmaker[Session] = session_factory or get_session_factory()
        self.quote_provider: QuoteProvider | None = quote_provider
        self.executor_factory: (
            Callable[[Session, sessionmaker[Session], QuoteProvider | None], RunExecutor] | None
        ) = executor_factory
        self.run_repository: RunRepository = RunRepository(session)

    def claim_next_run(self, run_id: int | None = None) -> int | None:
        try:
            run = self.run_repository.claim_next_queued(run_id=run_id)
            if run is None:
                self.session.rollback()
                return None
            run_id = run.id
            self.session.commit()
            return run_id
        except Exception:
            self.session.rollback()
            raise

    def drain_once(self) -> bool:
        run_id = self.claim_next_run()
        if run_id is None:
            return False

        with self.session_factory() as session:
            self._build_executor(session).execute_claimed_run(run_id)
        return True

    def dispatch_pending(self) -> None:
        thread = threading.Thread(
            target=self._drain_until_empty,
            daemon=True,
            name="ledger-agent-platform-run-queue",
        )
        thread.start()

    def _build_executor(self, session: Session) -> RunExecutor:
        if self.executor_factory is not None:
            return self.executor_factory(session, self.session_factory, self.quote_provider)

        from app.services.run_service import RunService

        return cast(
            RunExecutor,
            RunService(
                session,
                self.session_factory,
                quote_provider=self.quote_provider,
            ),
        )

    def _drain_until_empty(self) -> None:
        while True:
            try:
                with self.session_factory() as session:
                    run_id = RunQueueService(
                        session,
                        self.session_factory,
                        quote_provider=self.quote_provider,
                        executor_factory=self.executor_factory,
                    ).claim_next_run()
                if run_id is None:
                    return

                with self.session_factory() as session:
                    self._build_executor(session).execute_claimed_run(run_id)
            except Exception:
                logger.exception("Agent platform run queue worker failed")
                return


__all__ = ["RunQueueService"]
