from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import business_rule_error, not_found_error
from app.models.backtest import Backtest
from app.schemas.backtest import TradeDecision
from app.schemas.runtime import (
    PersonaProfileRef,
    RuntimeArtifactRead,
    RuntimeCallerType,
    RuntimeExecutionKind,
    RuntimeRunCreate,
    RuntimeRunRead,
)
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.backtest_completion_service import (
    BacktestCompletionService,
    BacktestCycleCompletionResult,
)
from app.services.backtest_engine import BacktestEngine
from app.services.backtest_runtime_mentions import (
    BacktestRuntimeMentionCompiler,
    BacktestRuntimeMentionResolver,
    append_mentioned_target_outputs,
    build_runtime_full_user_prompt,
    serialize_mentioned_target_outputs,
)
from app.services.execution_adapters import BacktestLangGraphExecutionAdapter, ExecutionAdapter
from app.services.orchestration_service import OrchestrationService
from app.services.report_service import ReportService

CycleDispatcher = Callable[[int, date], None]
ExecutionAdapterFactory = Callable[[Session], ExecutionAdapter]


@dataclass(frozen=True)
class BacktestRuntimeExecutionResult:
    run: RuntimeRunRead
    artifact: RuntimeArtifactRead
    completion: BacktestCycleCompletionResult | None = None


@dataclass(frozen=True)
class FrozenBacktestRuntimeInputs:
    inputs: dict[str, str]
    persona_profile_refs: tuple[PersonaProfileRef, ...] = ()


class BacktestRuntimeAdapter:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        *,
        execution_adapter_factory: ExecutionAdapterFactory | None = None,
        completion_service: BacktestCompletionService | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.runtime_service = AgentRuntimeService(session)
        self.runtime_mention_resolver = BacktestRuntimeMentionResolver(session_factory)
        self.execution_adapter_factory = execution_adapter_factory or (
            lambda current_session: BacktestLangGraphExecutionAdapter(current_session)
        )
        self.completion_service = completion_service or BacktestCompletionService()

    def execute_cycle(
        self,
        *,
        backtest_id: int,
        cycle_date: date,
        cycle_ctx: dict[str, Any],
        engine: BacktestEngine,
        dispatch_next_cycle: CycleDispatcher | None = None,
    ) -> BacktestRuntimeExecutionResult:
        backtest = self._get_backtest_or_raise(backtest_id)
        payload = self._build_runtime_payload(
            backtest=backtest,
            cycle_date=cycle_date,
            cycle_ctx=cycle_ctx,
        )
        prepared = self.runtime_service.prepare_run(payload)
        BacktestCompletionService.set_current_run_id(
            self.session_factory,
            backtest_id,
            prepared.run_id,
        )
        try:
            run = self.runtime_service.execute_prepared_run(
                prepared,
                self.execution_adapter_factory(self.session),
            )
        except Exception:
            self._sync_terminal_backtest_state_from_run(
                backtest_id=backtest_id,
                run_id=prepared.run_id,
            )
            raise
        return self._complete_if_succeeded(
            backtest_id=backtest_id,
            run_id=run.run_id,
            engine=engine,
            dispatch_next_cycle=dispatch_next_cycle,
        )

    def resume_run(
        self,
        run_id: int,
        *,
        engine: BacktestEngine,
        dispatch_next_cycle: CycleDispatcher | None = None,
    ) -> BacktestRuntimeExecutionResult:
        existing_run = self.runtime_service.get_run(run_id)
        backtest_id = self._backtest_id_from_run(existing_run)
        BacktestCompletionService.set_current_run_id(self.session_factory, backtest_id, run_id)
        try:
            run = self.runtime_service.resume_run(
                run_id, self.execution_adapter_factory(self.session)
            )
        except Exception:
            self._sync_terminal_backtest_state_from_run(
                backtest_id=backtest_id,
                run_id=run_id,
            )
            raise
        return self._complete_if_succeeded(
            backtest_id=backtest_id,
            run_id=run.run_id,
            engine=engine,
            dispatch_next_cycle=dispatch_next_cycle,
        )

    def retry_run(
        self,
        run_id: int,
        *,
        engine: BacktestEngine,
        dispatch_next_cycle: CycleDispatcher | None = None,
    ) -> BacktestRuntimeExecutionResult:
        source_run = self.runtime_service.get_run(run_id)
        if source_run.status not in {"FAILED", "WAITING_APPROVAL", "CANCELLED"}:
            raise business_rule_error(
                "runtime_retry_not_allowed",
                f"Run {run_id} cannot be retried from status {source_run.status}",
            )
        prepared = self.runtime_service.prepare_retry_run(run_id)
        backtest_id = self._backtest_id_from_run(source_run)
        BacktestCompletionService.set_current_run_id(
            self.session_factory,
            backtest_id,
            prepared.run_id,
        )
        try:
            run = self.runtime_service.execute_prepared_run(
                prepared,
                self.execution_adapter_factory(self.session),
            )
        except Exception:
            self._sync_terminal_backtest_state_from_run(
                backtest_id=backtest_id,
                run_id=prepared.run_id,
            )
            raise
        return self._complete_if_succeeded(
            backtest_id=backtest_id,
            run_id=run.run_id,
            engine=engine,
            dispatch_next_cycle=dispatch_next_cycle,
        )

    def _complete_if_succeeded(
        self,
        *,
        backtest_id: int,
        run_id: int,
        engine: BacktestEngine,
        dispatch_next_cycle: CycleDispatcher | None,
    ) -> BacktestRuntimeExecutionResult:
        run = self.runtime_service.get_run(run_id)
        artifact = self.runtime_service.get_artifact(run_id)
        completion: BacktestCycleCompletionResult | None = None
        if run.status == "SUCCEEDED":
            if artifact.report_markdown is None:
                raise business_rule_error(
                    "runtime_backtest_completion_artifacts_missing",
                    f"Runtime run {run_id} is missing its frozen analysis report",
                )
            if artifact.normalized_trade_decisions is None:
                raise business_rule_error(
                    "runtime_backtest_completion_artifacts_missing",
                    f"Runtime run {run_id} is missing its frozen trade decisions",
                )
            snapshot = self.runtime_service.load_frozen_snapshot(run_id)

            def load_run_state(current_backtest_id: int) -> dict[str, Any]:
                return BacktestCompletionService.load_run_state(
                    self.session_factory,
                    current_backtest_id,
                )

            def update_run_state(current_backtest_id: int, **kwargs: Any) -> None:
                BacktestCompletionService.update_run_state(
                    self.session_factory,
                    current_backtest_id,
                    **kwargs,
                )

            def clear_cycle_status(current_backtest_id: int) -> None:
                BacktestCompletionService.clear_cycle_status(
                    self.session_factory,
                    current_backtest_id,
                )

            completion = self.completion_service.complete_cycle(
                backtest_id=backtest_id,
                cycle_date=self._cycle_date_from_run(run),
                engine=engine,
                market_data=self._deserialize_market_data(snapshot.inputs),
                load_run_state=load_run_state,
                update_run_state=update_run_state,
                clear_cycle_status=clear_cycle_status,
                dispatch_next_cycle=dispatch_next_cycle or self._noop_dispatch,
                decisions=[
                    TradeDecision.model_validate(item)
                    for item in artifact.normalized_trade_decisions
                ],
                report_markdown=artifact.report_markdown,
                run_id=run_id,
                session_factory=self.session_factory,
            )
            run = self.runtime_service.get_run(run_id)
            artifact = self.runtime_service.get_artifact(run_id)
        elif run.status == "FAILED":
            self._update_backtest_terminal_state(
                backtest_id=backtest_id,
                run_id=run_id,
                status="FAILED",
                current_cycle_status="FAILED",
                error_message=artifact.terminal_error_message,
            )
        elif run.status == "CANCELLED":
            self._update_backtest_terminal_state(
                backtest_id=backtest_id,
                run_id=run_id,
                status="CANCELLED",
                current_cycle_status="CANCELLED",
                error_message=None,
            )
        return BacktestRuntimeExecutionResult(run=run, artifact=artifact, completion=completion)

    def _sync_terminal_backtest_state_from_run(self, *, backtest_id: int, run_id: int) -> None:
        try:
            run = self.runtime_service.get_run(run_id)
        except Exception:
            return
        if run.status not in {"FAILED", "CANCELLED"}:
            return
        try:
            artifact = self.runtime_service.get_artifact(run_id)
        except Exception:
            return
        self._update_backtest_terminal_state(
            backtest_id=backtest_id,
            run_id=run_id,
            status=("FAILED" if run.status == "FAILED" else "CANCELLED"),
            current_cycle_status=("FAILED" if run.status == "FAILED" else "CANCELLED"),
            error_message=(artifact.terminal_error_message if run.status == "FAILED" else None),
        )

    def _update_backtest_terminal_state(
        self,
        *,
        backtest_id: int,
        run_id: int,
        status: str,
        current_cycle_status: str,
        error_message: str | None,
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            if backtest.current_run_id not in {None, run_id}:
                return
            backtest.current_run_id = None
            backtest.last_completed_run_id = run_id
            backtest.status = status
            backtest.current_cycle_status = current_cycle_status
            backtest.error_message = error_message
            session.commit()

    def _build_runtime_payload(
        self,
        *,
        backtest: Backtest,
        cycle_date: date,
        cycle_ctx: dict[str, Any],
    ) -> RuntimeRunCreate:
        if backtest.workflow_spec_key is None or backtest.workflow_spec_version is None:
            raise business_rule_error(
                "runtime_backtest_workflow_not_configured",
                f"Backtest {backtest.id} is missing its pinned workflow target",
            )
        frozen_inputs = self._build_frozen_inputs(
            backtest=backtest,
            cycle_date=cycle_date,
            cycle_ctx=cycle_ctx,
        )
        return RuntimeRunCreate(
            caller_type=RuntimeCallerType.BACKTEST,
            caller_id=backtest.id,
            caller_scope_key=cycle_date.isoformat(),
            execution_kind=RuntimeExecutionKind.WORKFLOW,
            workflow_spec_key=backtest.workflow_spec_key,
            workflow_spec_version=backtest.workflow_spec_version,
            inputs=frozen_inputs.inputs,
            persona_profile_refs=list(frozen_inputs.persona_profile_refs),
            persist_run=True,
        )

    def _build_frozen_inputs(
        self,
        *,
        backtest: Backtest,
        cycle_date: date,
        cycle_ctx: dict[str, Any],
    ) -> FrozenBacktestRuntimeInputs:
        prompt_report_slug = str(cycle_ctx.get("prompt_report_slug", "")).strip()
        if not prompt_report_slug:
            raise business_rule_error(
                "runtime_backtest_prompt_report_missing",
                (
                    f"Backtest {backtest.id} cycle {cycle_date.isoformat()} "
                    "is missing its prompt report"
                ),
            )
        prompt_report = self._load_prompt_report(prompt_report_slug)
        authored_entry_prompt_body = str(cycle_ctx.get("authored_entry_prompt_body", ""))
        compiled_entry_prompt_body = str(cycle_ctx.get("compiled_entry_prompt_body", ""))
        execution_context_body = str(cycle_ctx.get("execution_context_body", ""))
        full_user_prompt = str(cycle_ctx.get("full_user_prompt", ""))

        resolved_targets = self.runtime_mention_resolver.resolve_targets(
            authored_entry_prompt_body=authored_entry_prompt_body,
            orchestration_pattern_key=backtest.orchestration_pattern_key,
        )

        compiled_mentions = BacktestRuntimeMentionCompiler(self.session).compile(
            authored_entry_prompt_body=authored_entry_prompt_body,
            resolved_targets=resolved_targets,
        )
        raw_mentioned_target_outputs = self.runtime_mention_resolver.build_mentioned_target_outputs(
            resolved_targets=resolved_targets,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
        )
        if raw_mentioned_target_outputs:
            execution_context_body = append_mentioned_target_outputs(
                execution_context_body,
                raw_mentioned_target_outputs,
            )
            full_user_prompt = build_runtime_full_user_prompt(
                execution_context_body=execution_context_body,
                compiled_entry_prompt_body=compiled_entry_prompt_body,
            )

        mentioned_target_outputs = serialize_mentioned_target_outputs(raw_mentioned_target_outputs)

        return FrozenBacktestRuntimeInputs(
            inputs={
                "prompt_report_slug": prompt_report_slug,
                "prompt_report": prompt_report,
                "authored_entry_prompt_body": authored_entry_prompt_body,
                "compiled_entry_prompt_body": compiled_entry_prompt_body,
                "execution_context_body": execution_context_body,
                "full_user_prompt": full_user_prompt,
                "raw_mention_handles_json": self._serialize_json(
                    list(compiled_mentions.raw_mention_handles)
                ),
                "resolved_mentions_json": self._serialize_json(
                    list(compiled_mentions.resolved_mentions)
                ),
                "resolved_builtin_versions_json": self._serialize_json(
                    list(compiled_mentions.resolved_builtin_versions)
                ),
                "resolved_role_versions_json": self._serialize_json(
                    list(compiled_mentions.resolved_role_versions)
                ),
                "resolved_character_versions_json": self._serialize_json(
                    list(compiled_mentions.resolved_character_versions)
                ),
                "mentioned_target_outputs_json": self._serialize_json(mentioned_target_outputs),
                "cycle_market_data_json": self._serialize_json(cycle_ctx.get("market_data", {})),
                "available_reports_json": self._serialize_json(
                    self._freeze_available_reports(backtest.id)
                ),
                "orchestration_catalog_json": self._serialize_json(
                    self._freeze_orchestration_catalog()
                ),
            },
            persona_profile_refs=compiled_mentions.persona_profile_refs,
        )

    def _load_prompt_report(self, prompt_report_slug: str) -> str:
        with self.session_factory() as session:
            report_service = ReportService(session)
            report = report_service.get_report_model_by_slug(prompt_report_slug)
            return report.content

    def _freeze_available_reports(self, backtest_id: int) -> dict[str, dict[str, Any]]:
        with self.session_factory() as session:
            report_service = ReportService(session)
            reports = report_service.list_reports(tag=f"backtest_{backtest_id}")
        return {report.slug: report.model_dump(mode="json", by_alias=True) for report in reports}

    def _freeze_orchestration_catalog(self) -> dict[str, Any]:
        with self.session_factory() as session:
            orchestration_service = OrchestrationService(session)
            return orchestration_service.list_mention_catalog().model_dump(
                mode="json",
                by_alias=True,
            )

    def _get_backtest_or_raise(self, backtest_id: int) -> Backtest:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)
        return backtest

    @staticmethod
    def _serialize_json(value: Any) -> str:
        return json.dumps(value, default=BacktestRuntimeAdapter._json_default, sort_keys=True)

    @staticmethod
    def _json_default(value: object) -> str:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    @staticmethod
    def _deserialize_market_data(inputs: Mapping[str, str]) -> dict[str, dict[str, Decimal]]:
        raw_payload = inputs.get("cycle_market_data_json", "{}")
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                "Frozen cycle market data must be valid JSON",
            ) from exc
        market_data: dict[str, dict[str, Decimal]] = {}
        if not isinstance(payload, dict):
            return market_data
        for raw_symbol, raw_row in payload.items():
            if not isinstance(raw_row, dict):
                continue
            symbol = str(raw_symbol)
            market_data[symbol] = {
                str(raw_key): Decimal(str(raw_value)) for raw_key, raw_value in raw_row.items()
            }
        return market_data

    @staticmethod
    def _backtest_id_from_run(run: Any) -> int:
        if run.caller_type != RuntimeCallerType.BACKTEST:
            raise business_rule_error(
                "runtime_backtest_adapter_invalid_caller",
                f"Run {run.run_id} is not owned by a backtest",
            )
        if run.caller_id is None:
            raise business_rule_error(
                "runtime_backtest_caller_context_missing",
                f"Run {run.run_id} is missing its backtest caller id",
            )
        return int(run.caller_id)

    @staticmethod
    def _cycle_date_from_run(run: Any) -> date:
        caller_scope_key = str(run.caller_scope_key or "").strip()
        if not caller_scope_key:
            raise business_rule_error(
                "runtime_backtest_cycle_date_invalid",
                f"Run {run.run_id} is missing its cycle date scope key",
            )
        try:
            return date.fromisoformat(caller_scope_key)
        except ValueError as exc:
            raise business_rule_error(
                "runtime_backtest_cycle_date_invalid",
                f"Run {run.run_id} has an invalid cycle date scope key {caller_scope_key!r}",
            ) from exc

    @staticmethod
    def _noop_dispatch(backtest_id: int, cycle_date: date) -> None:
        _ = (backtest_id, cycle_date)
