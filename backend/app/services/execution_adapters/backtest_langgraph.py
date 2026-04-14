from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from functools import partial
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import business_rule_error
from app.core.formatting import normalize_symbol
from app.langgraph.runner import (
    BacktestLangGraphCapabilityInputs,
    BacktestLangGraphRequest,
    BacktestLangGraphRunner,
    BacktestLangGraphToolAdapter,
    BacktestLangGraphToolRuntime,
    LiveBacktestSymbolAnalyzer,
)
from app.langgraph.seeds import build_backtest_langgraph_runner
from app.repositories.workflow_spec import WorkflowSpecRepository
from app.schemas.runtime import ApprovalMode, CapabilityType
from app.services.execution_adapters._shared import (
    build_waiting_approval_result,
    extract_graph_steps,
    has_approved_capability,
    load_checkpoint_state,
    load_json_input,
    optional_text_input,
    require_text_input,
)
from app.services.execution_adapters.contracts import (
    ExecutionAdapter,
    ExecutionAdapterRequest,
    ExecutionAdapterResult,
    ExecutionAdapterTraceEvent,
    ExecutionArtifactPatch,
)

_ADAPTER_KEY = "backtest_langgraph"
_APPROVAL_STEP_KEY = "tool_runtime"


class BacktestLangGraphExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        session: Session,
        *,
        runner_factory: Callable[[str], BacktestLangGraphRunner] | None = None,
    ) -> None:
        self.session = session
        self.workflow_repository = WorkflowSpecRepository(session)
        self.runner_factory = runner_factory or self._build_runner

    def execute(self, request: ExecutionAdapterRequest) -> ExecutionAdapterResult:
        if request.snapshot.execution_kind != "workflow":
            raise business_rule_error(
                "runtime_backtest_adapter_invalid_kind",
                "Backtest LangGraph adapter requires executionKind=workflow",
            )
        if request.caller_type != "backtest":
            raise business_rule_error(
                "runtime_backtest_adapter_invalid_caller",
                "Backtest LangGraph adapter requires callerType=backtest",
            )
        workflow = self._load_workflow(request)
        self._validate_frozen_plan(workflow.graph_definition, request)
        cycle_date = self._load_cycle_date(request)
        prompt_report_slug = require_text_input(request.snapshot.inputs, "prompt_report_slug")
        prompt_report = require_text_input(request.snapshot.inputs, "prompt_report")
        authored_entry_prompt_body = optional_text_input(
            request.snapshot.inputs,
            "authored_entry_prompt_body",
        )
        compiled_entry_prompt_body = optional_text_input(
            request.snapshot.inputs,
            "compiled_entry_prompt_body",
        )
        execution_context_body = optional_text_input(
            request.snapshot.inputs,
            "execution_context_body",
        )
        full_user_prompt = optional_text_input(request.snapshot.inputs, "full_user_prompt")
        resolved_mentions = cast(
            list[dict[str, Any]],
            load_json_input(request.snapshot.inputs, "resolved_mentions_json", default=[]),
        )
        mentioned_target_outputs = cast(
            list[dict[str, Any]],
            load_json_input(
                request.snapshot.inputs,
                "mentioned_target_outputs_json",
                default=[],
            ),
        )
        cycle_market_data = cast(
            dict[str, Any],
            load_json_input(request.snapshot.inputs, "cycle_market_data_json", default={}),
        )
        available_reports = cast(
            dict[str, Any],
            load_json_input(request.snapshot.inputs, "available_reports_json", default={}),
        )
        orchestration_catalog = cast(
            dict[str, Any],
            load_json_input(request.snapshot.inputs, "orchestration_catalog_json", default={}),
        )

        execution_mode = str(workflow.execution_mode or "structured_output")
        capability_inputs = BacktestLangGraphCapabilityInputs(
            tool_ids=tuple(tool.tool_id for tool in request.snapshot.resolved_tool_versions),
            bundle_keys=tuple(
                bundle.bundle_key for bundle in request.snapshot.resolved_bundle_versions
            ),
            connector_ids=tuple(
                connector.connector_id for connector in request.snapshot.resolved_connector_versions
            ),
        )
        if execution_mode == "tool_enabled":
            self._validate_resume_checkpoint(request)
            pending_connector = self._first_pending_connector(request)
            if pending_connector is not None:
                return build_waiting_approval_result(
                    request,
                    adapter_key=_ADAPTER_KEY,
                    step_key=_APPROVAL_STEP_KEY,
                    capability_key=pending_connector,
                    capability_index=self._connector_index(
                        capability_inputs.connector_ids, pending_connector
                    ),
                    trace_events=(
                        ExecutionAdapterTraceEvent(
                            event_type="STEP_STARTED",
                            step_key=_APPROVAL_STEP_KEY,
                            payload={
                                "workflowSpecKey": request.snapshot.workflow_spec_key,
                                "workflowSpecVersion": request.snapshot.workflow_spec_version,
                            },
                        ),
                    ),
                    extra_state={
                        "workflow_spec_key": request.snapshot.workflow_spec_key,
                        "workflow_spec_version": request.snapshot.workflow_spec_version,
                    },
                )

        tool_runtime = self._build_tool_runtime(
            request=request,
            prompt_report_slug=prompt_report_slug,
            prompt_report=prompt_report,
            authored_entry_prompt_body=authored_entry_prompt_body,
            compiled_entry_prompt_body=compiled_entry_prompt_body,
            execution_context_body=execution_context_body,
            full_user_prompt=full_user_prompt,
            resolved_mentions=resolved_mentions,
            mentioned_target_outputs=mentioned_target_outputs,
            cycle_market_data=cycle_market_data,
            available_reports=available_reports,
            orchestration_catalog=orchestration_catalog,
        )
        runner = self.runner_factory(workflow.key)
        step_key = self._execution_step_key(request)
        trace_events = [
            ExecutionAdapterTraceEvent(
                event_type="STEP_STARTED",
                step_key=step_key,
                payload={
                    "workflowSpecKey": workflow.key,
                    "workflowSpecVersion": workflow.version,
                },
            )
        ]
        result = runner.run_cycle(
            BacktestLangGraphRequest(
                backtest_id=cast(int, request.caller_id),
                cycle_date=cycle_date,
                prompt_report_slug=prompt_report_slug,
                prompt_report=prompt_report,
                authored_entry_prompt_body=authored_entry_prompt_body,
                compiled_entry_prompt_body=compiled_entry_prompt_body,
                execution_context_body=execution_context_body,
                full_user_prompt=full_user_prompt,
                resolved_mentions=tuple(resolved_mentions),
                orchestration_pattern_key=workflow.key,
                mentioned_target_outputs=tuple(
                    str(target.get("canonical_target_id", "")).strip()
                    for target in mentioned_target_outputs
                    if str(target.get("canonical_target_id", "")).strip()
                ),
                execution_mode=cast(Any, execution_mode),
                resolved_capability_inputs=capability_inputs,
                tool_runtime=tool_runtime,
            )
        )
        trace_events.extend(self._tool_trace_events(result.tool_call_trace))
        trace_events.append(
            ExecutionAdapterTraceEvent(
                event_type="STEP_COMPLETED",
                step_key=step_key,
                payload={
                    "workflowSpecKey": workflow.key,
                    "tradeDecisionCount": len(result.decisions),
                },
            )
        )
        normalized_trade_decisions = tuple(
            decision.model_dump(mode="json", by_alias=True) for decision in result.decisions
        )
        return ExecutionAdapterResult(
            status="SUCCEEDED",
            trace_events=tuple(trace_events),
            artifact_patch=ExecutionArtifactPatch(
                final_output={
                    "analysis_report": result.report_content,
                    "trade_decisions": list(normalized_trade_decisions),
                },
                report_markdown=result.report_content,
                normalized_trade_decisions=normalized_trade_decisions,
            ),
        )

    def _load_workflow(self, request: ExecutionAdapterRequest) -> Any:
        workflow_key = request.snapshot.workflow_spec_key
        workflow_version = request.snapshot.workflow_spec_version
        if workflow_key is None or workflow_version is None:
            raise business_rule_error(
                "runtime_backtest_adapter_missing_target",
                f"Run {request.run_id} is missing its pinned workflow target",
            )
        workflow = self.workflow_repository.get_by_key_version(workflow_key, workflow_version)
        if workflow is None:
            raise business_rule_error(
                "runtime_workflow_not_found",
                f"Workflow spec {workflow_key!r} v{workflow_version} was not found",
            )
        return workflow

    @staticmethod
    def _validate_frozen_plan(
        graph_definition: dict[str, Any], request: ExecutionAdapterRequest
    ) -> None:
        frozen_steps = tuple(request.snapshot.resolved_workflow_agent_refs)
        expected_steps = extract_graph_steps(graph_definition)
        if len(expected_steps) != len(frozen_steps):
            raise business_rule_error(
                "runtime_frozen_workflow_plan_drift",
                "Pinned backtest workflow metadata no longer matches the frozen step plan",
            )
        for frozen_step, expected_step in zip(frozen_steps, expected_steps, strict=True):
            if (
                expected_step["step_key"] != frozen_step.step_key
                or expected_step["agent_spec_key"] != frozen_step.agent_spec_key
            ):
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    "Pinned backtest workflow metadata no longer matches the frozen step plan",
                )
            raw_agent_version = expected_step.get("agent_spec_version")
            if (
                raw_agent_version is not None
                and raw_agent_version != frozen_step.agent_spec_version
            ):
                raise business_rule_error(
                    "runtime_frozen_workflow_plan_drift",
                    "Pinned backtest workflow metadata no longer matches the frozen step plan",
                )

    @staticmethod
    def _load_cycle_date(request: ExecutionAdapterRequest) -> date:
        if request.caller_id is None or request.caller_scope_key is None:
            raise business_rule_error(
                "runtime_backtest_caller_context_missing",
                "Backtest runtime execution requires callerId and callerScopeKey",
            )
        try:
            return date.fromisoformat(request.caller_scope_key)
        except ValueError as exc:
            raise business_rule_error(
                "runtime_backtest_cycle_date_invalid",
                f"Backtest callerScopeKey {request.caller_scope_key!r} is not an ISO cycle date",
            ) from exc

    def _validate_resume_checkpoint(self, request: ExecutionAdapterRequest) -> None:
        if request.dispatch_mode != "resume":
            return
        state = load_checkpoint_state(request, adapter_key=_ADAPTER_KEY)
        capability_key = str(state.get("capability_key") or "").strip()
        if not capability_key:
            raise business_rule_error(
                "runtime_checkpoint_mismatch",
                f"Run {request.run_id} checkpoint is missing its gated capability key",
            )
        if not has_approved_capability(
            request,
            step_key=_APPROVAL_STEP_KEY,
            capability_key=capability_key,
        ):
            raise business_rule_error(
                "runtime_checkpoint_approval_not_approved",
                (
                    f"Run {request.run_id} cannot resume because capability {capability_key!r} "
                    "is still not approved"
                ),
            )

    @staticmethod
    def _first_pending_connector(request: ExecutionAdapterRequest) -> str | None:
        ordered_connectors = {
            connector.connector_id for connector in request.snapshot.resolved_connector_versions
        }
        for capability in request.snapshot.resolved_capabilities:
            if capability.capability_type != CapabilityType.CONNECTOR:
                continue
            if capability.capability_key not in ordered_connectors:
                continue
            if capability.approval_mode != ApprovalMode.REQUIRED:
                continue
            if has_approved_capability(
                request,
                step_key=_APPROVAL_STEP_KEY,
                capability_key=capability.capability_key,
            ):
                continue
            return capability.capability_key
        return None

    @staticmethod
    def _connector_index(connector_ids: tuple[str, ...], capability_key: str) -> int:
        for index, connector_id in enumerate(connector_ids):
            if connector_id == capability_key:
                return index
        return 0

    def _build_tool_runtime(
        self,
        *,
        request: ExecutionAdapterRequest,
        prompt_report_slug: str,
        prompt_report: str,
        authored_entry_prompt_body: str,
        compiled_entry_prompt_body: str,
        execution_context_body: str,
        full_user_prompt: str,
        resolved_mentions: list[dict[str, Any]],
        mentioned_target_outputs: list[dict[str, Any]],
        cycle_market_data: dict[str, Any],
        available_reports: dict[str, Any],
        orchestration_catalog: dict[str, Any],
    ) -> BacktestLangGraphToolRuntime:
        cycle_context_payload = {
            "prompt_report_slug": prompt_report_slug,
            "prompt_report": prompt_report,
            "authored_entry_prompt_body": authored_entry_prompt_body,
            "compiled_entry_prompt_body": compiled_entry_prompt_body,
            "execution_context_body": execution_context_body,
            "full_user_prompt": full_user_prompt,
            "resolved_mentions": resolved_mentions,
            "mentioned_target_outputs": mentioned_target_outputs,
            "mentioned_target_output_ids": [
                str(target.get("canonical_target_id", "")).strip()
                for target in mentioned_target_outputs
                if str(target.get("canonical_target_id", "")).strip()
            ],
        }
        approval_modes = {
            capability.capability_key: capability.approval_mode
            for capability in request.snapshot.resolved_capabilities
            if capability.capability_type == CapabilityType.CONNECTOR
        }
        connector_transports = {
            capability.capability_key: capability.transport or "mcp"
            for capability in request.snapshot.resolved_capabilities
            if capability.capability_type == CapabilityType.CONNECTOR
        }
        adapters: list[BacktestLangGraphToolAdapter] = []
        for tool_version in request.snapshot.resolved_tool_versions:
            if tool_version.tool_id == "ledger.report_lookup":
                adapters.append(
                    BacktestLangGraphToolAdapter(
                        tool_id=tool_version.tool_id,
                        description="Read frozen report content by slug.",
                        parameters_schema={
                            "type": "object",
                            "properties": {"slug": {"type": "string"}},
                            "required": ["slug"],
                            "additionalProperties": False,
                        },
                        invoke=partial(
                            self._invoke_report_lookup,
                            prompt_report=prompt_report,
                            prompt_report_slug=prompt_report_slug,
                            available_reports=available_reports,
                        ),
                    )
                )
                continue
            if tool_version.tool_id == "ledger.orchestration_catalog_lookup":
                adapters.append(
                    BacktestLangGraphToolAdapter(
                        tool_id=tool_version.tool_id,
                        description="Read frozen orchestration catalog data.",
                        parameters_schema={
                            "type": "object",
                            "properties": {"handle": {"type": "string"}},
                            "additionalProperties": False,
                        },
                        invoke=partial(
                            self._invoke_orchestration_catalog_lookup,
                            orchestration_catalog=orchestration_catalog,
                            resolved_mentions=resolved_mentions,
                        ),
                    )
                )
                continue
            if tool_version.tool_id == "ledger.cycle_context_lookup":
                adapters.append(
                    BacktestLangGraphToolAdapter(
                        tool_id=tool_version.tool_id,
                        description="Read frozen cycle context artifacts.",
                        parameters_schema={
                            "type": "object",
                            "properties": {"artifact_key": {"type": "string"}},
                            "required": ["artifact_key"],
                            "additionalProperties": False,
                        },
                        invoke=partial(
                            self._invoke_cycle_context_lookup,
                            cycle_context_payload=cycle_context_payload,
                        ),
                    )
                )
                continue
            raise business_rule_error(
                "runtime_backtest_tool_not_supported",
                f"Backtest adapter does not support tool {tool_version.tool_id!r}",
            )

        for connector_version in request.snapshot.resolved_connector_versions:
            approval_required = (
                approval_modes.get(connector_version.connector_id) == ApprovalMode.REQUIRED
            )
            if connector_version.connector_id == "ledger.mcp.market_data":
                adapters.append(
                    BacktestLangGraphToolAdapter(
                        tool_id=connector_version.connector_id,
                        description="Read frozen market data connector output.",
                        parameters_schema={
                            "type": "object",
                            "properties": {"symbol": {"type": "string"}},
                            "required": ["symbol"],
                            "additionalProperties": False,
                        },
                        invoke=partial(
                            self._invoke_market_data_connector,
                            cycle_market_data=cycle_market_data,
                        ),
                        approval_required=approval_required,
                        approval_granted=True,
                        approval_metadata={
                            "kind": "connector",
                            "transport": connector_transports.get(
                                connector_version.connector_id,
                                "mcp",
                            ),
                        },
                    )
                )
                continue
            if connector_version.connector_id == "ledger.mcp.company_filings":
                adapters.append(
                    BacktestLangGraphToolAdapter(
                        tool_id=connector_version.connector_id,
                        description="Read frozen company filings connector output.",
                        parameters_schema={
                            "type": "object",
                            "properties": {"symbol": {"type": "string"}},
                            "required": ["symbol"],
                            "additionalProperties": False,
                        },
                        invoke=partial(
                            self._invoke_company_filings_connector,
                            prompt_report_slug=prompt_report_slug,
                        ),
                        approval_required=approval_required,
                        approval_granted=True,
                        approval_metadata={
                            "kind": "connector",
                            "transport": connector_transports.get(
                                connector_version.connector_id,
                                "mcp",
                            ),
                        },
                    )
                )
                continue
            raise business_rule_error(
                "runtime_backtest_connector_not_supported",
                (f"Backtest adapter does not support connector {connector_version.connector_id!r}"),
            )

        return BacktestLangGraphToolRuntime(adapters=tuple(adapters))

    @staticmethod
    def _invoke_report_lookup(
        arguments: dict[str, Any],
        *,
        prompt_report: str,
        prompt_report_slug: str,
        available_reports: dict[str, Any],
    ) -> dict[str, Any]:
        slug = str(arguments.get("slug", "")).strip()
        if not slug:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                "Frozen report lookup requires a non-empty slug",
            )
        if slug == prompt_report_slug:
            return {"slug": slug, "content": prompt_report}
        report_payload = available_reports.get(slug)
        if isinstance(report_payload, dict):
            return dict(report_payload)
        raise business_rule_error(
            "runtime_backtest_report_not_available",
            f"Frozen backtest artifact does not include report {slug!r}",
        )

    @staticmethod
    def _invoke_orchestration_catalog_lookup(
        arguments: dict[str, Any],
        *,
        orchestration_catalog: dict[str, Any],
        resolved_mentions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if orchestration_catalog:
            catalog = dict(orchestration_catalog)
        else:
            catalog = {"targets": list(resolved_mentions)}
        handle_value = arguments.get("handle")
        if handle_value is None:
            return catalog
        handle = str(handle_value).strip().lower()
        if not handle:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                "Frozen orchestration catalog lookup handle must be non-empty when provided",
            )
        targets = catalog.get("targets", [])
        if isinstance(targets, list):
            for target in targets:
                if not isinstance(target, dict):
                    continue
                if str(target.get("handle", "")).strip().lower() == handle:
                    return cast(dict[str, Any], target)
        raise business_rule_error(
            "runtime_backtest_target_not_available",
            f"Frozen backtest artifact does not include handle @{handle}",
        )

    @staticmethod
    def _invoke_cycle_context_lookup(
        arguments: dict[str, Any],
        *,
        cycle_context_payload: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_key = str(arguments.get("artifact_key", "")).strip()
        if artifact_key not in cycle_context_payload:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                f"Frozen cycle context artifact {artifact_key!r} is unavailable",
            )
        return {"artifact_key": artifact_key, "value": cycle_context_payload[artifact_key]}

    @staticmethod
    def _invoke_market_data_connector(
        arguments: dict[str, Any],
        *,
        cycle_market_data: dict[str, Any],
    ) -> dict[str, Any]:
        symbol = normalize_symbol(str(arguments.get("symbol", "")).strip())
        if not symbol:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                "Frozen market-data connector requires a non-empty symbol",
            )
        payload = cycle_market_data.get(symbol)
        if not isinstance(payload, dict):
            raise business_rule_error(
                "runtime_backtest_market_data_not_available",
                f"Frozen market data is unavailable for symbol {symbol!r}",
            )
        return {
            "symbol": symbol,
            "market_data": {
                str(key): (str(value) if isinstance(value, Decimal) else value)
                for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
            },
        }

    @staticmethod
    def _invoke_company_filings_connector(
        arguments: dict[str, Any],
        *,
        prompt_report_slug: str,
    ) -> dict[str, Any]:
        symbol = normalize_symbol(str(arguments.get("symbol", "")).strip())
        if not symbol:
            raise business_rule_error(
                "runtime_backtest_input_invalid",
                "Frozen company-filings connector requires a non-empty symbol",
            )
        return {"symbol": symbol, "prompt_report_slug": prompt_report_slug, "filings": []}

    @staticmethod
    def _tool_trace_events(
        tool_call_trace: list[dict[str, Any]],
    ) -> list[ExecutionAdapterTraceEvent]:
        return [
            ExecutionAdapterTraceEvent(
                event_type="TOOL_CALLED",
                step_key=_APPROVAL_STEP_KEY,
                capability_key=str(entry.get("tool_id", "")).strip() or None,
                payload=dict(entry),
            )
            for entry in tool_call_trace
        ]

    @staticmethod
    def _execution_step_key(request: ExecutionAdapterRequest) -> str:
        if request.snapshot.resolved_workflow_agent_refs:
            return request.snapshot.resolved_workflow_agent_refs[0].step_key
        return "langgraph_cycle"

    @staticmethod
    def _build_runner(pattern_key: str) -> BacktestLangGraphRunner:
        settings = get_settings()
        analyzer = LiveBacktestSymbolAnalyzer(
            model=settings.backtest_agent_model,
            api_key=settings.backtest_agent_api_key,
            base_url=settings.backtest_agent_base_url,
            timeout_seconds=settings.backtest_agent_timeout_seconds,
            temperature=settings.backtest_agent_temperature,
            api_mode=cast(Any, settings.backtest_agent_api_mode),
        )
        return build_backtest_langgraph_runner(pattern_key=pattern_key, analyzer=analyzer)
