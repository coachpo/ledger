from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import normalize_symbol
from app.langgraph.runner import (
    BacktestExecutionMode,
    BacktestLangGraphCapabilityInputs,
    BacktestLangGraphRequest,
    BacktestLangGraphRunner,
    BacktestLangGraphToolAdapter,
    BacktestLangGraphToolExecutionError,
    BacktestLangGraphToolRuntime,
    LiveBacktestSymbolAnalyzer,
)
from app.langgraph.seeds import (
    BacktestPatternSpec,
    PatternMentionPolicy,
    SeededCapabilityBundleSpec,
    SeededConnectorSpec,
    SeededToolSpec,
    build_backtest_langgraph_runner,
    get_backtest_pattern_spec,
    get_seeded_capability_bundle_spec,
    get_seeded_connector_spec,
    get_seeded_tool_spec,
)
from app.models.backtest import Backtest
from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot
from app.schemas.backtest import (
    BacktestExecutionOwner,
    BacktestLaunchMode,
    BacktestStatus,
    TradeDecision,
)
from app.schemas.backtest_callback import (
    CycleCompleteResponse,
    CycleReportUpload,
    CycleTradeResult,
    CycleTradesRequest,
    CycleTradesResponse,
)
from app.schemas.report import ReportMetadata
from app.services.backtest_completion_service import BacktestCompletionService
from app.services.backtest_engine import BacktestEngine
from app.services.backtest_runtime_mentions import (
    BacktestRuntimeMentionResolver,
    append_mentioned_target_outputs,
    build_runtime_full_user_prompt,
    resolve_runtime_pattern_mention_policy,
    serialize_builtin_versions,
    serialize_character_versions,
    serialize_mentioned_target_outputs,
    serialize_resolved_mentions,
    serialize_role_versions,
)
from app.services.orchestration_service import OrchestrationService
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)

_TERMINAL_BACKTEST_STATUSES = {
    BacktestStatus.COMPLETED,
    BacktestStatus.FAILED,
    BacktestStatus.CANCELLED,
}
_PHASE_1_ALLOWED_TOOL_IDS = frozenset(
    {
        "ledger.report_lookup",
        "ledger.orchestration_catalog_lookup",
        "ledger.cycle_context_lookup",
    }
)
_PHASE_1_CYCLE_CONTEXT_ARTIFACT_KEYS = (
    "prompt_report_slug",
    "prompt_report",
    "authored_entry_prompt_body",
    "compiled_entry_prompt_body",
    "execution_context_body",
    "full_user_prompt",
    "resolved_mentions",
    "mentioned_target_outputs",
    "mentioned_target_output_ids",
)
_REPORT_LOOKUP_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"slug": {"type": "string"}},
    "required": ["slug"],
    "additionalProperties": False,
}
_ORCHESTRATION_CATALOG_LOOKUP_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"handle": {"type": "string"}},
    "additionalProperties": False,
}
_CYCLE_CONTEXT_LOOKUP_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "artifact_key": {
            "type": "string",
            "enum": list(_PHASE_1_CYCLE_CONTEXT_ARTIFACT_KEYS),
        }
    },
    "required": ["artifact_key"],
    "additionalProperties": False,
}
_MARKET_DATA_CONNECTOR_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"symbol": {"type": "string"}},
    "required": ["symbol"],
    "additionalProperties": False,
}
_COMPANY_FILINGS_CONNECTOR_PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"symbol": {"type": "string"}},
    "required": ["symbol"],
    "additionalProperties": False,
}


class BacktestCycleService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory
        self.completion_service = BacktestCompletionService()

    def build_engine(self, backtest_id: int) -> BacktestEngine:
        return self._build_engine(backtest_id)

    def dispatch_cycle(self, backtest_id: int, cycle_date: date) -> None:
        self._dispatch_cycle(backtest_id, cycle_date)

    def start_backtest(self, backtest_id: int) -> None:
        engine = self._build_engine(backtest_id)

        try:
            schedule, benchmark_history = engine.initialize()
            if not schedule:
                return

            self._store_run_state(backtest_id, schedule, benchmark_history)
            self._dispatch_cycle(backtest_id, schedule[0])
        except Exception as exc:
            logger.exception("Failed to start backtest %d", backtest_id)
            engine._mark_failed(str(exc))

    def handle_report_callback(
        self, backtest_id: int, cycle_date: date, payload: CycleReportUpload
    ) -> str:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._ensure_callback_compatible(backtest)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        with self.session_factory() as session:
            report_service = ReportService(session)
            report = report_service.create_external_report(
                name=payload.name,
                slug=payload.name,
                content=payload.content,
                metadata=ReportMetadata.model_validate(
                    {
                        "tags": payload.tags + [f"backtest_{backtest_id}"],
                        "analysis": {
                            "backtestId": backtest_id,
                            "cycleDate": cycle_date.isoformat(),
                            "reviewType": "backtest_analysis",
                        },
                    }
                ),
            )
        return report.slug

    def handle_trades_callback(
        self, backtest_id: int, cycle_date: date, payload: CycleTradesRequest
    ) -> CycleTradesResponse:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._ensure_callback_compatible(backtest)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        engine = self._build_engine(backtest_id)
        market_data = engine._load_cycle_market_data(engine._portfolio_symbols(), cycle_date)
        trade_results = engine.apply_cycle_trades(
            cycle_date=cycle_date,
            decisions=payload.decisions,
            market_data=market_data,
            report_slug=payload.report_slug,
        )

        run_state = self._load_run_state(backtest_id)
        trade_log = list(run_state["trade_log"])
        trade_log.extend(trade_results)
        self._update_run_state(
            backtest_id,
            equity_points=run_state["equity_points"],
            trade_log=trade_log,
        )

        executed = [
            CycleTradeResult(
                symbol=str(trade["symbol"]),
                action=str(trade["side"]),
                executed=trade.get("executed"),
                executed_price=trade.get("executedPrice"),
                failure_reason=trade.get("failureReason"),
            )
            for trade in trade_results
        ]
        return CycleTradesResponse(executed=executed)

    def handle_cycle_complete(self, backtest_id: int, cycle_date: date) -> CycleCompleteResponse:
        backtest = self._get_backtest_or_raise(backtest_id)
        self._ensure_callback_compatible(backtest)
        self._validate_cycle_status(
            backtest,
            cycle_date,
            allow=[
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            ],
        )
        self._set_cycle_status(
            backtest_id,
            BacktestStatus.PROCESSING_CALLBACK,
            cycle_date=cycle_date,
        )

        engine = self._build_engine(backtest_id)
        market_data = engine._load_cycle_market_data(engine._portfolio_symbols(), cycle_date)
        completion = self.completion_service.complete_cycle(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            engine=engine,
            market_data=market_data,
            load_run_state=self._load_run_state,
            update_run_state=self._update_run_state,
            clear_cycle_status=self._clear_cycle_status,
            dispatch_next_cycle=self._dispatch_cycle,
        )

        refreshed = self._get_backtest_or_raise(backtest_id)
        return CycleCompleteResponse(
            backtest_id=backtest_id,
            status=refreshed.status,
            completed_cycles=refreshed.completed_cycles,
            total_cycles=refreshed.total_cycles,
            next_cycle_date=(
                completion.next_cycle_date.isoformat()
                if completion.next_cycle_date is not None
                else None
            ),
            finished=completion.finished,
        )

    def _dispatch_cycle(self, backtest_id: int, cycle_date: date) -> None:
        engine = self._build_engine(backtest_id)
        backtest = self._get_backtest_or_raise(backtest_id)

        try:
            cycle_ctx = engine.execute_cycle(cycle_date)
        except Exception as exc:
            logger.exception("Failed to prepare cycle %s for backtest %d", cycle_date, backtest_id)
            engine._mark_failed(str(exc))
            self._clear_cycle_status(backtest_id)
            return

        if cycle_ctx.get("cancelled"):
            self._clear_cycle_status(backtest_id)
            return

        if getattr(backtest, "execution_owner", None) == BacktestExecutionOwner.RUNTIME_V2.value:
            try:
                self._run_runtime_cycle(backtest_id, cycle_date, engine, cycle_ctx)
            except Exception as exc:
                logger.exception(
                    "Failed to execute runtime-backed cycle %s for backtest %d",
                    cycle_date,
                    backtest_id,
                )
                self._mark_runtime_dispatch_failure(backtest_id, str(exc))
            return

        settings = get_settings()
        if settings.backtest_test_mode:
            self._deterministic_cycle(backtest_id, cycle_date, engine, cycle_ctx)
            return

        try:
            self._run_internal_cycle(backtest_id, cycle_date, engine, cycle_ctx)
        except Exception as exc:
            logger.exception(
                "Failed to execute internal LangGraph cycle %s for backtest %d",
                cycle_date,
                backtest_id,
            )
            engine._mark_failed(str(exc))
            self._clear_cycle_status(backtest_id)

    def _ensure_callback_compatible(self, backtest: Backtest) -> None:
        if backtest.execution_owner == BacktestExecutionOwner.RUNTIME_V2.value:
            raise business_rule_error(
                "invalid_backtest_state",
                "Runtime-backed backtests do not accept legacy callback ingress",
            )
        if backtest.launch_mode not in {None, BacktestLaunchMode.LEGACY_CALLBACK.value}:
            raise business_rule_error(
                "invalid_backtest_state",
                "Only legacy callback backtests accept callback ingress",
            )

    def _handle_timeout(self, backtest_id: int, cycle_date: date) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            if backtest.current_cycle_status not in {
                BacktestStatus.AWAITING_CALLBACK,
                BacktestStatus.PROCESSING_CALLBACK,
            }:
                return
            if backtest.current_cycle_date != cycle_date:
                return
            backtest.status = BacktestStatus.FAILED
            backtest.error_message = f"Webhook callback timed out after {backtest.webhook_timeout}s"
            backtest.current_cycle_status = None
            session.commit()

    def _deterministic_cycle(
        self,
        backtest_id: int,
        cycle_date: date,
        engine: BacktestEngine,
        cycle_ctx: dict[str, Any],
    ) -> None:
        authored_entry_prompt_body = str(cycle_ctx.get("authored_entry_prompt_body", ""))
        if authored_entry_prompt_body:
            backtest = self._get_backtest_or_raise(backtest_id)
            compiled_entry_prompt_body = str(cycle_ctx.get("compiled_entry_prompt_body", ""))
            execution_context_body = str(cycle_ctx.get("execution_context_body", ""))
            full_user_prompt = str(cycle_ctx.get("full_user_prompt", ""))
            pattern_policy = self._resolve_pattern_mention_policy(
                backtest.orchestration_pattern_key
            )
            resolved_targets = self._resolve_mentions(
                authored_entry_prompt_body=authored_entry_prompt_body,
                orchestration_pattern_key=backtest.orchestration_pattern_key,
                pattern_policy=pattern_policy,
            )
            mentioned_target_outputs = self._dispatch_mentioned_target_outputs(
                resolved_targets=resolved_targets,
                compiled_entry_prompt_body=compiled_entry_prompt_body,
                execution_context_body=execution_context_body,
            )
            if resolved_targets:
                execution_context_body = self._append_mentioned_target_outputs(
                    execution_context_body,
                    mentioned_target_outputs,
                )
                full_user_prompt = self._build_full_user_prompt(
                    execution_context_body=execution_context_body,
                    compiled_entry_prompt_body=compiled_entry_prompt_body,
                )

            (
                execution_mode,
                resolved_bundle_versions,
                resolved_tool_versions,
                resolved_connector_versions,
                resolved_capability_inputs,
            ) = self._resolve_phase1_capability_inputs(
                orchestration_pattern_key=backtest.orchestration_pattern_key,
                resolved_targets=resolved_targets,
            )

            self._store_orchestration_snapshot(
                backtest_id=backtest_id,
                cycle_date=cycle_date,
                prompt_report_slug=str(cycle_ctx.get("prompt_report_slug", "")),
                orchestration_pattern_key=backtest.orchestration_pattern_key,
                pattern_policy_version=pattern_policy.version,
                entry_prompt_hash=self._hash_prompt_text(authored_entry_prompt_body),
                full_user_prompt_hash=self._hash_prompt_text(full_user_prompt),
                execution_mode=execution_mode,
                resolved_mentions=self._serialize_resolved_mentions(resolved_targets),
                mentioned_target_outputs=self._serialize_mentioned_target_outputs(
                    mentioned_target_outputs
                ),
                resolved_builtin_versions=self._serialize_builtin_versions(resolved_targets),
                resolved_role_versions=self._serialize_role_versions(resolved_targets),
                resolved_character_versions=self._serialize_character_versions(resolved_targets),
                resolved_bundle_versions=resolved_bundle_versions,
                resolved_tool_versions=resolved_tool_versions,
                resolved_connector_versions=resolved_connector_versions,
                tool_call_trace=[],
                approval_trace=self._initial_approval_trace(
                    connector_ids=resolved_capability_inputs.connector_ids
                ),
            )

        symbols = engine._portfolio_symbols()
        if not symbols:
            decisions = [
                TradeDecision(
                    symbol="AAPL",
                    action="BUY",
                    quantity=2,
                    target_price=None,
                    reasoning="Deterministic starter position",
                )
            ]
        else:
            decisions = [
                TradeDecision(
                    symbol=symbol,
                    action="HOLD",
                    quantity=None,
                    target_price=None,
                    reasoning="Deterministic hold",
                )
                for symbol in symbols
            ]

        self.completion_service.complete_cycle(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            engine=engine,
            market_data=cycle_ctx["market_data"],
            load_run_state=self._load_run_state,
            update_run_state=self._update_run_state,
            clear_cycle_status=self._clear_cycle_status,
            dispatch_next_cycle=self._dispatch_cycle,
            decisions=decisions,
            report_slug=cycle_ctx.get("prompt_report_slug"),
        )

    def _build_engine(self, backtest_id: int) -> BacktestEngine:
        from app.services.quote_provider import (
            DeterministicQuoteProvider,
            YahooFinanceQuoteProvider,
        )

        settings = get_settings()
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)

        quote_provider: Any
        if settings.backtest_test_mode:
            quote_provider = DeterministicQuoteProvider()
        else:
            quote_provider = YahooFinanceQuoteProvider(
                timeout=settings.quote_provider_timeout_seconds
            )

        return BacktestEngine(
            backtest=backtest,
            session_factory=self.session_factory,
            settings=settings,
            quote_provider=quote_provider,
        )

    def _build_langgraph_runner(self, orchestration_pattern_key: str) -> BacktestLangGraphRunner:
        settings = get_settings()
        analyzer = LiveBacktestSymbolAnalyzer(
            model=settings.backtest_agent_model,
            api_key=settings.backtest_agent_api_key,
            base_url=settings.backtest_agent_base_url,
            timeout_seconds=settings.backtest_agent_timeout_seconds,
            temperature=settings.backtest_agent_temperature,
            api_mode=cast(Any, settings.backtest_agent_api_mode),
        )
        return build_backtest_langgraph_runner(
            pattern_key=orchestration_pattern_key,
            analyzer=analyzer,
        )

    def _load_prompt_report(self, prompt_report_slug: str) -> str:
        with self.session_factory() as session:
            report_service = ReportService(session)
            report = report_service.get_report_model_by_slug(prompt_report_slug)
            return report.content

    def _get_backtest_or_raise(self, backtest_id: int) -> Backtest:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                raise not_found_error("Backtest")
            session.expunge(backtest)
        return backtest

    def _validate_cycle_status(
        self, backtest: Backtest, cycle_date: date, *, allow: list[str]
    ) -> None:
        if backtest.status in _TERMINAL_BACKTEST_STATUSES:
            raise business_rule_error(
                "invalid_backtest_state",
                f"Backtest is {backtest.status}, cannot process callbacks",
            )

        if backtest.current_cycle_date is not None and backtest.current_cycle_date != cycle_date:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                (
                    f"Backtest is waiting for cycle {backtest.current_cycle_date.isoformat()}, "
                    f"not {cycle_date.isoformat()}"
                ),
            )

        if backtest.current_cycle_status not in allow:
            raise business_rule_error(
                "invalid_backtest_cycle_status",
                (
                    f"Backtest cycle status is {backtest.current_cycle_status}, "
                    f"expected one of {allow}"
                ),
            )

    def _set_cycle_status(
        self, backtest_id: int, status: str, *, cycle_date: date | None = None
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.current_cycle_status = status
            if cycle_date is not None:
                backtest.current_cycle_date = cycle_date
            session.commit()

    def _clear_cycle_status(self, backtest_id: int) -> None:
        self.completion_service.clear_cycle_status(self.session_factory, backtest_id)

    def _run_runtime_cycle(
        self,
        backtest_id: int,
        cycle_date: date,
        engine: BacktestEngine,
        cycle_ctx: dict[str, Any],
    ) -> None:
        from app.services.backtest_runtime_adapter import BacktestRuntimeAdapter

        adapter = BacktestRuntimeAdapter(self.session, self.session_factory)
        adapter.execute_cycle(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            cycle_ctx=cycle_ctx,
            engine=engine,
            dispatch_next_cycle=self._dispatch_cycle,
        )

    def _mark_runtime_dispatch_failure(self, backtest_id: int, error_message: str) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            if backtest.current_run_id is not None:
                return
            if backtest.status in _TERMINAL_BACKTEST_STATUSES:
                return
            backtest.status = BacktestStatus.FAILED.value
            backtest.current_cycle_status = BacktestStatus.FAILED.value
            backtest.error_message = error_message
            session.commit()

    @staticmethod
    def _resolve_public_url(settings: Any, path: str) -> str:
        public_base_url = getattr(settings, "public_base_url", None)
        if not public_base_url:
            return path
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{public_base_url}{normalized_path}"

    def _run_internal_cycle(
        self,
        backtest_id: int,
        cycle_date: date,
        engine: BacktestEngine,
        cycle_ctx: dict[str, Any],
    ) -> None:
        prompt_report_slug = str(cycle_ctx["prompt_report_slug"])
        prompt_report = self._load_prompt_report(prompt_report_slug)
        backtest = self._get_backtest_or_raise(backtest_id)
        authored_entry_prompt_body = str(cycle_ctx.get("authored_entry_prompt_body", ""))
        compiled_entry_prompt_body = str(cycle_ctx.get("compiled_entry_prompt_body", ""))
        execution_context_body = str(cycle_ctx.get("execution_context_body", ""))
        pattern_policy = self._resolve_pattern_mention_policy(backtest.orchestration_pattern_key)
        resolved_targets = self._resolve_mentions(
            authored_entry_prompt_body=authored_entry_prompt_body,
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            pattern_policy=pattern_policy,
        )
        resolved_mentions = self._serialize_resolved_mentions(resolved_targets)
        mentioned_target_outputs = self._dispatch_mentioned_target_outputs(
            resolved_targets=resolved_targets,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
        )
        serialized_mentioned_target_outputs = self._serialize_mentioned_target_outputs(
            mentioned_target_outputs
        )
        mentioned_target_output_ids = tuple(
            target["canonical_target_id"] for target in resolved_targets
        )
        if mentioned_target_outputs:
            execution_context_body = self._append_mentioned_target_outputs(
                execution_context_body,
                mentioned_target_outputs,
            )
            full_user_prompt = self._build_full_user_prompt(
                execution_context_body=execution_context_body,
                compiled_entry_prompt_body=compiled_entry_prompt_body,
            )
        else:
            full_user_prompt = str(cycle_ctx.get("full_user_prompt", ""))
        (
            execution_mode,
            resolved_bundle_versions,
            resolved_tool_versions,
            resolved_connector_versions,
            resolved_capability_inputs,
        ) = self._resolve_phase1_capability_inputs(
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            resolved_targets=resolved_targets,
        )
        tool_runtime: BacktestLangGraphToolRuntime | None = None
        if execution_mode == "tool_enabled":
            tool_runtime = self._build_phase1_tool_runtime(
                tool_ids=resolved_capability_inputs.tool_ids,
                connector_ids=resolved_capability_inputs.connector_ids,
                prompt_report_slug=prompt_report_slug,
                prompt_report=prompt_report,
                authored_entry_prompt_body=authored_entry_prompt_body,
                compiled_entry_prompt_body=compiled_entry_prompt_body,
                execution_context_body=execution_context_body,
                full_user_prompt=full_user_prompt,
                resolved_mentions=resolved_mentions,
                mentioned_target_outputs=serialized_mentioned_target_outputs,
                mentioned_target_output_ids=mentioned_target_output_ids,
                cycle_market_data=cast(dict[str, Any], cycle_ctx.get("market_data", {})),
            )
        self._store_orchestration_snapshot(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            prompt_report_slug=prompt_report_slug,
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            pattern_policy_version=pattern_policy.version,
            entry_prompt_hash=self._hash_prompt_text(authored_entry_prompt_body),
            full_user_prompt_hash=self._hash_prompt_text(full_user_prompt),
            execution_mode=execution_mode,
            resolved_mentions=resolved_mentions,
            mentioned_target_outputs=serialized_mentioned_target_outputs,
            resolved_builtin_versions=self._serialize_builtin_versions(resolved_targets),
            resolved_role_versions=self._serialize_role_versions(resolved_targets),
            resolved_character_versions=self._serialize_character_versions(resolved_targets),
            resolved_bundle_versions=resolved_bundle_versions,
            resolved_tool_versions=resolved_tool_versions,
            resolved_connector_versions=resolved_connector_versions,
            tool_call_trace=[],
            approval_trace=self._initial_approval_trace(
                connector_ids=resolved_capability_inputs.connector_ids
            ),
        )
        runner = self._build_langgraph_runner(backtest.orchestration_pattern_key)
        request = BacktestLangGraphRequest(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            prompt_report_slug=prompt_report_slug,
            prompt_report=prompt_report,
            authored_entry_prompt_body=authored_entry_prompt_body,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
            full_user_prompt=full_user_prompt,
            resolved_mentions=tuple(resolved_mentions),
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            mentioned_target_outputs=mentioned_target_output_ids,
            execution_mode=execution_mode,
            resolved_capability_inputs=resolved_capability_inputs,
            tool_runtime=tool_runtime,
        )
        try:
            result = runner.run_cycle(request)
        except BacktestLangGraphToolExecutionError as exc:
            if execution_mode == "tool_enabled":
                self._update_orchestration_snapshot_tool_call_trace(
                    backtest_id=backtest_id,
                    cycle_date=cycle_date,
                    tool_call_trace=exc.tool_call_trace,
                    approval_trace=getattr(exc, "approval_trace", "not_required"),
                )
            raise
        if execution_mode == "tool_enabled":
            self._update_orchestration_snapshot_tool_call_trace(
                backtest_id=backtest_id,
                cycle_date=cycle_date,
                tool_call_trace=result.tool_call_trace,
                approval_trace=getattr(result, "approval_trace", "not_required"),
            )
        self.completion_service.complete_cycle(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            engine=engine,
            market_data=cycle_ctx["market_data"],
            load_run_state=self._load_run_state,
            update_run_state=self._update_run_state,
            clear_cycle_status=self._clear_cycle_status,
            dispatch_next_cycle=self._dispatch_cycle,
            decisions=result.decisions,
            report_markdown=result.report_content,
        )

    @staticmethod
    def _resolve_pattern_mention_policy(pattern_key: str) -> PatternMentionPolicy:
        return resolve_runtime_pattern_mention_policy(pattern_key)

    def _get_runtime_mention_resolver(self) -> BacktestRuntimeMentionResolver:
        return BacktestRuntimeMentionResolver(self.session_factory)

    @staticmethod
    def _get_backtest_pattern_spec_or_raise(pattern_key: str) -> BacktestPatternSpec:
        pattern_spec = get_backtest_pattern_spec(pattern_key)
        if pattern_spec is None:
            raise business_rule_error(
                "invalid_orchestration_pattern",
                f"Unknown orchestration pattern: {pattern_key}",
            )
        return pattern_spec

    def _resolve_phase1_capability_inputs(
        self,
        *,
        orchestration_pattern_key: str,
        resolved_targets: list[dict[str, Any]] | None = None,
    ) -> tuple[
        BacktestExecutionMode,
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        BacktestLangGraphCapabilityInputs,
    ]:
        pattern_spec = self._get_backtest_pattern_spec_or_raise(orchestration_pattern_key)
        execution_mode = pattern_spec.execution_mode
        if execution_mode == "structured_output":
            return execution_mode, [], [], [], BacktestLangGraphCapabilityInputs()
        if execution_mode != "tool_enabled":
            raise business_rule_error(
                "invalid_orchestration_pattern",
                (
                    f"Unsupported execution mode {execution_mode} for orchestration pattern "
                    f"{orchestration_pattern_key}"
                ),
            )

        resolved_tool_specs_by_id: dict[str, SeededToolSpec] = {}
        for configured_tool_id in pattern_spec.default_tool_ids:
            tool_id = configured_tool_id.strip()
            if tool_id in resolved_tool_specs_by_id:
                continue

            tool_spec = self._resolve_tool_spec_or_raise(
                tool_id=tool_id,
                orchestration_pattern_key=orchestration_pattern_key,
            )
            resolved_tool_specs_by_id[tool_spec.tool_id] = tool_spec

        resolved_bundle_specs = self._resolve_phase2_bundle_specs(
            orchestration_pattern_key=orchestration_pattern_key,
            pattern_spec=pattern_spec,
            resolved_targets=resolved_targets or [],
        )
        resolved_connector_specs_by_id: dict[str, SeededConnectorSpec] = {}
        for configured_connector_id in pattern_spec.connector_ids:
            connector_id = configured_connector_id.strip()
            if not connector_id or connector_id in resolved_connector_specs_by_id:
                continue

            connector_spec = self._resolve_connector_spec_or_raise(
                connector_id=connector_id,
                orchestration_pattern_key=orchestration_pattern_key,
            )
            resolved_connector_specs_by_id[connector_spec.connector_id] = connector_spec

        allowed_connector_ids = frozenset(resolved_connector_specs_by_id)
        for bundle_spec in resolved_bundle_specs:
            for configured_tool_id in bundle_spec.tool_ids:
                tool_id = configured_tool_id.strip()
                if tool_id in resolved_tool_specs_by_id:
                    continue

                tool_spec = self._resolve_tool_spec_or_raise(
                    tool_id=tool_id,
                    orchestration_pattern_key=orchestration_pattern_key,
                    bundle_key=bundle_spec.bundle_key,
                )
                resolved_tool_specs_by_id[tool_spec.tool_id] = tool_spec
            if not allowed_connector_ids:
                continue
            for configured_connector_id in bundle_spec.connector_ids:
                connector_id = configured_connector_id.strip()
                if not connector_id or connector_id in resolved_connector_specs_by_id:
                    continue

                connector_spec = self._resolve_connector_spec_or_raise(
                    connector_id=connector_id,
                    orchestration_pattern_key=orchestration_pattern_key,
                    bundle_key=bundle_spec.bundle_key,
                    allowed_connector_ids=allowed_connector_ids,
                )
                resolved_connector_specs_by_id[connector_spec.connector_id] = connector_spec

        resolved_bundle_specs.sort(key=lambda bundle_spec: bundle_spec.bundle_key)
        resolved_tool_specs = sorted(
            resolved_tool_specs_by_id.values(),
            key=lambda tool_spec: tool_spec.tool_id,
        )
        resolved_connector_specs = sorted(
            resolved_connector_specs_by_id.values(),
            key=lambda connector_spec: connector_spec.connector_id,
        )
        resolved_bundle_versions = [
            {"bundle_key": bundle_spec.bundle_key, "revision": bundle_spec.revision}
            for bundle_spec in resolved_bundle_specs
        ]
        resolved_tool_versions = [
            {"tool_id": tool_spec.tool_id, "revision": tool_spec.revision}
            for tool_spec in resolved_tool_specs
        ]
        resolved_connector_versions = [
            {"connector_id": connector_spec.connector_id, "revision": connector_spec.revision}
            for connector_spec in resolved_connector_specs
        ]
        return (
            execution_mode,
            resolved_bundle_versions,
            resolved_tool_versions,
            resolved_connector_versions,
            BacktestLangGraphCapabilityInputs(
                tool_ids=tuple(tool_spec.tool_id for tool_spec in resolved_tool_specs),
                bundle_keys=tuple(bundle_spec.bundle_key for bundle_spec in resolved_bundle_specs),
                connector_ids=tuple(
                    connector_spec.connector_id for connector_spec in resolved_connector_specs
                ),
            ),
        )

    @staticmethod
    def _resolve_tool_spec_or_raise(
        *,
        tool_id: str,
        orchestration_pattern_key: str,
        bundle_key: str | None = None,
    ) -> SeededToolSpec:
        tool_spec = get_seeded_tool_spec(tool_id)
        if tool_spec is None:
            if bundle_key is None:
                raise business_rule_error(
                    "unknown_capability_tool",
                    (
                        f"Capability tool {tool_id!r} configured for orchestration pattern "
                        f"{orchestration_pattern_key} was not found"
                    ),
                )
            raise business_rule_error(
                "unknown_capability_tool",
                (
                    f"Capability tool {tool_id!r} expanded from capability bundle {bundle_key} "
                    f"for orchestration pattern {orchestration_pattern_key} was not found"
                ),
            )
        if tool_spec.tool_id not in _PHASE_1_ALLOWED_TOOL_IDS:
            if bundle_key is None:
                raise business_rule_error(
                    "disallowed_capability_tool",
                    (
                        f"Capability tool {tool_spec.tool_id} is not allowed for phase-1 "
                        f"orchestration pattern {orchestration_pattern_key}"
                    ),
                )
            raise business_rule_error(
                "disallowed_capability_tool",
                (
                    f"Capability tool {tool_spec.tool_id} expanded from capability bundle "
                    f"{bundle_key} is not allowed for phase-1 orchestration pattern "
                    f"{orchestration_pattern_key}"
                ),
            )
        return tool_spec

    @staticmethod
    def _resolve_connector_spec_or_raise(
        *,
        connector_id: str,
        orchestration_pattern_key: str,
        bundle_key: str | None = None,
        allowed_connector_ids: frozenset[str] | None = None,
    ) -> SeededConnectorSpec:
        connector_spec = get_seeded_connector_spec(connector_id)
        if connector_spec is None:
            if bundle_key is None:
                raise business_rule_error(
                    "unknown_capability_connector",
                    (
                        f"Capability connector {connector_id!r} configured for orchestration "
                        f"pattern {orchestration_pattern_key} was not found"
                    ),
                )
            raise business_rule_error(
                "unknown_capability_connector",
                (
                    f"Capability connector {connector_id!r} expanded from capability bundle "
                    f"{bundle_key} for orchestration pattern {orchestration_pattern_key} was "
                    "not found"
                ),
            )
        if (
            allowed_connector_ids is not None
            and connector_spec.connector_id not in allowed_connector_ids
        ):
            if bundle_key is None:
                raise business_rule_error(
                    "disallowed_capability_connector",
                    (
                        f"Capability connector {connector_spec.connector_id} is not allowed for "
                        f"orchestration pattern {orchestration_pattern_key}"
                    ),
                )
            raise business_rule_error(
                "disallowed_capability_connector",
                (
                    f"Capability connector {connector_spec.connector_id} expanded from capability "
                    f"bundle {bundle_key} is not allowed for orchestration pattern "
                    f"{orchestration_pattern_key}"
                ),
            )
        return connector_spec

    @staticmethod
    def _collect_phase2_bundle_keys(resolved_targets: list[dict[str, Any]]) -> list[str]:
        bundle_keys: list[str] = []
        seen: set[str] = set()

        def collect(raw_bundle_keys: Any) -> None:
            if not isinstance(raw_bundle_keys, (list, tuple)):
                return
            for raw_bundle_key in raw_bundle_keys:
                bundle_key = str(raw_bundle_key).strip()
                if bundle_key in seen:
                    continue
                bundle_keys.append(bundle_key)
                seen.add(bundle_key)

        for target in resolved_targets:
            if target["target_type"] == "builtin":
                collect(target.get("capability_bundle_keys", ()))
        for target in resolved_targets:
            if target["target_type"] == "character":
                collect(target.get("role_capability_bundle_keys", ()))
        for target in resolved_targets:
            if target["target_type"] == "character":
                collect(target.get("character_capability_bundle_keys", ()))

        return bundle_keys

    @staticmethod
    def _resolve_phase2_bundle_specs(
        *,
        orchestration_pattern_key: str,
        pattern_spec: BacktestPatternSpec,
        resolved_targets: list[dict[str, Any]],
    ) -> list[SeededCapabilityBundleSpec]:
        allowed_bundle_keys = frozenset(pattern_spec.allowed_bundle_keys)
        resolved_bundle_specs: list[SeededCapabilityBundleSpec] = []
        for bundle_key in BacktestCycleService._collect_phase2_bundle_keys(resolved_targets):
            bundle_spec = get_seeded_capability_bundle_spec(bundle_key)
            if bundle_spec is None:
                raise business_rule_error(
                    "unknown_capability_bundle_key",
                    (
                        f"Capability bundle key {bundle_key!r} referenced by orchestration "
                        f"inputs for pattern {orchestration_pattern_key} was not found"
                    ),
                )
            if bundle_key not in allowed_bundle_keys:
                raise business_rule_error(
                    "disallowed_capability_bundle_key",
                    (
                        f"Capability bundle key {bundle_key} is not allowed for orchestration "
                        f"pattern {orchestration_pattern_key}"
                    ),
                )
            resolved_bundle_specs.append(bundle_spec)
        return resolved_bundle_specs

    def _build_phase1_tool_runtime(
        self,
        *,
        tool_ids: tuple[str, ...],
        connector_ids: tuple[str, ...],
        prompt_report_slug: str,
        prompt_report: str,
        authored_entry_prompt_body: str,
        compiled_entry_prompt_body: str,
        execution_context_body: str,
        full_user_prompt: str,
        resolved_mentions: list[dict[str, Any]],
        mentioned_target_outputs: list[dict[str, Any]],
        mentioned_target_output_ids: tuple[str, ...],
        cycle_market_data: dict[str, Any],
    ) -> BacktestLangGraphToolRuntime:
        cycle_context_payload: dict[str, Any] = {
            "prompt_report_slug": prompt_report_slug,
            "prompt_report": prompt_report,
            "authored_entry_prompt_body": authored_entry_prompt_body,
            "compiled_entry_prompt_body": compiled_entry_prompt_body,
            "execution_context_body": execution_context_body,
            "full_user_prompt": full_user_prompt,
            "resolved_mentions": resolved_mentions,
            "mentioned_target_outputs": mentioned_target_outputs,
            "mentioned_target_output_ids": list(mentioned_target_output_ids),
        }
        adapters: list[BacktestLangGraphToolAdapter] = []
        for tool_id in tool_ids:
            tool_spec = get_seeded_tool_spec(tool_id)
            if tool_spec is None:
                raise business_rule_error(
                    "unknown_capability_tool",
                    f"Capability tool {tool_id!r} was not found for tool runtime construction",
                )
            if tool_id == "ledger.report_lookup":
                adapters.append(self._build_phase1_report_lookup_adapter(tool_spec))
                continue
            if tool_id == "ledger.orchestration_catalog_lookup":
                adapters.append(self._build_phase1_orchestration_catalog_lookup_adapter(tool_spec))
                continue
            if tool_id == "ledger.cycle_context_lookup":
                adapters.append(
                    self._build_phase1_cycle_context_lookup_adapter(
                        tool_spec,
                        cycle_context_payload=cycle_context_payload,
                    )
                )
                continue
            raise business_rule_error(
                "unknown_capability_tool",
                f"Capability tool {tool_id!r} is not supported by the phase-1 runtime",
            )
        for connector_id in connector_ids:
            connector_spec = get_seeded_connector_spec(connector_id)
            if connector_spec is None:
                raise business_rule_error(
                    "unknown_capability_connector",
                    (
                        f"Capability connector {connector_id!r} was not found for connector "
                        "runtime construction"
                    ),
                )
            if connector_id == "ledger.mcp.market_data":
                adapters.append(
                    self._build_phase3_market_data_connector_adapter(
                        connector_spec,
                        cycle_market_data=cycle_market_data,
                    )
                )
                continue
            if connector_id == "ledger.mcp.company_filings":
                adapters.append(
                    self._build_phase3_company_filings_connector_adapter(
                        connector_spec,
                        cycle_context_payload=cycle_context_payload,
                    )
                )
                continue
            raise business_rule_error(
                "unknown_capability_connector",
                (f"Capability connector {connector_id!r} is not supported by the phase-3 runtime"),
            )

        return BacktestLangGraphToolRuntime(adapters=tuple(adapters))

    def _build_phase1_report_lookup_adapter(
        self, tool_spec: SeededToolSpec
    ) -> BacktestLangGraphToolAdapter:
        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            slug = str(arguments.get("slug", "")).strip()
            if not slug:
                raise business_rule_error(
                    "invalid_tool_arguments",
                    "Report lookup requires a non-empty slug",
                )
            with self.session_factory() as session:
                report_service = ReportService(session)
                report = report_service.get_report_by_slug(slug)
                return report.model_dump(mode="json", by_alias=True)

        return BacktestLangGraphToolAdapter(
            tool_id=tool_spec.tool_id,
            description=tool_spec.description,
            parameters_schema=_REPORT_LOOKUP_PARAMETERS_SCHEMA,
            invoke=invoke,
        )

    def _build_phase1_orchestration_catalog_lookup_adapter(
        self, tool_spec: SeededToolSpec
    ) -> BacktestLangGraphToolAdapter:
        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            handle_value = arguments.get("handle")
            with self.session_factory() as session:
                orchestration_service = OrchestrationService(session)
                catalog = orchestration_service.list_mention_catalog().model_dump(
                    mode="json",
                    by_alias=True,
                )
            if handle_value is None:
                return catalog

            handle = str(handle_value).strip().lower()
            if not handle:
                raise business_rule_error(
                    "invalid_tool_arguments",
                    "Orchestration catalog lookup handle must be non-empty when provided",
                )
            targets = catalog.get("targets", [])
            match = next(
                (
                    target
                    for target in targets
                    if str(target.get("handle", "")).strip().lower() == handle
                ),
                None,
            )
            if match is None:
                raise business_rule_error(
                    "orchestration_catalog_target_not_found",
                    f"No orchestration catalog target found for handle {handle!r}",
                )
            return cast(dict[str, Any], match)

        return BacktestLangGraphToolAdapter(
            tool_id=tool_spec.tool_id,
            description=tool_spec.description,
            parameters_schema=_ORCHESTRATION_CATALOG_LOOKUP_PARAMETERS_SCHEMA,
            invoke=invoke,
        )

    def _build_phase1_cycle_context_lookup_adapter(
        self,
        tool_spec: SeededToolSpec,
        *,
        cycle_context_payload: dict[str, Any],
    ) -> BacktestLangGraphToolAdapter:
        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            artifact_key = str(arguments.get("artifact_key", "")).strip()
            if artifact_key not in _PHASE_1_CYCLE_CONTEXT_ARTIFACT_KEYS:
                raise business_rule_error(
                    "invalid_cycle_context_lookup",
                    f"Unknown cycle context artifact key {artifact_key!r}",
                )
            return {
                "artifact_key": artifact_key,
                "value": cycle_context_payload[artifact_key],
            }

        return BacktestLangGraphToolAdapter(
            tool_id=tool_spec.tool_id,
            description=tool_spec.description,
            parameters_schema=_CYCLE_CONTEXT_LOOKUP_PARAMETERS_SCHEMA,
            invoke=invoke,
        )

    def _build_phase3_market_data_connector_adapter(
        self,
        connector_spec: SeededConnectorSpec,
        *,
        cycle_market_data: dict[str, Any],
    ) -> BacktestLangGraphToolAdapter:
        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            symbol = normalize_symbol(str(arguments.get("symbol", "")).strip())
            if not symbol:
                raise business_rule_error(
                    "invalid_connector_arguments",
                    "Market data connector requires a non-empty symbol",
                )
            payload = cycle_market_data.get(symbol)
            if not isinstance(payload, dict):
                raise business_rule_error(
                    "connector_market_data_not_found",
                    f"No market data is available for symbol {symbol!r}",
                )
            return {
                "symbol": symbol,
                "market_data": {
                    str(key): (str(value) if isinstance(value, Decimal) else value)
                    for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
                },
            }

        return BacktestLangGraphToolAdapter(
            tool_id=connector_spec.connector_id,
            description=connector_spec.description,
            parameters_schema=_MARKET_DATA_CONNECTOR_PARAMETERS_SCHEMA,
            invoke=invoke,
            approval_required=True,
            approval_granted=connector_spec.lifecycle == "approved",
            approval_metadata={"kind": "connector", "transport": connector_spec.transport},
        )

    def _build_phase3_company_filings_connector_adapter(
        self,
        connector_spec: SeededConnectorSpec,
        *,
        cycle_context_payload: dict[str, Any],
    ) -> BacktestLangGraphToolAdapter:
        def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            symbol = normalize_symbol(str(arguments.get("symbol", "")).strip())
            if not symbol:
                raise business_rule_error(
                    "invalid_connector_arguments",
                    "Company filings connector requires a non-empty symbol",
                )
            return {
                "symbol": symbol,
                "prompt_report_slug": str(cycle_context_payload["prompt_report_slug"]),
                "filings": [],
            }

        return BacktestLangGraphToolAdapter(
            tool_id=connector_spec.connector_id,
            description=connector_spec.description,
            parameters_schema=_COMPANY_FILINGS_CONNECTOR_PARAMETERS_SCHEMA,
            invoke=invoke,
            approval_required=True,
            approval_granted=connector_spec.lifecycle == "approved",
            approval_metadata={"kind": "connector", "transport": connector_spec.transport},
        )

    def _resolve_mentions(
        self,
        *,
        authored_entry_prompt_body: str,
        orchestration_pattern_key: str,
        pattern_policy: PatternMentionPolicy,
    ) -> list[dict[str, Any]]:
        return self._get_runtime_mention_resolver().resolve_targets(
            authored_entry_prompt_body=authored_entry_prompt_body,
            orchestration_pattern_key=orchestration_pattern_key,
            pattern_policy=pattern_policy,
        )

    def _dispatch_mentioned_target_outputs(
        self,
        *,
        resolved_targets: list[dict[str, Any]],
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> list[dict[str, Any]]:
        return self._get_runtime_mention_resolver().build_mentioned_target_outputs(
            resolved_targets=resolved_targets,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
        )

    @staticmethod
    def _build_full_user_prompt(
        *, execution_context_body: str, compiled_entry_prompt_body: str
    ) -> str:
        return build_runtime_full_user_prompt(
            execution_context_body=execution_context_body,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
        )

    @staticmethod
    def _hash_prompt_text(prompt_text: str) -> str:
        return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_resolved_mentions(
        resolved_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return serialize_resolved_mentions(resolved_targets)

    @staticmethod
    def _serialize_mentioned_target_outputs(
        mentioned_target_outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return serialize_mentioned_target_outputs(mentioned_target_outputs)

    @staticmethod
    def _serialize_builtin_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return serialize_builtin_versions(resolved_targets)

    @staticmethod
    def _serialize_role_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return serialize_role_versions(resolved_targets)

    @staticmethod
    def _serialize_character_versions(
        resolved_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return serialize_character_versions(resolved_targets)

    @staticmethod
    def _append_mentioned_target_outputs(
        execution_context_body: str, mentioned_target_outputs: list[dict[str, Any]]
    ) -> str:
        return append_mentioned_target_outputs(execution_context_body, mentioned_target_outputs)

    @staticmethod
    def _initial_approval_trace(*, connector_ids: tuple[str, ...]) -> Any:
        if connector_ids:
            return []
        return "not_required"

    def _store_orchestration_snapshot(
        self,
        *,
        backtest_id: int,
        cycle_date: date,
        prompt_report_slug: str,
        orchestration_pattern_key: str,
        pattern_policy_version: int,
        entry_prompt_hash: str,
        full_user_prompt_hash: str,
        execution_mode: str,
        resolved_mentions: list[dict[str, Any]],
        mentioned_target_outputs: list[dict[str, Any]],
        resolved_builtin_versions: list[dict[str, Any]],
        resolved_role_versions: list[dict[str, Any]],
        resolved_character_versions: list[dict[str, Any]],
        resolved_bundle_versions: list[dict[str, Any]],
        resolved_tool_versions: list[dict[str, Any]],
        resolved_connector_versions: list[dict[str, Any]],
        tool_call_trace: list[dict[str, Any]],
        approval_trace: Any,
    ) -> None:
        if not callable(self.session_factory):
            logger.debug(
                (
                    "Skipping orchestration snapshot storage for backtest %d on %s "
                    "without a session factory"
                ),
                backtest_id,
                cycle_date.isoformat(),
            )
            return

        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                logger.debug(
                    "Skipping orchestration snapshot storage for missing backtest %d on %s",
                    backtest_id,
                    cycle_date.isoformat(),
                )
                return

            existing = session.scalar(
                select(BacktestOrchestrationSnapshot).where(
                    BacktestOrchestrationSnapshot.backtest_id == backtest_id,
                    BacktestOrchestrationSnapshot.cycle_date == cycle_date,
                )
            )
            snapshot = existing or BacktestOrchestrationSnapshot(
                backtest_id=backtest_id,
                cycle_date=cycle_date,
                prompt_report_slug=prompt_report_slug,
                orchestration_pattern_key=orchestration_pattern_key,
                pattern_policy_version=pattern_policy_version,
                entry_prompt_hash=entry_prompt_hash,
                full_user_prompt_hash=full_user_prompt_hash,
                execution_mode=execution_mode,
                resolved_mentions=resolved_mentions,
                mentioned_target_outputs=mentioned_target_outputs,
                resolved_builtin_versions=resolved_builtin_versions,
                resolved_role_versions=resolved_role_versions,
                resolved_character_versions=resolved_character_versions,
                resolved_bundle_versions=resolved_bundle_versions,
                resolved_tool_versions=resolved_tool_versions,
                resolved_connector_versions=resolved_connector_versions,
                tool_call_trace=tool_call_trace,
                approval_trace=approval_trace,
            )
            snapshot.prompt_report_slug = prompt_report_slug
            snapshot.orchestration_pattern_key = orchestration_pattern_key
            snapshot.pattern_policy_version = pattern_policy_version
            snapshot.entry_prompt_hash = entry_prompt_hash
            snapshot.full_user_prompt_hash = full_user_prompt_hash
            snapshot.execution_mode = execution_mode
            snapshot.resolved_mentions = list(resolved_mentions)
            snapshot.mentioned_target_outputs = list(mentioned_target_outputs)
            snapshot.resolved_builtin_versions = list(resolved_builtin_versions)
            snapshot.resolved_role_versions = list(resolved_role_versions)
            snapshot.resolved_character_versions = list(resolved_character_versions)
            snapshot.resolved_bundle_versions = list(resolved_bundle_versions)
            snapshot.resolved_tool_versions = list(resolved_tool_versions)
            snapshot.resolved_connector_versions = list(resolved_connector_versions)
            snapshot.tool_call_trace = list(tool_call_trace)
            snapshot.approval_trace = (
                list(approval_trace) if isinstance(approval_trace, list) else approval_trace
            )
            session.add(snapshot)
            session.commit()

        logger.debug(
            "Stored orchestration snapshot for backtest %d on %s",
            backtest_id,
            cycle_date.isoformat(),
        )

    def _update_orchestration_snapshot_tool_call_trace(
        self,
        *,
        backtest_id: int,
        cycle_date: date,
        tool_call_trace: list[dict[str, Any]],
        approval_trace: Any = "not_required",
    ) -> None:
        if not callable(self.session_factory):
            logger.debug(
                (
                    "Skipping orchestration snapshot trace update for backtest %d on %s "
                    "without a session factory"
                ),
                backtest_id,
                cycle_date.isoformat(),
            )
            return

        with self.session_factory() as session:
            snapshot = session.scalar(
                select(BacktestOrchestrationSnapshot).where(
                    BacktestOrchestrationSnapshot.backtest_id == backtest_id,
                    BacktestOrchestrationSnapshot.cycle_date == cycle_date,
                )
            )
            if snapshot is None:
                logger.debug(
                    "Skipping orchestration snapshot trace update for missing snapshot "
                    "row %d on %s",
                    backtest_id,
                    cycle_date.isoformat(),
                )
                return

            snapshot.tool_call_trace = list(tool_call_trace)
            snapshot.approval_trace = (
                list(approval_trace) if isinstance(approval_trace, list) else approval_trace
            )
            session.commit()

        logger.debug(
            "Updated orchestration snapshot trace for backtest %d on %s",
            backtest_id,
            cycle_date.isoformat(),
        )

    def _store_run_state(
        self,
        backtest_id: int,
        schedule: list[date],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.results = {
                "_run_state": {
                    "schedule": [cycle_date.isoformat() for cycle_date in schedule],
                    "benchmark_history": {
                        symbol: [(point_date, str(value)) for point_date, value in points]
                        for symbol, points in benchmark_history.items()
                    },
                    "trade_log": [],
                    "equity_points": [],
                }
            }
            session.commit()

    def _load_run_state(self, backtest_id: int) -> dict[str, Any]:
        return self.completion_service.load_run_state(self.session_factory, backtest_id)

    def _update_run_state(
        self,
        backtest_id: int,
        *,
        equity_points: list[tuple[str, Decimal]],
        trade_log: list[dict[str, Any]],
    ) -> None:
        self.completion_service.update_run_state(
            self.session_factory,
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
