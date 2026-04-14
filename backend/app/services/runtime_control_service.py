from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.models.runtime_control_flag import RuntimeControlFlag
from app.models.runtime_flag_change_event import RuntimeFlagChangeEvent
from app.repositories.backtest import BacktestRepository
from app.repositories.runtime_control_flag import RuntimeControlFlagRepository
from app.repositories.runtime_flag_change_event import RuntimeFlagChangeEventRepository
from app.schemas.runtime import (
    RuntimeControlFlagListRead,
    RuntimeControlFlagRead,
    RuntimeFlagChangeEventListRead,
    RuntimeFlagChangeEventRead,
)

BACKTEST_RUNTIME_V2_FLAG_KEY = "AGENT_RUNTIME_V2_BACKTESTS_ENABLED"
_MANAGED_RUNTIME_FLAGS = {BACKTEST_RUNTIME_V2_FLAG_KEY: False}
_RUNTIME_V2_EXECUTION_OWNER = "runtime_v2"


class RuntimeControlService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.control_flag_repository = RuntimeControlFlagRepository(session)
        self.flag_event_repository = RuntimeFlagChangeEventRepository(session)
        self.backtest_repository = BacktestRepository(session)

    def ensure_managed_flags(self) -> RuntimeControlFlagListRead:
        for flag_key, default_enabled in _MANAGED_RUNTIME_FLAGS.items():
            if self.control_flag_repository.get_by_key(flag_key) is None:
                self.control_flag_repository.add(
                    RuntimeControlFlag(flag_key=flag_key, enabled=default_enabled)
                )
        self.session.flush()
        return self.list_flags()

    def list_flags(self) -> RuntimeControlFlagListRead:
        return RuntimeControlFlagListRead(
            items=[
                RuntimeControlFlagRead.model_validate(flag)
                for flag in self.control_flag_repository.list_all()
            ]
        )

    def get_flag(self, flag_key: str) -> RuntimeControlFlagRead:
        normalized_flag_key = self._normalize_flag_key(flag_key)
        flag = self.control_flag_repository.get_by_key(normalized_flag_key)
        if flag is None:
            raise not_found_error("Runtime control flag")
        return RuntimeControlFlagRead.model_validate(flag)

    def list_flag_events(self, flag_key: str) -> RuntimeFlagChangeEventListRead:
        normalized_flag_key = self._normalize_flag_key(flag_key)
        return RuntimeFlagChangeEventListRead(
            items=[
                RuntimeFlagChangeEventRead.model_validate(event)
                for event in self.flag_event_repository.list_for_flag(normalized_flag_key)
            ]
        )

    def set_backtest_runtime_v2_enabled(
        self,
        *,
        enabled: bool,
        actor: str,
        reason: str,
    ) -> RuntimeControlFlagRead:
        return self.set_flag(
            flag_key=BACKTEST_RUNTIME_V2_FLAG_KEY,
            enabled=enabled,
            actor=actor,
            reason=reason,
        )

    def set_flag(
        self,
        *,
        flag_key: str,
        enabled: bool,
        actor: str,
        reason: str,
    ) -> RuntimeControlFlagRead:
        normalized_flag_key = self._normalize_flag_key(flag_key)
        normalized_actor = self._normalize_required_text(actor, field_name="Actor")
        normalized_reason = self._normalize_required_text(reason, field_name="Reason")
        flag = self._get_or_create_flag(normalized_flag_key)
        old_enabled = flag.enabled

        rejection_message = self._build_rejection_message(
            flag_key=normalized_flag_key,
            new_enabled=enabled,
        )
        if rejection_message is not None:
            self.flag_event_repository.add(
                RuntimeFlagChangeEvent(
                    flag_key=normalized_flag_key,
                    old_enabled=old_enabled,
                    new_enabled=enabled,
                    actor=normalized_actor,
                    reason=(
                        f"{normalized_reason}\n\nRejected: {rejection_message}"
                        if normalized_reason
                        else rejection_message
                    ),
                    result="rejected",
                )
            )
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
            raise business_rule_error("runtime_flag_change_rejected", rejection_message)

        flag.enabled = enabled
        self.flag_event_repository.add(
            RuntimeFlagChangeEvent(
                flag_key=normalized_flag_key,
                old_enabled=old_enabled,
                new_enabled=enabled,
                actor=normalized_actor,
                reason=normalized_reason,
                result="applied",
            )
        )

        try:
            self.session.commit()
            self.session.refresh(flag)
        except Exception:
            self.session.rollback()
            raise

        return RuntimeControlFlagRead.model_validate(flag)

    def _get_or_create_flag(self, flag_key: str) -> RuntimeControlFlag:
        flag = self.control_flag_repository.get_by_key(flag_key)
        if flag is not None:
            return flag

        created = RuntimeControlFlag(flag_key=flag_key, enabled=_MANAGED_RUNTIME_FLAGS[flag_key])
        self.control_flag_repository.add(created)
        self.session.flush()
        return created

    def _build_rejection_message(self, *, flag_key: str, new_enabled: bool) -> str | None:
        if flag_key != BACKTEST_RUNTIME_V2_FLAG_KEY or new_enabled:
            return None

        blocking_backtests = self.backtest_repository.list_non_terminal(
            execution_owner=_RUNTIME_V2_EXECUTION_OWNER
        )
        if not blocking_backtests:
            return None

        details = ", ".join(
            f"{backtest.id}:{backtest.status}" for backtest in blocking_backtests[:10]
        )
        return (
            "Cannot disable AGENT_RUNTIME_V2_BACKTESTS_ENABLED while non-terminal "
            f"runtime_v2 backtests exist ({details})."
        )

    @staticmethod
    def _normalize_flag_key(flag_key: str) -> str:
        normalized = RuntimeControlService._normalize_required_text(flag_key, field_name="Flag key")
        if normalized not in _MANAGED_RUNTIME_FLAGS:
            raise business_rule_error(
                "runtime_unknown_flag",
                f"Unknown runtime control flag: {normalized}",
            )
        return normalized

    @staticmethod
    def _normalize_required_text(value: str, *, field_name: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise business_rule_error(
                "runtime_invalid_flag_change_request",
                f"{field_name} is required",
            )
        return normalized


__all__ = ["BACKTEST_RUNTIME_V2_FLAG_KEY", "RuntimeControlService"]
