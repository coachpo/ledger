from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import business_rule_error, not_found_error
from app.langgraph.runner import (
    BacktestLangGraphRequest,
    BacktestLangGraphRunner,
    LiveBacktestSymbolAnalyzer,
)
from app.langgraph.seeds import (
    ANALYST_REVIEWER_PATTERN_MENTION_POLICY,
    SEED_PATTERN_MENTION_POLICY,
    PatternMentionPolicy,
    build_backtest_langgraph_runner,
    get_seeded_builtin_spec_for_handle,
)
from app.models.backtest import Backtest
from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot
from app.repositories.orchestration_character import OrchestrationCharacterRepository
from app.schemas.backtest import BacktestStatus, TradeDecision
from app.schemas.backtest_callback import (
    CycleCompleteResponse,
    CycleReportUpload,
    CycleTradeResult,
    CycleTradesRequest,
    CycleTradesResponse,
)
from app.schemas.report import ReportMetadata
from app.services.backtest_engine import BacktestEngine
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)
_MENTION_RE = re.compile(r"(?<![@A-Za-z0-9_])@(?P<handle>[A-Za-z][A-Za-z0-9_]*)\b")

_TERMINAL_BACKTEST_STATUSES = {
    BacktestStatus.COMPLETED,
    BacktestStatus.FAILED,
    BacktestStatus.CANCELLED,
}


class BacktestCycleService:
    def __init__(self, session: Session, session_factory: sessionmaker[Session]) -> None:
        self.session = session
        self.session_factory = session_factory

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
        date_str, equity_value = engine.record_cycle_equity(cycle_date, market_data)

        run_state = self._load_run_state(backtest_id)
        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule",
            )

        benchmark_history = run_state["benchmark_history"]
        trade_log = run_state["trade_log"]
        equity_points = list(run_state["equity_points"])
        if equity_points and equity_points[-1][0] == date_str:
            equity_points[-1] = (date_str, equity_value)
        else:
            equity_points.append((date_str, equity_value))

        current_index = schedule.index(cycle_date)
        is_last_cycle = current_index >= len(schedule) - 1
        if is_last_cycle:
            engine.finalize(
                equity_points=equity_points,
                benchmark_history=benchmark_history,
                trade_log=trade_log,
                schedule=schedule,
            )
            self._clear_cycle_status(backtest_id)
            refreshed = self._get_backtest_or_raise(backtest_id)
            return CycleCompleteResponse(
                backtest_id=backtest_id,
                status=refreshed.status,
                completed_cycles=refreshed.completed_cycles,
                total_cycles=refreshed.total_cycles,
                next_cycle_date=None,
                finished=True,
            )

        next_cycle_date = schedule[current_index + 1]
        self._update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        self._dispatch_cycle(backtest_id, next_cycle_date)

        refreshed = self._get_backtest_or_raise(backtest_id)
        return CycleCompleteResponse(
            backtest_id=backtest_id,
            status=refreshed.status,
            completed_cycles=refreshed.completed_cycles,
            total_cycles=refreshed.total_cycles,
            next_cycle_date=next_cycle_date.isoformat(),
            finished=False,
        )

    def _dispatch_cycle(self, backtest_id: int, cycle_date: date) -> None:
        engine = self._build_engine(backtest_id)

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

            self._store_orchestration_snapshot(
                backtest_id=backtest_id,
                cycle_date=cycle_date,
                prompt_report_slug=str(cycle_ctx.get("prompt_report_slug", "")),
                orchestration_pattern_key=backtest.orchestration_pattern_key,
                pattern_policy_version=pattern_policy.version,
                entry_prompt_hash=self._hash_prompt_text(authored_entry_prompt_body),
                full_user_prompt_hash=self._hash_prompt_text(full_user_prompt),
                resolved_mentions=self._serialize_resolved_mentions(resolved_targets),
                mentioned_target_outputs=self._serialize_mentioned_target_outputs(
                    mentioned_target_outputs
                ),
                resolved_builtin_versions=self._serialize_builtin_versions(resolved_targets),
                resolved_role_versions=self._serialize_role_versions(resolved_targets),
                resolved_character_versions=self._serialize_character_versions(resolved_targets),
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

        run_state = self._load_run_state(backtest_id)
        trade_log = list(run_state["trade_log"])
        cycle_trades = engine.apply_cycle_trades(
            cycle_date=cycle_date,
            decisions=decisions,
            market_data=cycle_ctx["market_data"],
            report_slug=cycle_ctx.get("prompt_report_slug"),
        )
        trade_log.extend(cycle_trades)

        date_str, equity_value = engine.record_cycle_equity(cycle_date, cycle_ctx["market_data"])
        equity_points = list(run_state["equity_points"])
        if equity_points and equity_points[-1][0] == date_str:
            equity_points[-1] = (date_str, equity_value)
        else:
            equity_points.append((date_str, equity_value))

        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            engine._mark_failed(
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule"
            )
            self._clear_cycle_status(backtest_id)
            return

        benchmark_history = run_state["benchmark_history"]
        current_index = schedule.index(cycle_date)
        if current_index >= len(schedule) - 1:
            engine.finalize(
                equity_points=equity_points,
                benchmark_history=benchmark_history,
                trade_log=trade_log,
                schedule=schedule,
            )
            self._clear_cycle_status(backtest_id)
            return

        self._update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        self._dispatch_cycle(backtest_id, schedule[current_index + 1])

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
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return
            backtest.current_cycle_status = None
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
        self._store_orchestration_snapshot(
            backtest_id=backtest_id,
            cycle_date=cycle_date,
            prompt_report_slug=prompt_report_slug,
            orchestration_pattern_key=backtest.orchestration_pattern_key,
            pattern_policy_version=pattern_policy.version,
            entry_prompt_hash=self._hash_prompt_text(authored_entry_prompt_body),
            full_user_prompt_hash=self._hash_prompt_text(full_user_prompt),
            resolved_mentions=resolved_mentions,
            mentioned_target_outputs=self._serialize_mentioned_target_outputs(
                mentioned_target_outputs
            ),
            resolved_builtin_versions=self._serialize_builtin_versions(resolved_targets),
            resolved_role_versions=self._serialize_role_versions(resolved_targets),
            resolved_character_versions=self._serialize_character_versions(resolved_targets),
        )
        runner = self._build_langgraph_runner(backtest.orchestration_pattern_key)
        result = runner.run_cycle(
            BacktestLangGraphRequest(
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
            )
        )
        report_slug = engine._store_cycle_report(cycle_date, result.report_content)
        trade_results = engine.apply_cycle_trades(
            cycle_date=cycle_date,
            decisions=result.decisions,
            market_data=cycle_ctx["market_data"],
            report_slug=report_slug,
        )

        run_state = self._load_run_state(backtest_id)
        trade_log = list(run_state["trade_log"])
        trade_log.extend(trade_results)
        date_str, equity_value = engine.record_cycle_equity(cycle_date, cycle_ctx["market_data"])

        schedule = run_state["schedule"]
        if cycle_date not in schedule:
            raise business_rule_error(
                "invalid_backtest_cycle_date",
                f"Cycle date {cycle_date.isoformat()} is not part of the backtest schedule",
            )

        benchmark_history = run_state["benchmark_history"]
        equity_points = list(run_state["equity_points"])
        if equity_points and equity_points[-1][0] == date_str:
            equity_points[-1] = (date_str, equity_value)
        else:
            equity_points.append((date_str, equity_value))

        current_index = schedule.index(cycle_date)
        is_last_cycle = current_index >= len(schedule) - 1
        if is_last_cycle:
            engine.finalize(
                equity_points=equity_points,
                benchmark_history=benchmark_history,
                trade_log=trade_log,
                schedule=schedule,
            )
            self._clear_cycle_status(backtest_id)
            return

        self._update_run_state(
            backtest_id,
            equity_points=equity_points,
            trade_log=trade_log,
        )
        next_cycle_date = schedule[current_index + 1]
        self._dispatch_cycle(backtest_id, next_cycle_date)

    @staticmethod
    def _resolve_pattern_mention_policy(pattern_key: str) -> PatternMentionPolicy:
        if pattern_key == "seeded_internal_backtest_v1":
            return SEED_PATTERN_MENTION_POLICY
        if pattern_key == "analyst_reviewer_v1":
            return ANALYST_REVIEWER_PATTERN_MENTION_POLICY
        return SEED_PATTERN_MENTION_POLICY

    def _resolve_mentions(
        self,
        *,
        authored_entry_prompt_body: str,
        orchestration_pattern_key: str,
        pattern_policy: PatternMentionPolicy,
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()

        for match in _MENTION_RE.finditer(authored_entry_prompt_body):
            original_text = match.group(0)
            handle = match.group("handle").lower()
            builtin_spec = get_seeded_builtin_spec_for_handle(handle)
            if builtin_spec is not None:
                canonical_target_id = builtin_spec.canonical_target_id
                if canonical_target_id in seen:
                    continue
                if handle not in pattern_policy.allowed_builtin_handles:
                    self._raise_mention_not_allowed(handle, orchestration_pattern_key)
                resolved.append(
                    {
                        "original_text": original_text,
                        "handle": handle,
                        "canonical_target_id": canonical_target_id,
                        "target_type": "builtin",
                        "role_id": None,
                        "role_version": None,
                        "character_id": None,
                        "character_version": None,
                        "mention_order": len(resolved),
                        "builtin_revision": builtin_spec.revision,
                    }
                )
                seen.add(canonical_target_id)
                continue

            canonical_target_id = f"character:{handle}"
            if canonical_target_id in seen:
                continue
            if not pattern_policy.allow_characters:
                self._raise_mention_not_allowed(handle, orchestration_pattern_key)

            character_record = self._resolve_orchestration_character(handle)
            character_spec = character_record["character"]
            role_spec = character_record["role"]
            if not character_spec.enabled:
                raise business_rule_error(
                    "mention_target_disabled",
                    f"Mention target @{handle} is disabled",
                )
            if not role_spec.enabled:
                raise business_rule_error(
                    "character_role_disabled",
                    f"Character role for @{handle} is disabled",
                )
            resolved.append(
                {
                    "original_text": original_text,
                    "handle": handle,
                    "canonical_target_id": canonical_target_id,
                    "target_type": "character",
                    "role_id": role_spec.id,
                    "role_version": role_spec.version,
                    "character_id": character_spec.id,
                    "character_version": character_spec.version,
                    "mention_order": len(resolved),
                    "role_name": role_spec.name,
                    "role_key": role_spec.key,
                    "role_system_prompt": role_spec.system_prompt,
                    "character_prompt_append": character_spec.prompt_append,
                }
            )
            seen.add(canonical_target_id)

        return resolved

    def _resolve_orchestration_character(self, handle: str) -> Any:
        with self.session_factory() as session:
            character = OrchestrationCharacterRepository(session).get_by_handle(handle)
            if character is None:
                raise business_rule_error(
                    "mention_target_not_found",
                    f"Mention target @{handle} was not found",
                )
            session.refresh(character)
            role = character.role
            if role is None:
                raise business_rule_error(
                    "mention_target_not_found",
                    f"Mention target @{handle} was not found",
                )
            session.refresh(role)
            return {
                "character": character,
                "role": role,
            }

    def _dispatch_mentioned_target_outputs(
        self,
        *,
        resolved_targets: list[dict[str, Any]],
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> list[dict[str, Any]]:
        mentioned_target_outputs: list[dict[str, Any]] = []
        for target in resolved_targets:
            if target["target_type"] == "builtin":
                output_markdown = self._run_builtin_pre_run_step(
                    handle=str(target["handle"]),
                    compiled_entry_prompt_body=compiled_entry_prompt_body,
                    execution_context_body=execution_context_body,
                )
            else:
                output_markdown = self._run_character_pre_run_step(
                    target=target,
                    compiled_entry_prompt_body=compiled_entry_prompt_body,
                    execution_context_body=execution_context_body,
                )
            mentioned_target_outputs.append(
                {
                    "handle": target["handle"],
                    "canonical_target_id": target["canonical_target_id"],
                    "target_type": target["target_type"],
                    "output_markdown": output_markdown,
                }
            )
        return mentioned_target_outputs

    def _run_builtin_pre_run_step(
        self,
        *,
        handle: str,
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> str:
        builtin_spec = get_seeded_builtin_spec_for_handle(handle)
        if builtin_spec is None:
            raise business_rule_error(
                "mention_target_not_found",
                f"Mention target @{handle} was not found",
            )
        return (
            f"{builtin_spec.description} Entry prompt focus: "
            f"{self._compact_artifact_text(compiled_entry_prompt_body)}. "
            f"Execution context focus: {self._compact_artifact_text(execution_context_body)}."
        )

    def _run_character_pre_run_step(
        self,
        *,
        target: dict[str, Any],
        compiled_entry_prompt_body: str,
        execution_context_body: str,
    ) -> str:
        character_guidance = str(target.get("character_prompt_append") or "").strip()
        guidance_summary = (
            self._compact_artifact_text(character_guidance)
            if character_guidance
            else "No character-specific guidance provided"
        )
        return (
            f"{target['role_name']} execution brief. "
            f"System prompt: {self._compact_artifact_text(str(target['role_system_prompt']))}. "
            f"Character guidance: {guidance_summary}. "
            f"Entry prompt focus: {self._compact_artifact_text(compiled_entry_prompt_body)}. "
            f"Execution context focus: {self._compact_artifact_text(execution_context_body)}."
        )

    @staticmethod
    def _compact_artifact_text(value: str) -> str:
        normalized = " ".join(value.split())
        return normalized or "none"

    @staticmethod
    def _raise_mention_not_allowed(handle: str, orchestration_pattern_key: str) -> None:
        raise business_rule_error(
            "mention_target_not_allowed_by_pattern",
            (
                f"Mention target @{handle} is not allowed by orchestration pattern "
                f"{orchestration_pattern_key}"
            ),
        )

    @staticmethod
    def _build_full_user_prompt(
        *, execution_context_body: str, compiled_entry_prompt_body: str
    ) -> str:
        return "\n\n".join(
            [part for part in (execution_context_body, compiled_entry_prompt_body) if part]
        )

    @staticmethod
    def _hash_prompt_text(prompt_text: str) -> str:
        return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_resolved_mentions(
        resolved_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "original_text": target["original_text"],
                "handle": target["handle"],
                "canonical_target_id": target["canonical_target_id"],
                "target_type": target["target_type"],
                "role_id": target["role_id"],
                "role_version": target["role_version"],
                "character_id": target["character_id"],
                "character_version": target["character_version"],
                "mention_order": target["mention_order"],
            }
            for target in resolved_targets
        ]

    @staticmethod
    def _serialize_mentioned_target_outputs(
        mentioned_target_outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "handle": target["handle"],
                "canonical_target_id": target["canonical_target_id"],
                "target_type": target["target_type"],
                "output_markdown": target["output_markdown"],
            }
            for target in mentioned_target_outputs
        ]

    @staticmethod
    def _serialize_builtin_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "canonical_target_id": target["canonical_target_id"],
                "handle": target["handle"],
                "revision": target["builtin_revision"],
            }
            for target in resolved_targets
            if target["target_type"] == "builtin"
        ]

    @staticmethod
    def _serialize_role_versions(resolved_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "canonical_target_id": f"role:{target['role_key']}",
                "role_id": target["role_id"],
                "version": target["role_version"],
            }
            for target in resolved_targets
            if target["target_type"] == "character"
        ]

    @staticmethod
    def _serialize_character_versions(
        resolved_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "canonical_target_id": target["canonical_target_id"],
                "character_id": target["character_id"],
                "version": target["character_version"],
            }
            for target in resolved_targets
            if target["target_type"] == "character"
        ]

    @staticmethod
    def _append_mentioned_target_outputs(
        execution_context_body: str, mentioned_target_outputs: list[dict[str, Any]]
    ) -> str:
        if not mentioned_target_outputs:
            return execution_context_body
        lines = ["## Mentioned Target Outputs"]
        for mention in mentioned_target_outputs:
            lines.append(f"- {mention['handle']}: {mention['output_markdown']}")
        mentioned_outputs = "\n".join(lines)
        normalized_execution_context_body = execution_context_body.rstrip("\n")
        if not normalized_execution_context_body:
            return mentioned_outputs
        return f"{normalized_execution_context_body}\n\n{mentioned_outputs}"

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
        resolved_mentions: list[dict[str, Any]],
        mentioned_target_outputs: list[dict[str, Any]],
        resolved_builtin_versions: list[dict[str, Any]],
        resolved_role_versions: list[dict[str, Any]],
        resolved_character_versions: list[dict[str, Any]],
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
            if existing is not None:
                logger.debug(
                    "Skipping orchestration snapshot rewrite for backtest %d on %s",
                    backtest_id,
                    cycle_date.isoformat(),
                )
                return

            session.add(
                BacktestOrchestrationSnapshot(
                    backtest_id=backtest_id,
                    cycle_date=cycle_date,
                    prompt_report_slug=prompt_report_slug,
                    orchestration_pattern_key=orchestration_pattern_key,
                    pattern_policy_version=pattern_policy_version,
                    entry_prompt_hash=entry_prompt_hash,
                    full_user_prompt_hash=full_user_prompt_hash,
                    resolved_mentions=resolved_mentions,
                    mentioned_target_outputs=mentioned_target_outputs,
                    resolved_builtin_versions=resolved_builtin_versions,
                    resolved_role_versions=resolved_role_versions,
                    resolved_character_versions=resolved_character_versions,
                )
            )
            session.commit()

        logger.debug(
            "Stored orchestration snapshot for backtest %d on %s",
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
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            raw_results = backtest.results if backtest is not None else None

        if not isinstance(raw_results, dict):
            return {
                "schedule": [],
                "benchmark_history": {},
                "trade_log": [],
                "equity_points": [],
            }

        raw_run_state = raw_results.get("_run_state", {})
        if not isinstance(raw_run_state, dict):
            raw_run_state = {}

        raw_benchmark_history = raw_run_state.get("benchmark_history", {})
        benchmark_history: dict[str, list[tuple[str, Decimal]]] = {}
        if isinstance(raw_benchmark_history, dict):
            for symbol, points in raw_benchmark_history.items():
                if not isinstance(symbol, str) or not isinstance(points, list):
                    continue
                benchmark_history[symbol] = [
                    (str(point_date), Decimal(str(value))) for point_date, value in points
                ]

        raw_equity_points = raw_run_state.get("equity_points", [])
        equity_points = [
            (str(point_date), Decimal(str(value))) for point_date, value in raw_equity_points
        ]

        raw_trade_log = raw_run_state.get("trade_log", [])
        trade_log = [item for item in raw_trade_log if isinstance(item, dict)]

        return {
            "schedule": [
                date.fromisoformat(str(cycle_date))
                for cycle_date in raw_run_state.get("schedule", [])
            ],
            "benchmark_history": benchmark_history,
            "trade_log": trade_log,
            "equity_points": equity_points,
        }

    def _update_run_state(
        self,
        backtest_id: int,
        *,
        equity_points: list[tuple[str, Decimal]],
        trade_log: list[dict[str, Any]],
    ) -> None:
        with self.session_factory() as session:
            backtest = session.get(Backtest, backtest_id)
            if backtest is None:
                return

            existing_results = backtest.results if isinstance(backtest.results, dict) else {}
            run_state = existing_results.get("_run_state", {})
            if not isinstance(run_state, dict):
                run_state = {}

            run_state["equity_points"] = [
                (point_date, str(value)) for point_date, value in equity_points
            ]
            run_state["trade_log"] = trade_log
            backtest.results = {**existing_results, "_run_state": run_state}
            session.commit()
