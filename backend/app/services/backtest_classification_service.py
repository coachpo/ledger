from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import utcnow
from app.langgraph.seeds import (
    DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY,
    get_backtest_pattern_spec,
)
from app.models.backtest import Backtest
from app.repositories.backtest import BacktestRepository
from app.repositories.runtime_control_flag import RuntimeControlFlagRepository
from app.schemas.backtest import BacktestExecutionOwner, BacktestLaunchMode, BacktestStatus
from app.services.runtime_control_service import BACKTEST_RUNTIME_V2_FLAG_KEY
from app.services.runtime_seed_bootstrap import resolve_rollback_window_workflow_pin

_TERMINAL_BACKTEST_STATUSES = {
    BacktestStatus.COMPLETED.value,
    BacktestStatus.FAILED.value,
    BacktestStatus.CANCELLED.value,
}


@dataclass(frozen=True)
class BacktestRoutingDecision:
    orchestration_pattern_key: str
    launch_mode: BacktestLaunchMode
    workflow_spec_key: str | None
    workflow_spec_version: int | None
    execution_owner: BacktestExecutionOwner


@dataclass(frozen=True)
class BacktestManifestClassification:
    backtest_id: int
    launch_mode: BacktestLaunchMode
    execution_owner: BacktestExecutionOwner
    classified_by: str
    classification_note: str | None = None


class BacktestClassificationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.backtest_repository = BacktestRepository(session)
        self.control_flag_repository = RuntimeControlFlagRepository(session)

    def resolve_create_time_routing(
        self,
        *,
        launch_mode: BacktestLaunchMode,
        requested_pattern_key: str | None,
    ) -> BacktestRoutingDecision:
        orchestration_pattern_key = self._normalize_orchestration_pattern_key(requested_pattern_key)
        return self._resolve_routing(
            orchestration_pattern_key=orchestration_pattern_key,
            launch_mode=launch_mode,
            requested_execution_owner=None,
            runtime_flag_enabled=self._runtime_v2_enabled(),
        )

    def classify_backtests_from_manifest(
        self,
        entries: Iterable[BacktestManifestClassification],
    ) -> list[Backtest]:
        classified_backtests: list[Backtest] = []

        try:
            for entry in entries:
                classified_backtests.append(self._classify_backtest(entry))
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        for backtest in classified_backtests:
            self.session.refresh(backtest)
        return classified_backtests

    def _classify_backtest(self, entry: BacktestManifestClassification) -> Backtest:
        backtest = self.backtest_repository.get(entry.backtest_id)
        if backtest is None:
            raise not_found_error("Backtest")

        decision = self._resolve_routing(
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            launch_mode=entry.launch_mode,
            requested_execution_owner=entry.execution_owner,
            runtime_flag_enabled=None,
        )
        if self._matches_persisted_routing(backtest, decision):
            return backtest
        if self._has_existing_routing_persistence(backtest):
            raise business_rule_error(
                "backtest_classification_conflict",
                f"Backtest {backtest.id} is already pinned and cannot be reclassified",
            )
        if self._would_rehome_active_backtest(backtest, decision):
            raise business_rule_error(
                "backtest_classification_rehome_rejected",
                f"Backtest {backtest.id} cannot be re-homed to runtime_v2 while status is "
                f"{backtest.status}",
            )

        backtest.launch_mode = decision.launch_mode.value
        backtest.workflow_spec_key = decision.workflow_spec_key
        backtest.workflow_spec_version = decision.workflow_spec_version
        backtest.execution_owner = decision.execution_owner.value
        backtest.launch_mode_classified_at = utcnow()
        backtest.launch_mode_classified_by = self._normalize_required_text(
            entry.classified_by,
            field_name="Classification actor",
        )
        backtest.launch_mode_classification_note = self._normalize_optional_text(
            entry.classification_note
        )
        self.session.flush()
        return backtest

    def _resolve_routing(
        self,
        *,
        orchestration_pattern_key: str,
        launch_mode: BacktestLaunchMode,
        requested_execution_owner: BacktestExecutionOwner | None,
        runtime_flag_enabled: bool | None,
    ) -> BacktestRoutingDecision:
        if launch_mode == BacktestLaunchMode.LEGACY_CALLBACK:
            if requested_execution_owner not in {
                None,
                BacktestExecutionOwner.LEGACY_PATH,
            }:
                raise business_rule_error(
                    "invalid_backtest_execution_owner",
                    "Legacy callback backtests must remain on legacy_path",
                )
            return BacktestRoutingDecision(
                orchestration_pattern_key=orchestration_pattern_key,
                launch_mode=launch_mode,
                workflow_spec_key=None,
                workflow_spec_version=None,
                execution_owner=BacktestExecutionOwner.LEGACY_PATH,
            )

        workflow_spec_key, workflow_spec_version = self._resolve_internal_workflow_pin(
            orchestration_pattern_key
        )
        if requested_execution_owner is None:
            execution_owner = (
                BacktestExecutionOwner.RUNTIME_V2
                if runtime_flag_enabled and workflow_spec_key is not None
                else BacktestExecutionOwner.LEGACY_PATH
            )
        else:
            if (
                requested_execution_owner == BacktestExecutionOwner.RUNTIME_V2
                and workflow_spec_key is None
            ):
                raise business_rule_error(
                    "invalid_backtest_execution_owner",
                    "runtime_v2 backtests require a rollback-compatible seeded workflow pin",
                )
            execution_owner = requested_execution_owner

        return BacktestRoutingDecision(
            orchestration_pattern_key=orchestration_pattern_key,
            launch_mode=launch_mode,
            workflow_spec_key=workflow_spec_key,
            workflow_spec_version=workflow_spec_version,
            execution_owner=execution_owner,
        )

    def _normalize_orchestration_pattern_key(self, pattern_key: str | None) -> str:
        if pattern_key is None:
            return DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY

        normalized = pattern_key.strip()
        if not normalized:
            return DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY

        pattern_spec = get_backtest_pattern_spec(normalized)
        if pattern_spec is None:
            raise business_rule_error(
                "invalid_orchestration_pattern",
                f"Unknown orchestration pattern: {normalized}",
            )

        return pattern_spec.key

    def _resolve_internal_workflow_pin(
        self, orchestration_pattern_key: str
    ) -> tuple[str | None, int | None]:
        try:
            workflow_spec_key, workflow_spec_version = resolve_rollback_window_workflow_pin(
                self.session,
                orchestration_pattern_key,
            )
        except ValueError:
            return None, None
        return workflow_spec_key, workflow_spec_version

    def _runtime_v2_enabled(self) -> bool:
        flag = self.control_flag_repository.get_by_key(BACKTEST_RUNTIME_V2_FLAG_KEY)
        return bool(flag.enabled) if flag is not None else False

    @staticmethod
    def _has_existing_routing_persistence(backtest: Backtest) -> bool:
        return any(
            value is not None
            for value in (
                backtest.launch_mode,
                backtest.workflow_spec_key,
                backtest.workflow_spec_version,
                backtest.execution_owner,
                backtest.launch_mode_classified_at,
                backtest.launch_mode_classified_by,
                backtest.launch_mode_classification_note,
            )
        )

    @staticmethod
    def _matches_persisted_routing(
        backtest: Backtest,
        decision: BacktestRoutingDecision,
    ) -> bool:
        return (
            backtest.launch_mode == decision.launch_mode.value
            and backtest.workflow_spec_key == decision.workflow_spec_key
            and backtest.workflow_spec_version == decision.workflow_spec_version
            and backtest.execution_owner == decision.execution_owner.value
        )

    @staticmethod
    def _would_rehome_active_backtest(
        backtest: Backtest,
        decision: BacktestRoutingDecision,
    ) -> bool:
        return (
            decision.execution_owner == BacktestExecutionOwner.RUNTIME_V2
            and backtest.status not in _TERMINAL_BACKTEST_STATUSES
        )

    @staticmethod
    def _normalize_required_text(value: str, *, field_name: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise business_rule_error(
                "invalid_backtest_classification_manifest",
                f"{field_name} is required",
            )
        return normalized

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


__all__ = [
    "BacktestClassificationService",
    "BacktestManifestClassification",
    "BacktestRoutingDecision",
]
