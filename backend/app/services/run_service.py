from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, cast

from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, business_rule_error, not_found_error, validation_error
from app.core.formatting import utcnow
from app.core.telemetry import (
    configure_logfire,
    create_logfire_span,
    format_current_span_id,
    format_current_trace_id,
)
from app.db.engine import get_session_factory
from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.report import ReportRepository
from app.repositories.run import RunRepository
from app.repositories.run_agent_invocation import RunAgentInvocationRepository
from app.repositories.run_step import RunStepRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.memory import MemoryArtifactRead
from app.schemas.memory_report import (
    AgentMemoryReportCreateMetadata,
    AgentMemoryTrustedCreateContext,
)
from app.schemas.run import (
    RunCreatedRead,
    RunListItemRead,
    RunListRead,
    RunMemoryArtifactRead,
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunStepReplayCreateRequest,
    RunStepReplayDraftRead,
    RunTargetKind,
)
from app.schemas.workflow import (
    WorkflowLaunchCreateRequest,
    WorkflowLaunchCreateResponse,
    WorkflowLaunchRead,
    WorkflowVersionListRead,
    WorkflowVersionRead,
)
from app.schemas.workflow_package import (
    WorkflowPackageLaunchCreateRequest,
    WorkflowPackageLaunchCreateResponse,
    WorkflowPackageLaunchRead,
)
from app.services.agent_execution_service import (
    AgentExecutionService,
    RunAgentInvocationResult,
    RunExecutionError,
    normalize_agent_invocation_result,
)
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanGraphMetadata,
    ExecutionPlanSource,
    ExecutionPlanStep,
    ExecutionPlanTarget,
    PackageLocalOutputSchemaSpec,
    PackageResolvedModelBinding,
    PackageRuntimeAgentSpec,
)
from app.services.execution_plan_builder import ExecutionPlanBuilder, ExecutionPlanBuilderError
from app.services.memory_service import MemoryService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    SchemaField,
    SchemaNode,
    SchemaObject,
    SchemaRef,
)
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)
from app.services.market_data_service import MarketDataService
from app.services.memory_follow_up_service import MemoryFollowUpService
from app.services.quote_provider import DeterministicQuoteProvider, QuoteProvider
from app.services.workflow_package_preflight import WorkflowPackagePreflightService

logger = logging.getLogger(__name__)

_RUN_STATUS_QUEUED = "queued"
_RUN_STATUS_RUNNING = "running"
_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class _RuntimeInvocationContext:
    run_id: int
    target_kind: str
    target_key: str
    target_version: int
    workflow_key: str | None = None


@dataclass(frozen=True)
class _PreparedWorkflowLaunch:
    workflow: Workflow
    plan: ExecutionPlan


@dataclass(frozen=True)
class _PreparedWorkflowPackageLaunch:
    package: WorkflowPackage
    package_version: WorkflowPackageVersion
    plan: ExecutionPlan


@dataclass
class _PreparedAgentInvocation:
    agent: Agent | PackageRuntimeAgentSpec
    output_model: type[BaseModel]
    resolved_input: dict[str, Any]
    invocation: RunAgentInvocation
    optional: bool
    step_index: int
    slot: str
    runtime_context: _RuntimeInvocationContext


_CURRENT_RUNTIME_INVOCATION_CONTEXT: ContextVar[_RuntimeInvocationContext | None] = ContextVar(
    "ledger_runtime_invocation_context",
    default=None,
)


class RunService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        quote_provider: QuoteProvider | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.quote_provider: QuoteProvider | None = quote_provider
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.report_repository = ReportRepository(session)
        self.run_repository = RunRepository(session)
        self.workflow_package_repository = WorkflowPackageRepository(session)
        self.run_step_repository = RunStepRepository(session)
        self.run_agent_invocation_repository = RunAgentInvocationRepository(session)
        self.execution_plan_builder = ExecutionPlanBuilder(session)
        self.agent_execution_service = AgentExecutionService(
            self.session_factory,
            quote_provider=quote_provider,
        )
        self.schema_compiler = OutputSchemaCompiler(self.output_schema_repository)
        self._stored_schema_node_cache: dict[tuple[str, int], SchemaNode] = {}

    def list_runs(
        self,
        *,
        target_kind: RunTargetKind | None = None,
        target_id: int | None = None,
        target_key: str | None = None,
        target_version: int | None = None,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
        workflow_package_key: str | None = None,
        workflow_package_id: int | None = None,
        model_connection_key: str | None = None,
        status_filter: RunStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> RunListRead:
        runs = self.run_repository.list_all(
            target_kind=target_kind.value if target_kind is not None else None,
            target_id=target_id,
            target_key=target_key,
            target_version=target_version,
            workflow_id=workflow_id,
            workflow_key=None,
            workflow_version=workflow_version,
            workflow_package_id=workflow_package_id,
            workflow_package_key=workflow_package_key,
            package_workflow_key=workflow_key,
            model_connection_key=model_connection_key,
            status=status_filter.value if status_filter is not None else None,
            limit=limit,
            offset=offset,
        )
        return RunListRead(items=[self._to_list_item(run) for run in runs])

    def get_run(self, run_id: int) -> RunRead:
        return self._to_read_model(self._get_run_or_raise(run_id))

    def delete_run(self, run_id: int) -> None:
        run = self.run_repository.get(run_id)
        if run is None:
            raise not_found_error("Run")
        try:
            _ = self.report_repository.delete_agent_memory_by_run_ids([run.id])
            self.run_repository.delete(run)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def delete_runs_for_target(
        self,
        *,
        target_kind: str,
        target_id: int,
        workflow_package_id: int | None = None,
    ) -> None:
        runs = self.run_repository.list_for_target_owner(
            target_kind=target_kind,
            target_id=target_id,
            workflow_package_id=workflow_package_id,
        )
        if not runs:
            return
        run_ids = [run.id for run in runs]
        try:
            _ = self.report_repository.delete_agent_memory_by_run_ids(run_ids)
            for run in runs:
                self.run_repository.delete(run)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def get_workflow_launch(
        self,
        workflow_id: int,
        *,
        version: int | None = None,
    ) -> WorkflowLaunchRead:
        prepared = self._prepare_workflow_launch(workflow_id, version=version)
        return self._to_workflow_launch_read(prepared)

    def list_workflow_versions(self, workflow_id: int) -> WorkflowVersionListRead:
        anchor = self.execution_plan_builder.workflow_repository.get(workflow_id)
        if anchor is None:
            raise not_found_error("Workflow")
        versions = self.execution_plan_builder.workflow_repository.list_versions(anchor.key)
        return WorkflowVersionListRead(
            items=[
                WorkflowVersionRead.model_validate(
                    {
                        "id": workflow.id,
                        "key": workflow.key,
                        "version": workflow.version,
                        "status": workflow.status,
                        "name": workflow.name,
                        "description": workflow.description,
                        "inputSchema": workflow.input_schema,
                        "createdAt": workflow.created_at,
                        "updatedAt": workflow.updated_at,
                    }
                )
                for workflow in versions
            ]
        )

    def create_workflow_launch(
        self,
        workflow_id: int,
        payload: WorkflowLaunchCreateRequest,
    ) -> WorkflowLaunchCreateResponse:
        prepared = self._prepare_workflow_launch(workflow_id, version=payload.version)
        created = self._create_run_from_plan(prepared.plan, payload.parameters)
        return WorkflowLaunchCreateResponse.model_validate(
            {
                "id": created.id,
                "status": created.status,
                "workflowId": created.target_id,
                "workflowKey": created.target_key,
                "workflowVersion": created.target_version,
                "createdAt": created.created_at,
            }
        )

    def get_workflow_package_launch(
        self,
        package_id: int,
        *,
        version: int | None = None,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        prepared = self._prepare_workflow_package_launch(
            package_id,
            version=version,
            workflow_key=workflow_key,
            require_api_key=False,
        )
        return self._to_workflow_package_launch_read(prepared)

    def create_workflow_package_launch(
        self,
        package_id: int,
        payload: WorkflowPackageLaunchCreateRequest,
    ) -> WorkflowPackageLaunchCreateResponse:
        prepared = self._prepare_workflow_package_launch(
            package_id,
            version=payload.version,
            workflow_key=payload.workflow_key,
            require_api_key=True,
        )
        created = self._create_run_from_plan(
            prepared.plan,
            payload.parameters,
            workflow_package_version=prepared.package_version,
        )
        return WorkflowPackageLaunchCreateResponse.model_validate(
            {
                "id": created.id,
                "status": created.status,
                "workflowPackageId": prepared.package.id,
                "workflowPackageKey": prepared.package.key,
                "workflowPackageVersion": prepared.package_version.version,
                "workflowKey": (
                    prepared.plan.package_workflow.key
                    if prepared.plan.package_workflow is not None
                    else prepared.package.key
                ),
                "createdAt": created.created_at,
            }
        )

    def create_target_run(
        self,
        target_kind: str,
        target_id: int,
        input_payload: dict[str, Any],
        *,
        version: int | None = None,
    ) -> RunCreatedRead:
        plan = self.execution_plan_builder.build_target_plan(
            target_kind, target_id, version=version
        )
        return self._create_run_from_plan(plan, input_payload)

    def _prepare_workflow_launch(
        self,
        workflow_id: int,
        *,
        version: int | None,
    ) -> _PreparedWorkflowLaunch:
        plan = self.execution_plan_builder.build_target_plan(
            "workflow",
            workflow_id,
            version=version,
        )
        workflow = self.execution_plan_builder.workflow_repository.get(plan.target.id)
        if workflow is None:
            raise not_found_error("Workflow")
        return _PreparedWorkflowLaunch(workflow=workflow, plan=plan)

    def _prepare_workflow_package_launch(
        self,
        package_id: int,
        *,
        version: int | None,
        workflow_key: str | None,
        require_api_key: bool,
    ) -> _PreparedWorkflowPackageLaunch:
        package, package_version = self._resolve_workflow_package_version(
            package_id,
            version=version,
        )
        selected_workflow_key = self._resolve_workflow_package_workflow_key(
            package_version,
            workflow_key,
        )
        preflight = WorkflowPackagePreflightService(self.session).run(
            package_version,
            workflow_key=selected_workflow_key,
            require_api_key=require_api_key,
        )
        if require_api_key and preflight.blocking_errors:
            raise validation_error(
                "Workflow package launch validation failed",
                preflight.blocking_errors,
            )
        try:
            package_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
                package_version.compiled_plan,
                selected_workflow_key,
                model_bindings=preflight.model_bindings,
                package_version=package_version.version,
            )
        except WorkflowPackageExecutionPlanError as exc:
            raise validation_error(
                "Workflow package launch validation failed",
                list(exc.details),
            ) from exc
        plan = replace(
            package_plan,
            target=ExecutionPlanTarget(
                kind="workflow_package",
                id=package.id,
                key=package.key,
                version=package_version.version,
            ),
        )
        return _PreparedWorkflowPackageLaunch(
            package=package,
            package_version=package_version,
            plan=plan,
        )

    def _resolve_workflow_package_version(
        self,
        package_id: int,
        *,
        version: int | None,
    ) -> tuple[WorkflowPackage, WorkflowPackageVersion]:
        package = self.workflow_package_repository.get(package_id)
        if package is None:
            raise not_found_error("Workflow package")
        package_version = (
            self.workflow_package_repository.get_latest_version(package.id)
            if version is None
            else self.workflow_package_repository.get_version(package.id, version)
        )
        if package_version is None:
            raise not_found_error("Workflow package version")
        return package, package_version

    def _resolve_workflow_package_version_for_run(
        self,
        run: Run,
    ) -> tuple[WorkflowPackage, WorkflowPackageVersion]:
        if run.workflow_package_id is None or run.workflow_package_version is None:
            raise self._package_artifact_unavailable_error(
                "Workflow package run is missing package version provenance"
            )
        package = self.workflow_package_repository.get(run.workflow_package_id)
        if package is None:
            raise self._package_artifact_unavailable_error(
                "Workflow package artifact is no longer available"
            )
        package_version = self.workflow_package_repository.get_version(
            package.id,
            run.workflow_package_version,
        )
        if package_version is None:
            raise self._package_artifact_unavailable_error(
                "Workflow package version artifact is no longer available"
            )
        if (
            run.workflow_package_version_id is not None
            and package_version.id != run.workflow_package_version_id
        ):
            raise self._package_artifact_unavailable_error(
                "Workflow package version artifact identity changed"
            )
        return package, package_version

    @staticmethod
    def _package_artifact_unavailable_error(message: str) -> ApiError:
        return business_rule_error(
            "workflow_package_run_artifact_unavailable",
            message,
            details=[{"field": "packageProvenance", "issue": message}],
        )

    @staticmethod
    def _resolve_workflow_package_workflow_key(
        package_version: WorkflowPackageVersion,
        workflow_key: str | None,
    ) -> str:
        workflows = [
            workflow
            for workflow in package_version.compiled_plan.get("workflows") or []
            if isinstance(workflow, dict)
        ]
        if not workflows:
            raise validation_error(
                "Workflow package launch validation failed",
                [{"field": "spec.workflows", "issue": "Package has no workflows"}],
            )
        selected_key = workflow_key or str(workflows[0].get("key"))
        if any(str(workflow.get("key")) == selected_key for workflow in workflows):
            return selected_key
        raise not_found_error("Workflow package workflow")

    def _resolve_workflow_package_model_bindings(
        self,
        package_version: WorkflowPackageVersion,
        *,
        require_api_key: bool,
    ) -> tuple[dict[str, PackageResolvedModelBinding], list[dict[str, Any]]]:
        model_service = ModelConnectionService(self.session)
        bindings: dict[str, PackageResolvedModelBinding] = {}
        errors: list[dict[str, Any]] = []
        agents = package_version.compiled_plan.get("agents") or []
        for index, raw_agent in enumerate(agents):
            if not isinstance(raw_agent, dict):
                continue
            key = str(raw_agent.get("modelConnection") or "")
            path = f"spec.agents[{index}].modelConnection"
            try:
                binding = model_service.resolve_package_model_connection_binding(
                    key,
                    path=path,
                    require_api_key=require_api_key,
                )
            except ApiError as exc:
                errors.extend(exc.details)
                continue
            bindings[key] = PackageResolvedModelBinding(
                key=binding.key,
                name=binding.name,
                connection_kind=binding.connection_kind,
                base_url=binding.base_url,
                model_id=binding.model_id,
                reasoning_effort=binding.reasoning_effort,
                api_style=binding.api_style,
                timeout_seconds=binding.timeout_seconds,
                has_api_key=binding.has_api_key,
            )
        return bindings, errors

    @staticmethod
    def _run_target_kind(plan: ExecutionPlan) -> str:
        if plan.target.kind == "workflow_package":
            return RunTargetKind.WORKFLOW_PACKAGE.value
        return plan.target.kind

    @staticmethod
    def _run_target_fk_identity(
        plan: ExecutionPlan,
        workflow_package_version: WorkflowPackageVersion | None,
    ) -> dict[str, int | None]:
        if plan.target.kind == "agent":
            return {
                "agent_id": plan.target.id,
                "target_workflow_id": None,
                "workflow_package_id": None,
                "workflow_package_version_id": None,
            }
        if plan.target.kind == "workflow":
            return {
                "agent_id": None,
                "target_workflow_id": plan.target.id,
                "workflow_package_id": None,
                "workflow_package_version_id": None,
            }
        assert workflow_package_version is not None
        return {
            "agent_id": None,
            "target_workflow_id": None,
            "workflow_package_id": workflow_package_version.package_id,
            "workflow_package_version_id": workflow_package_version.id,
        }

    def _create_run_from_plan(
        self,
        plan: ExecutionPlan,
        input_payload: dict[str, Any],
        *,
        workflow_package_version: WorkflowPackageVersion | None = None,
    ) -> RunCreatedRead:
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=input_payload,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        package_workflow_key = (
            plan.package_workflow.key if plan.package_workflow is not None else None
        )
        target_fk_identity = self._run_target_fk_identity(plan, workflow_package_version)
        run = Run(
            **target_fk_identity,
            target_kind=self._run_target_kind(plan),
            target_id=plan.target.id,
            target_key=plan.target.key,
            target_version=plan.target.version,
            workflow_package_key=(
                plan.target.key if workflow_package_version is not None else None
            ),
            workflow_package_version=(
                workflow_package_version.version if workflow_package_version is not None else None
            ),
            workflow_package_hash=(
                workflow_package_version.manifest_hash
                if workflow_package_version is not None
                else None
            ),
            workflow_package_workflow_key=package_workflow_key,
            input=validated_input,
            status=_RUN_STATUS_QUEUED,
            queued_at=utcnow(),
            started_at=None,
            resume_step_index=1,
            final_output=None,
            total_tokens=0,
            inherited_tokens=0,
            executed_tokens=0,
            trace_id=None,
            error=None,
            finished_at=None,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
            )
            if workflow_package_version is not None:
                workflow_package_version.launched_at = (
                    workflow_package_version.launched_at or utcnow()
                )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        self._dispatch_queue_worker()
        return self._to_created_read(run)

    def build_rerun_draft(self, source_run_id: int) -> RunRerunDraftRead:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind == RunTargetKind.WORKFLOW_PACKAGE.value:
            _ = self._build_plan_for_run(source_run)
        return RunRerunDraftRead.model_validate(
            {
                "sourceRunId": source_run.id,
                "targetKind": source_run.target_kind,
                "targetId": source_run.target_id,
                "targetKey": source_run.target_key,
                "targetVersion": source_run.target_version,
                "parameters": deepcopy(source_run.input),
                "packageProvenance": self._package_provenance_payload(source_run),
            }
        )

    def create_rerun(
        self,
        source_run_id: int,
        payload: RunRerunCreateRequest,
    ) -> RunCreatedRead:
        source_run = self._get_run_or_raise(source_run_id)
        plan = self._build_plan_for_run(source_run)
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=payload.parameters,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        return self._create_queued_lineage_run(
            source_run=source_run,
            plan=plan,
            validated_input=validated_input,
            replay_step_index=None,
            copied_steps=[],
            resume_step_index=1,
            min_planned_step_index=1,
        )

    def build_step_replay_draft(
        self,
        source_run_id: int,
        replay_step_index: int,
    ) -> RunStepReplayDraftRead:
        source_run, _plan, _copied_steps = self._prepare_step_replay_source(
            source_run_id,
            replay_step_index,
        )
        return RunStepReplayDraftRead.model_validate(
            {
                "sourceRunId": source_run.id,
                "replayStepIndex": replay_step_index,
                "targetKind": source_run.target_kind,
                "targetId": source_run.target_id,
                "targetKey": source_run.target_key,
                "targetVersion": source_run.target_version,
                "parameters": deepcopy(source_run.input),
                "packageProvenance": self._package_provenance_payload(source_run),
            }
        )

    def create_step_replay(
        self,
        source_run_id: int,
        payload: RunStepReplayCreateRequest,
    ) -> RunCreatedRead:
        replay_step_index = payload.replay_step_index
        source_run, plan, copied_steps = self._prepare_step_replay_source(
            source_run_id,
            replay_step_index,
        )
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=payload.parameters,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        return self._create_queued_lineage_run(
            source_run=source_run,
            plan=plan,
            validated_input=validated_input,
            replay_step_index=replay_step_index,
            copied_steps=copied_steps,
            resume_step_index=replay_step_index,
            min_planned_step_index=replay_step_index,
        )

    def _create_queued_lineage_run(
        self,
        *,
        source_run: Run,
        plan: ExecutionPlan,
        validated_input: dict[str, Any],
        replay_step_index: int | None,
        copied_steps: list[RunStep],
        resume_step_index: int,
        min_planned_step_index: int,
    ) -> RunCreatedRead:
        inherited_tokens = self._copied_invocation_token_totals(copied_steps)
        run = Run(
            agent_id=source_run.agent_id,
            target_workflow_id=source_run.target_workflow_id,
            target_kind=source_run.target_kind,
            target_id=source_run.target_id,
            target_key=source_run.target_key,
            target_version=source_run.target_version,
            workflow_package_id=source_run.workflow_package_id,
            workflow_package_key=source_run.workflow_package_key,
            workflow_package_version_id=source_run.workflow_package_version_id,
            workflow_package_version=source_run.workflow_package_version,
            workflow_package_hash=source_run.workflow_package_hash,
            workflow_package_workflow_key=source_run.workflow_package_workflow_key,
            input=validated_input,
            status=_RUN_STATUS_QUEUED,
            queued_at=utcnow(),
            started_at=None,
            source_run_id=source_run.id,
            lineage_root_run_id=source_run.lineage_root_run_id or source_run.id,
            forked_from_step_index=replay_step_index,
            resume_step_index=resume_step_index,
            final_output=None,
            total_tokens=inherited_tokens,
            inherited_tokens=inherited_tokens,
            executed_tokens=0,
            trace_id=None,
            error=None,
            finished_at=None,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._copy_replay_context_rows(run=run, source_steps=copied_steps)
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
                min_step_index=min_planned_step_index,
            )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        self._dispatch_queue_worker()
        return self._to_created_read(run)

    def _create_planned_run_rows(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        validated_input: dict[str, Any],
        min_step_index: int = 1,
    ) -> None:
        plan_steps = [step for step in plan.steps if step.index >= min_step_index]
        planned_steps = self.run_step_repository.create_planned_steps(
            run_id=run.id,
            step_indexes=(step.index for step in plan_steps),
            graph_metadata_by_index=self._step_graph_metadata_payloads(plan_steps),
        )
        self.session.flush()
        steps_by_index = {step.step_index: step for step in planned_steps}
        for plan_step in plan_steps:
            run_step = steps_by_index[plan_step.index]
            for position, plan_agent in enumerate(plan_step.agents):
                resolved_input, resolved_input_origin = self._planned_resolved_input(
                    plan_agent=plan_agent,
                    validated_input=validated_input,
                )
                _ = self.run_agent_invocation_repository.create_invocation(
                    run_step_id=run_step.id,
                    run_id=run.id,
                    step_index=plan_step.index,
                    slot=plan_agent.slot,
                    position=position,
                    agent_id=plan_agent.agent_id,
                    agent_key=plan_agent.agent_key,
                    agent_version=plan_agent.agent_version,
                    output_schema_id=plan_agent.output_schema_id,
                    output_schema_version=plan_agent.output_schema_version,
                    input_mode=plan_agent.input_mode,
                    wiring={
                        target_name: self._plan_source_payload(source)
                        for target_name, source in plan_agent.wiring.items()
                    },
                    graph_metadata=self._graph_metadata_payload(plan_agent.graph_metadata),
                    optional=plan_agent.optional,
                    resolved_input=resolved_input,
                    resolved_input_origin=resolved_input_origin,
                )

    @classmethod
    def _step_graph_metadata_payloads(
        cls,
        plan_steps: list[ExecutionPlanStep],
    ) -> dict[int, dict[str, Any]]:
        payloads: dict[int, dict[str, Any]] = {}
        for step in plan_steps:
            payload = cls._graph_metadata_payload(step.graph_metadata)
            if payload is not None:
                payloads[step.index] = payload
        return payloads

    @staticmethod
    def _planned_resolved_input(
        *,
        plan_agent: ExecutionPlanAgent,
        validated_input: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if plan_agent.input_mode == "passthrough":
            return dict(validated_input), "passthrough"
        return {}, "derived"

    def _build_plan_for_run(self, run: Run) -> ExecutionPlan:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return self.execution_plan_builder.build_plan_for_run(run)
        package, package_version = self._resolve_workflow_package_version_for_run(run)
        del package
        workflow_key = run.workflow_package_workflow_key
        if workflow_key is None:
            raise ExecutionPlanBuilderError(
                code="run_workflow_package_workflow_missing",
                message="Workflow package run is missing workflow key provenance",
            )
        model_bindings, _binding_errors = self._resolve_workflow_package_model_bindings(
            package_version,
            require_api_key=False,
        )
        try:
            package_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
                package_version.compiled_plan,
                workflow_key,
                model_bindings=model_bindings,
                package_version=package_version.version,
            )
        except WorkflowPackageExecutionPlanError as exc:
            raise ExecutionPlanBuilderError(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ) from exc
        return replace(
            package_plan,
            target=ExecutionPlanTarget(
                kind="workflow_package",
                id=run.target_id,
                key=run.target_key,
                version=run.target_version,
            ),
        )

    def _prepare_step_replay_source(
        self,
        source_run_id: int,
        replay_step_index: int,
    ) -> tuple[Run, ExecutionPlan, list[RunStep]]:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind not in {"workflow", RunTargetKind.WORKFLOW_PACKAGE.value}:
            raise business_rule_error(
                "run_step_replay_target_kind_unsupported",
                "Step replay is only supported for workflow runs",
                details=[
                    {
                        "field": "targetKind",
                        "issue": "Step replay requires a workflow source run",
                    }
                ],
            )
        if source_run.status != _RUN_STATUS_SUCCEEDED:
            raise business_rule_error(
                "run_step_replay_source_not_succeeded",
                "Only succeeded runs can be replayed",
            )
        plan = self._build_plan_for_run(source_run)
        plan_step_indexes = {step.index for step in plan.steps}
        if replay_step_index not in plan_step_indexes:
            raise business_rule_error(
                "run_step_replay_step_not_found",
                f"Replay step {replay_step_index} does not exist on the source run plan",
            )

        source_steps_by_index = {
            step.step_index: step for step in cast(list[RunStep], source_run.steps)
        }
        replay_step = source_steps_by_index.get(replay_step_index)
        if replay_step is None:
            raise business_rule_error(
                "run_step_replay_step_not_found",
                f"Replay step {replay_step_index} does not exist on the source run",
            )
        if replay_step.status != _RUN_STATUS_SUCCEEDED or replay_step.persisted_at is None:
            raise business_rule_error(
                "run_step_replay_step_not_persisted",
                f"Replay step {replay_step_index} must be succeeded and persisted",
            )

        copied_steps: list[RunStep] = []
        for step_index in sorted(index for index in plan_step_indexes if index < replay_step_index):
            step = source_steps_by_index.get(step_index)
            if step is None or step.status != _RUN_STATUS_SUCCEEDED or step.persisted_at is None:
                raise business_rule_error(
                    "run_step_replay_context_not_persisted",
                    "All source context steps must be succeeded and persisted",
                    details=[{"field": f"steps.{step_index}", "issue": "Step is not persisted"}],
                )
            invocations = cast(list[RunAgentInvocation], step.invocations)
            for invocation in invocations:
                if not self._source_context_invocation_is_persisted(invocation):
                    raise business_rule_error(
                        "run_step_replay_context_output_not_persisted",
                        "All source context invocation outputs must be succeeded and persisted",
                        details=[
                            {
                                "field": f"steps.{step_index}.{invocation.slot}",
                                "issue": "Invocation output is not persisted",
                            }
                        ],
                    )
            copied_steps.append(step)
        return source_run, plan, copied_steps

    @staticmethod
    def _source_context_invocation_is_persisted(invocation: RunAgentInvocation) -> bool:
        if invocation.persisted_at is None:
            return False
        if invocation.status == _RUN_STATUS_SUCCEEDED:
            return invocation.output_origin is not None
        return invocation.optional and invocation.status in {_RUN_STATUS_FAILED, "skipped"}

    @staticmethod
    def _copied_invocation_token_totals(source_steps: list[RunStep]) -> int:
        tokens = 0
        for step in source_steps:
            for invocation in cast(list[RunAgentInvocation], step.invocations):
                tokens += int(invocation.tokens or 0)
        return tokens

    def _copy_replay_context_rows(
        self,
        *,
        run: Run,
        source_steps: list[RunStep],
    ) -> None:
        copied_at = utcnow()
        copied_steps: dict[int, RunStep] = {}
        for source_step in source_steps:
            copied_step = RunStep(
                run_id=run.id,
                step_index=source_step.step_index,
                status=source_step.status,
                origin="copied",
                source_run_step_id=source_step.id,
                source_run_id=source_step.run_id,
                source_step_index=source_step.step_index,
                graph_metadata=deepcopy(source_step.graph_metadata),
                error=source_step.error,
                started_at=source_step.started_at,
                finished_at=source_step.finished_at,
                persisted_at=copied_at,
            )
            self.session.add(copied_step)
            copied_steps[source_step.step_index] = copied_step
        self.session.flush()

        for source_step in source_steps:
            copied_step = copied_steps[source_step.step_index]
            for source_invocation in cast(list[RunAgentInvocation], source_step.invocations):
                copied_invocation = self.run_agent_invocation_repository.create_invocation(
                    run_step_id=copied_step.id,
                    run_id=run.id,
                    step_index=source_invocation.step_index,
                    slot=source_invocation.slot,
                    position=source_invocation.position,
                    agent_id=source_invocation.agent_id,
                    agent_key=source_invocation.agent_key,
                    agent_version=source_invocation.agent_version,
                    output_schema_id=source_invocation.output_schema_id,
                    output_schema_version=source_invocation.output_schema_version,
                    input_mode=source_invocation.input_mode,
                    wiring=deepcopy(source_invocation.wiring),
                    graph_metadata=deepcopy(source_invocation.graph_metadata),
                    optional=source_invocation.optional,
                    resolved_input=deepcopy(source_invocation.resolved_input),
                    resolved_input_origin="copied",
                    status=source_invocation.status,
                    output=deepcopy(source_invocation.output),
                    output_origin=(
                        "copied" if source_invocation.output_origin is not None else None
                    ),
                    source_invocation_id=source_invocation.id,
                )
                copied_invocation.error_code = source_invocation.error_code
                copied_invocation.error_message = source_invocation.error_message
                copied_invocation.error_details = deepcopy(source_invocation.error_details)
                copied_invocation.tokens = source_invocation.tokens
                copied_invocation.duration_ms = source_invocation.duration_ms
                copied_invocation.trace_span_id = source_invocation.trace_span_id
                copied_invocation.started_at = source_invocation.started_at
                copied_invocation.finished_at = source_invocation.finished_at
                copied_invocation.persisted_at = copied_at

    def execute_run(self, run_id: int) -> None:
        try:
            claimed_run = self.run_repository.claim_next_queued(run_id=run_id)
            if claimed_run is None:
                self.session.rollback()
                return
            claimed_run_id = claimed_run.id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.execute_claimed_run(claimed_run_id)

    def execute_claimed_run(self, run_id: int) -> None:
        try:
            asyncio.run(self._execute_claimed_run_async(run_id))
        except Exception as exc:
            logger.exception("Agent platform run %d failed", run_id)
            self.session.rollback()
            failure = self._coerce_execution_error(exc)
            self._mark_run_failed_in_fresh_session(
                run_id,
                code=failure.code,
                message=failure.message,
            )

    async def _execute_claimed_run_async(self, run_id: int) -> None:
        run = self._get_run_or_raise(run_id)
        if run.status != _RUN_STATUS_RUNNING:
            return
        if run.started_at is None:
            started_at = utcnow()
            run.started_at = started_at
            self.session.commit()
            self._run_workflow_package_start_follow_up(run, now=started_at)
        plan = self._build_plan_for_run(run)
        try:
            trace_session = self._start_trace_session(run=run, plan=plan)
        except Exception:
            await self._execute_run_with_trace(run=run, plan=plan, trace_id=None)
            return

        with trace_session as run_span:
            trace_id = format_current_trace_id(run_span)
            await self._execute_run_with_trace(run=run, plan=plan, trace_id=trace_id)

    async def _execute_run_with_trace(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        trace_id: str | None,
    ) -> None:
        total_tokens = int(run.inherited_tokens or 0)
        executed_tokens = 0

        for step in plan.steps:
            if step.index < run.resume_step_index:
                continue
            slot_outputs = self._hydrate_slot_outputs(run.id, before_step_index=step.index)
            run_step = self._get_planned_step_or_raise(run_id=run.id, step_index=step.index)
            self._assert_planned_invocations_exist(run_id=run.id, step=step)
            _ = self.run_step_repository.mark_running(run_step)
            self.session.commit()
            step_slot_outputs, step_tokens, fatal_error = await self._execute_step(
                run=run,
                plan=plan,
                step=step,
                initial_input=run.input,
                slot_outputs=slot_outputs,
                trace_id=trace_id,
            )
            if fatal_error is None:
                _ = self.run_step_repository.persist_success(run_step)
            else:
                _ = self.run_step_repository.persist_failure(run_step, error=fatal_error)
            executed_tokens += step_tokens
            total_tokens += step_tokens
            self._sync_run_totals(
                run,
                total_tokens=total_tokens,
                executed_tokens=executed_tokens,
            )
            self.session.commit()
            if fatal_error is not None:
                self._skip_pending_steps_after_failure(run_id=run.id, after_step_index=step.index)
                run.status = _RUN_STATUS_FAILED
                run.error = fatal_error
                run.finished_at = utcnow()
                self.session.commit()
                return
            for slot, value in step_slot_outputs.items():
                slot_outputs[(step.index, slot)] = value

        slot_outputs = self._hydrate_slot_outputs(run.id)
        final_output, final_error = self._resolve_final_output(
            plan=plan,
            slot_outputs=slot_outputs,
        )
        self._sync_run_totals(
            run,
            total_tokens=total_tokens,
            executed_tokens=executed_tokens,
        )
        if final_error is not None:
            run.status = _RUN_STATUS_FAILED
            run.error = final_error
            run.finished_at = utcnow()
            self.session.commit()
            return

        run.final_output = final_output
        run.status = _RUN_STATUS_SUCCEEDED
        run.trace_id = trace_id
        run.error = None
        run.finished_at = utcnow()
        self._create_post_run_memory_artifact(run.id)
        self.session.commit()

    def _run_workflow_package_start_follow_up(self, run: Run, *, now: datetime) -> None:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return
        quote_provider = self.quote_provider or DeterministicQuoteProvider()
        MemoryFollowUpService(
            self.session,
            MarketDataService(session=self.session, quote_provider=quote_provider),
        ).run_due(now)

    def _create_post_run_memory_artifact(self, run_id: int) -> None:
        run = self._get_run_or_raise(run_id)
        if run.status != _RUN_STATUS_SUCCEEDED or run.target_kind != "workflow":
            return
        policy = self._post_run_memory_policy(run)
        if policy is None:
            return
        source_refs = policy.get("sourceRefs")
        if not isinstance(source_refs, dict):
            return
        slot_outputs = self._hydrate_slot_outputs(run.id)
        payload = self._post_run_memory_payload(
            source_refs,
            benchmark_symbol_ref=policy.get("benchmarkSymbol"),
            initial_input=run.input,
            slot_outputs=slot_outputs,
        )
        context_ref = self._post_run_memory_context_ref(source_refs, policy)
        context_invocation = self._post_run_memory_context_invocation(context_ref, run_id=run.id)
        if context_invocation is None:
            return
        agent = self.agent_repository.get_by_key_version(
            context_invocation.agent_key,
            context_invocation.agent_version,
        )
        if agent is None:
            return
        trusted_context = AgentMemoryTrustedCreateContext(
            run_id=run.id,
            agent_key=context_invocation.agent_key,
            agent_version=context_invocation.agent_version,
            agent_name=agent.name,
            workflow_key=run.target_key,
            workflow_version=run.target_version,
            step_id=self._post_run_memory_context_node_id(context_ref, context_invocation),
            slot=self._post_run_memory_context_slot(context_ref, context_invocation),
            trace_id=run.trace_id,
        )
        memory_service = MemoryService(self.session)
        _ = memory_service.write_memory(
            capability_references=agent.capabilities,
            payload=memory_service.write_request_from_report_create(
                payload=payload,
                trusted_context=trusted_context,
            ),
            commit=False,
        )

    def _post_run_memory_policy(self, run: Run) -> dict[str, Any] | None:
        workflow = self.execution_plan_builder.workflow_repository.get_by_key_version(
            run.target_key,
            run.target_version,
        )
        if workflow is None:
            return None
        compiled_graph = workflow.output_spec.get("compiledGraph")
        if not isinstance(compiled_graph, dict):
            return None
        policy = compiled_graph.get("postRunMemory")
        if not isinstance(policy, dict) or policy.get("enabled") is not True:
            return None
        return cast(dict[str, Any], policy)

    def _post_run_memory_payload(
        self,
        source_refs: dict[Any, Any],
        *,
        benchmark_symbol_ref: Any | None = None,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> AgentMemoryReportCreateMetadata:
        analysis: dict[str, Any] = {
            "ticker": self._resolve_post_run_memory_ref(
                source_refs["ticker"],
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            ),
            "decision": {
                "action": self._resolve_post_run_memory_ref(
                    source_refs["action"],
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                ),
                "rationale": self._resolve_post_run_memory_ref(
                    source_refs["rationale"],
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                ),
                "riskSummary": self._resolve_post_run_memory_ref(
                    source_refs["riskSummary"],
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                ),
                "executionPlan": self._resolve_post_run_memory_ref(
                    source_refs["executionPlan"],
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                ),
            },
        }
        if benchmark_symbol_ref is not None:
            analysis["benchmarkSymbol"] = self._resolve_post_run_memory_ref(
                benchmark_symbol_ref,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
        for source_field, analysis_field in (
            ("portfolioSlug", "portfolioSlug"),
            ("horizonDays", "horizonDays"),
            ("confidence", "confidence"),
            ("decisionSummary", "decisionSummary"),
        ):
            reference = source_refs.get(source_field)
            if reference is not None:
                analysis[analysis_field] = self._resolve_post_run_memory_ref(
                    reference,
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                )
        return AgentMemoryReportCreateMetadata.model_validate({"analysis": analysis})

    def _resolve_post_run_memory_ref(
        self,
        reference: Any,
        *,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> Any:
        if not isinstance(reference, dict):
            raise RunExecutionError(
                code="post_run_memory_ref_invalid",
                message="postRunMemory compiled source reference is invalid",
            )
        source_kind = reference.get("source")
        if source_kind == "inputs":
            payload: dict[str, Any] = {"from": "input"}
            if reference.get("path") is not None:
                payload["path"] = reference["path"]
            value, _optional_null = self._resolve_source_value(
                payload,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            return value
        if source_kind == "nodes":
            payload = {
                "from": "step",
                "stepIndex": reference["stepIndex"],
                "slot": reference["compiledSlot"],
            }
            if reference.get("path") is not None:
                payload["path"] = reference["path"]
            value, optional_null = self._resolve_source_value(
                payload,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if optional_null:
                raise RunExecutionError(
                    code="post_run_memory_source_null",
                    message="postRunMemory source resolved to a null optional slot",
                )
            return value
        raise RunExecutionError(
            code="post_run_memory_ref_invalid",
            message="postRunMemory compiled source reference is invalid",
        )

    @staticmethod
    def _post_run_memory_context_ref(
        source_refs: dict[Any, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any] | None:
        for field_name in (
            "action",
            "rationale",
            "riskSummary",
            "executionPlan",
            "decisionSummary",
            "ticker",
        ):
            reference = source_refs.get(field_name)
            if isinstance(reference, dict) and reference.get("source") == "nodes":
                return cast(dict[str, Any], reference)
        benchmark_ref = policy.get("benchmarkSymbol")
        if isinstance(benchmark_ref, dict) and benchmark_ref.get("source") == "nodes":
            return cast(dict[str, Any], benchmark_ref)
        return None

    def _post_run_memory_context_invocation(
        self,
        context_ref: dict[str, Any] | None,
        *,
        run_id: int,
    ) -> RunAgentInvocation | None:
        if context_ref is None:
            return None
        step_index = context_ref.get("stepIndex")
        slot = context_ref.get("compiledSlot")
        if step_index is None or slot is None:
            return None
        return self.run_agent_invocation_repository.get_by_run_step_slot(
            run_id,
            int(step_index),
            str(slot),
        )

    @staticmethod
    def _post_run_memory_context_node_id(
        context_ref: dict[str, Any] | None,
        invocation: RunAgentInvocation,
    ) -> str | None:
        if context_ref is not None:
            node_id = context_ref.get("sourceNodeId") or context_ref.get("nodeId")
            if node_id is not None:
                return str(node_id)
        metadata = invocation.graph_metadata or {}
        node_id = metadata.get("nodeId")
        return None if node_id is None else str(node_id)

    @staticmethod
    def _post_run_memory_context_slot(
        context_ref: dict[str, Any] | None,
        invocation: RunAgentInvocation,
    ) -> str:
        if context_ref is not None:
            slot = context_ref.get("sourceSlot") or context_ref.get("compiledSlot")
            if slot is not None:
                return str(slot)
        return invocation.slot

    def _hydrate_slot_outputs(
        self,
        run_id: int,
        *,
        before_step_index: int | None = None,
    ) -> dict[tuple[int, str], Any]:
        slot_outputs = self.run_agent_invocation_repository.hydrate_successful_outputs(
            run_id,
            before_step_index=before_step_index,
        )
        for invocation in self.run_agent_invocation_repository.list_by_run(run_id):
            if before_step_index is not None and invocation.step_index >= before_step_index:
                continue
            if invocation.optional and invocation.status in {"failed", "skipped"}:
                slot_outputs[(invocation.step_index, invocation.slot)] = None
        return slot_outputs

    def _get_planned_step_or_raise(self, *, run_id: int, step_index: int) -> RunStep:
        run_step = self.run_step_repository.get_by_run_step_index(run_id, step_index)
        if run_step is None:
            raise RunExecutionError(
                code="run_planned_step_missing",
                message=f"Run {run_id} is missing planned step {step_index}",
            )
        return run_step

    def _get_planned_invocation_or_raise(
        self,
        *,
        run_id: int,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocation:
        invocation = self.run_agent_invocation_repository.get_by_run_step_slot(
            run_id,
            step_index,
            slot,
        )
        if invocation is None:
            raise RunExecutionError(
                code="run_planned_invocation_missing",
                message=f"Run {run_id} is missing planned invocation {step_index}.{slot}",
            )
        return invocation

    def _assert_planned_invocations_exist(self, *, run_id: int, step: ExecutionPlanStep) -> None:
        for plan_agent in step.agents:
            _ = self._get_planned_invocation_or_raise(
                run_id=run_id,
                step_index=step.index,
                slot=plan_agent.slot,
            )

    def _persist_failed_invocation(
        self,
        invocation: RunAgentInvocation,
        failure: RunExecutionError,
        *,
        tokens: int,
        duration_ms: int | None,
        trace_span_id: str | None,
    ) -> None:
        _ = self.run_agent_invocation_repository.persist_failure(
            invocation,
            error_code=failure.code,
            error_message=failure.message,
            error_details=list(failure.details),
            tokens=tokens,
            duration_ms=duration_ms,
            trace_span_id=trace_span_id,
        )

    def _skip_pending_steps_after_failure(self, *, run_id: int, after_step_index: int) -> None:
        for step in self.run_step_repository.list_by_run(run_id):
            if step.step_index <= after_step_index or step.status != "pending":
                continue
            _ = self.run_step_repository.persist_skipped(
                step,
                error="Run failed before this step started",
            )
            for invocation in self.run_agent_invocation_repository.list_by_run_step(
                run_id,
                step.step_index,
            ):
                if invocation.status == "pending":
                    _ = self.run_agent_invocation_repository.persist_skipped(
                        invocation,
                        error_code="run_step_skipped",
                        error_message="Run failed before this invocation started",
                    )

    @staticmethod
    def _runtime_resolved_input_origin(plan_agent: ExecutionPlanAgent) -> str:
        if plan_agent.input_mode == "passthrough":
            return "passthrough"
        return "derived"

    @staticmethod
    def _sync_run_totals(
        run: Run,
        *,
        total_tokens: int,
        executed_tokens: int,
    ) -> None:
        run.total_tokens = total_tokens
        run.executed_tokens = executed_tokens
        if run.source_run_id is None:
            run.inherited_tokens = 0
            run.total_tokens = executed_tokens

    def _resolve_final_output(
        self,
        *,
        plan: ExecutionPlan,
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any | None, str | None]:
        try:
            source_value, optional_null = self._resolve_final_output_value(
                plan.final_output,
                slot_outputs=slot_outputs,
            )
        except RunExecutionError as exc:
            return None, exc.message
        if optional_null:
            return None, "Final output cannot resolve from a null slot"
        return source_value, None

    async def _execute_step(
        self,
        *,
        run: Run,
        plan: ExecutionPlan,
        step: ExecutionPlanStep,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        trace_id: str | None,
    ) -> tuple[dict[str, Any], int, str | None]:
        step_index = step.index
        prepared_invocations: list[_PreparedAgentInvocation] = []
        step_slot_outputs: dict[str, Any] = {}
        fatal_error: str | None = None

        for plan_agent in step.agents:
            invocation = self._get_planned_invocation_or_raise(
                run_id=run.id,
                step_index=step_index,
                slot=plan_agent.slot,
            )
            prepared, failure = self._prepare_agent_invocation(
                runtime_context=_RuntimeInvocationContext(
                    run_id=run.id,
                    target_kind=self._run_target_kind(plan),
                    target_key=plan.target.key,
                    target_version=plan.target.version,
                    workflow_key=(
                        plan.package_workflow.key if plan.package_workflow is not None else None
                    ),
                ),
                step_index=step_index,
                plan_agent=plan_agent,
                invocation=invocation,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if prepared is None:
                assert failure is not None
                self._persist_failed_invocation(
                    invocation,
                    failure,
                    tokens=0,
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[plan_agent.slot] = None
                if not plan_agent.optional and fatal_error is None:
                    fatal_error = failure.message
                continue
            _ = self.run_agent_invocation_repository.mark_running(
                invocation,
                resolved_input=prepared.resolved_input,
                resolved_input_origin=self._runtime_resolved_input_origin(plan_agent),
            )
            prepared_invocations.append(prepared)

        self.session.commit()
        results = await asyncio.gather(
            *(
                self._execute_invocation(prepared, trace_id=trace_id)
                for prepared in prepared_invocations
            ),
            return_exceptions=True,
        )

        step_tokens = 0
        for index, prepared in enumerate(prepared_invocations):
            result = results[index]
            if isinstance(result, Exception):
                failure = self._coerce_execution_error(result)
                self._persist_failed_invocation(
                    prepared.invocation,
                    failure,
                    tokens=0,
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[prepared.slot] = None
                if not prepared.optional and fatal_error is None:
                    fatal_error = failure.message
                continue

            assert isinstance(result, RunAgentInvocationResult)
            step_tokens += result.tokens
            _ = self.run_agent_invocation_repository.persist_success(
                prepared.invocation,
                output=result.output,
                output_origin="executed",
                tokens=result.tokens,
                duration_ms=result.duration_ms,
                trace_span_id=result.trace_span_id,
            )
            step_slot_outputs[prepared.slot] = result.output

        return step_slot_outputs, step_tokens, fatal_error

    def _prepare_agent_invocation(
        self,
        *,
        runtime_context: _RuntimeInvocationContext,
        step_index: int,
        plan_agent: ExecutionPlanAgent,
        invocation: RunAgentInvocation,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[_PreparedAgentInvocation | None, RunExecutionError | None]:
        try:
            agent = self._resolve_runtime_agent(plan_agent)
            output_schema = self._resolve_runtime_agent_output_schema(agent)
            output_model = self.schema_compiler.build_runtime_model(output_schema)
            input_schema = self._runtime_agent_input_schema(agent)
            input_model = self._build_input_model(
                input_schema,
                candidate_key=f"{agent.key}_input",
            )
            input_node = self.schema_compiler.parse_json_schema_node(
                input_schema,
                path=f"steps[{step_index - 1}].{agent.key}.inputSchema",
            )
            resolved_input = self._resolve_agent_input(
                step_index=step_index,
                plan_agent=plan_agent,
                input_node=input_node,
                input_model=input_model,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            return (
                _PreparedAgentInvocation(
                    agent=agent,
                    output_model=output_model,
                    resolved_input=resolved_input,
                    invocation=invocation,
                    optional=plan_agent.optional,
                    step_index=step_index,
                    slot=plan_agent.slot,
                    runtime_context=runtime_context,
                ),
                None,
            )
        except RunExecutionError as exc:
            return None, exc
        except OutputSchemaCompilerError as exc:
            failure = RunExecutionError(
                code="agent_schema_build_failed",
                message=str(exc),
            )
            return None, failure

    def _resolve_agent_input(
        self,
        *,
        step_index: int,
        plan_agent: ExecutionPlanAgent,
        input_node: SchemaNode,
        input_model: type[BaseModel],
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> dict[str, Any]:
        if plan_agent.input_mode == "passthrough":
            try:
                validated = input_model.model_validate(initial_input)
            except ValidationError as exc:
                raise RunExecutionError(
                    code="agent_input_validation_failed",
                    message="Resolved agent input failed schema validation",
                    details=self._validation_details_from_pydantic_error(exc),
                ) from exc
            return validated.model_dump(mode="json", exclude_none=True)

        if plan_agent.input_mode != "wired":
            raise RunExecutionError(
                code="agent_input_mode_invalid",
                message=f"Unsupported plan input mode {plan_agent.input_mode!r}",
            )

        input_object = self._object_schema(input_node)
        target_fields = {field.name: field for field in input_object.fields}
        wiring = dict(plan_agent.wiring)
        agent_field_prefix = f"steps[{step_index - 1}].agents.{plan_agent.slot}.wiring"
        for target_name in wiring:
            if target_name not in target_fields and not input_object.allow_additional_properties:
                raise RunExecutionError(
                    code="agent_input_unknown_field",
                    message=f"Input field {target_name!r} is not defined on the agent schema",
                    details=[
                        {
                            "field": f"{agent_field_prefix}.{target_name}",
                            "issue": "Input field is not defined on the agent schema",
                        }
                    ],
                )

        payload: dict[str, Any] = {}
        for target_name, target_field in target_fields.items():
            source = wiring.get(target_name)
            if source is None:
                if target_field.required:
                    raise RunExecutionError(
                        code="agent_input_missing_required_field",
                        message=f"Required input field {target_name!r} is not wired",
                        details=[
                            {
                                "field": f"{agent_field_prefix}.{target_name}",
                                "issue": "Required input field is not wired",
                            }
                        ],
                    )
                continue

            value, optional_null = self._resolve_source_value(
                self._plan_source_payload(source),
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if optional_null:
                if target_field.required:
                    raise RunExecutionError(
                        code="agent_optional_source_required",
                        message="Optional slot failure left a required downstream field unresolved",
                        details=[
                            {
                                "field": f"{agent_field_prefix}.{target_name}",
                                "issue": (
                                    "Optional slot failure cannot satisfy a required input field"
                                ),
                            }
                        ],
                    )
                continue
            payload[target_name] = value

        if input_object.allow_additional_properties:
            for target_name, source in wiring.items():
                if target_name in target_fields:
                    continue
                value, optional_null = self._resolve_source_value(
                    self._plan_source_payload(source),
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                )
                if not optional_null:
                    payload[target_name] = value

        try:
            validated = input_model.model_validate(payload)
        except ValidationError as exc:
            raise RunExecutionError(
                code="agent_input_validation_failed",
                message="Resolved agent input failed schema validation",
                details=self._validation_details_from_pydantic_error(exc),
            ) from exc
        return validated.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _plan_source_payload(source: ExecutionPlanSource) -> dict[str, Any]:
        payload: dict[str, Any] = {"from": source.source}
        if source.path is not None:
            payload["path"] = source.path
        if source.step_index is not None:
            payload["stepIndex"] = source.step_index
        if source.slot is not None:
            payload["slot"] = source.slot
        return payload

    @staticmethod
    def _graph_metadata_payload(
        graph_metadata: ExecutionPlanGraphMetadata | None,
    ) -> dict[str, Any] | None:
        if graph_metadata is None:
            return None
        payload: dict[str, Any] = {}
        if graph_metadata.node_id is not None:
            payload["nodeId"] = graph_metadata.node_id
        if graph_metadata.node_kind is not None:
            payload["nodeKind"] = graph_metadata.node_kind
        if graph_metadata.graph_path is not None:
            payload["graphPath"] = graph_metadata.graph_path
        if graph_metadata.fanout_id is not None:
            payload["fanoutId"] = graph_metadata.fanout_id
        if graph_metadata.branch_id is not None:
            payload["branchId"] = graph_metadata.branch_id
        if graph_metadata.loop_id is not None:
            payload["loopId"] = graph_metadata.loop_id
        if graph_metadata.loop_iteration is not None:
            payload["loopIteration"] = graph_metadata.loop_iteration
        if graph_metadata.source_refs is not None:
            payload["sourceRefs"] = deepcopy(graph_metadata.source_refs)
        return payload or None

    def _resolve_final_output_value(
        self,
        final_output: ExecutionPlanFinalOutput,
        *,
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any, bool]:
        key = (final_output.step_index, final_output.slot)
        if key not in slot_outputs:
            raise RunExecutionError(
                code="run_source_slot_missing",
                message=(
                    f"Slot {final_output.slot!r} from step {final_output.step_index} "
                    "is not available"
                ),
                details=[
                    {
                        "field": f"step.{final_output.step_index}.{final_output.slot}",
                        "issue": "Referenced slot is not available in the current run state",
                    }
                ],
            )

        base_value = slot_outputs[key]
        if base_value is None:
            return None, True
        if final_output.path is None:
            return base_value, False
        return self._resolve_value_path(base_value, final_output.path), False

    def _resolve_source_value(
        self,
        source: dict[str, Any],
        *,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
    ) -> tuple[Any, bool]:
        source_kind = str(source.get("from", "")).strip().lower()
        path = source.get("path")
        if source_kind == "input":
            base_value = initial_input
        elif source_kind == "step":
            step_index = int(source["stepIndex"])
            slot = str(source["slot"])
            key = (step_index, slot)
            if key not in slot_outputs:
                raise RunExecutionError(
                    code="run_source_slot_missing",
                    message=f"Slot {slot!r} from step {step_index} is not available",
                    details=[
                        {
                            "field": f"step.{step_index}.{slot}",
                            "issue": "Referenced slot is not available in the current run state",
                        }
                    ],
                )
            base_value = slot_outputs[key]
            if base_value is None:
                return None, True
        else:
            raise RunExecutionError(
                code="run_source_kind_invalid",
                message=f"Unsupported workflow source kind {source_kind!r}",
            )

        if path is None:
            return base_value, False
        if base_value is None:
            return None, True
        return self._resolve_value_path(base_value, str(path)), False

    @staticmethod
    def _resolve_value_path(value: Any, path: str) -> Any:
        current = value
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                raise RunExecutionError(
                    code="run_source_path_invalid",
                    message=f"Resolved source path {path!r} is not available in the source payload",
                )
            current = current[segment]
        return current

    async def _execute_invocation(
        self,
        prepared: _PreparedAgentInvocation,
        *,
        trace_id: str | None,
    ) -> RunAgentInvocationResult:
        if trace_id is None:
            return await self._execute_invocation_with_trace_span(
                prepared,
                trace_id=trace_id,
                trace_span_id=None,
            )

        with create_logfire_span(
            "Run step {step_index} slot {slot} agent {agent_key}",
            step_index=prepared.step_index,
            slot=prepared.slot,
            agent_key=prepared.agent.key,
            run_trace_id=trace_id,
        ) as invocation_span:
            return await self._execute_invocation_with_trace_span(
                prepared,
                trace_id=trace_id,
                trace_span_id=format_current_span_id(invocation_span),
            )

    async def _execute_invocation_with_trace_span(
        self,
        prepared: _PreparedAgentInvocation,
        *,
        trace_id: str | None,
        trace_span_id: str | None,
    ) -> RunAgentInvocationResult:
        try:
            context_token = _CURRENT_RUNTIME_INVOCATION_CONTEXT.set(prepared.runtime_context)
            try:
                raw_result = await self._invoke_agent(
                    agent=prepared.agent,
                    resolved_input=prepared.resolved_input,
                    output_model=prepared.output_model,
                    trace_id=trace_id,
                    step_index=prepared.step_index,
                    slot=prepared.slot,
                )
            finally:
                _CURRENT_RUNTIME_INVOCATION_CONTEXT.reset(context_token)
            result = self._coerce_invocation_result(raw_result)
            validated_output = prepared.output_model.model_validate(result.output)
        except ValidationError as exc:
            raise RunExecutionError(
                code="agent_output_validation_failed",
                message="Agent output failed schema validation",
                details=self._validation_details_from_pydantic_error(exc),
                trace_span_id=trace_span_id,
            ) from exc
        except RunExecutionError as exc:
            if exc.trace_span_id is None:
                exc.trace_span_id = trace_span_id
            raise
        except Exception as exc:
            raise RunExecutionError(
                code="agent_execution_failed",
                message=str(exc),
                trace_span_id=trace_span_id,
            ) from exc
        return RunAgentInvocationResult(
            output=validated_output.model_dump(mode="json"),
            tokens=result.tokens,
            duration_ms=result.duration_ms,
            trace_span_id=trace_span_id,
        )

    async def _invoke_agent(
        self,
        *,
        agent: Agent | PackageRuntimeAgentSpec,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocationResult:
        runtime_context = _CURRENT_RUNTIME_INVOCATION_CONTEXT.get()
        workflow_key = None
        workflow_version = None
        if runtime_context is not None:
            if runtime_context.target_kind == "workflow":
                workflow_key = runtime_context.target_key
                workflow_version = runtime_context.target_version
            elif runtime_context.target_kind == RunTargetKind.WORKFLOW_PACKAGE.value:
                workflow_key = runtime_context.workflow_key
                workflow_version = runtime_context.target_version
        return await self.agent_execution_service.invoke(
            agent=agent,
            resolved_input=resolved_input,
            output_model=output_model,
            trace_id=trace_id,
            step_index=step_index,
            slot=slot,
            openai_client_factory=OpenAI,
            run_id=None if runtime_context is None else runtime_context.run_id,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
        )

    @staticmethod
    def _coerce_invocation_result(raw_result: Any) -> RunAgentInvocationResult:
        return normalize_agent_invocation_result(raw_result)

    @staticmethod
    def _apply_failed_entry(
        entry: dict[str, Any],
        failure: RunExecutionError,
        *,
        tokens: int,
        duration_ms: int | None,
        trace_span_id: str | None,
    ) -> None:
        entry["output"] = None
        entry["error"] = {
            "code": failure.code,
            "message": failure.message,
            "details": list(failure.details),
        }
        entry["status"] = _RUN_STATUS_FAILED
        entry["tokens"] = tokens
        entry["durationMs"] = duration_ms
        entry["traceSpanId"] = trace_span_id

    def _resolve_runtime_agent(
        self,
        plan_agent: ExecutionPlanAgent,
    ) -> Agent | PackageRuntimeAgentSpec:
        if plan_agent.package_runtime_agent is not None:
            return plan_agent.package_runtime_agent
        agent = self.agent_repository.get_by_key_version(
            plan_agent.agent_key,
            plan_agent.agent_version,
        )
        if agent is None:
            raise RunExecutionError(
                code="run_agent_missing",
                message=(
                    f"Agent {plan_agent.agent_key!r} version "
                    f"{plan_agent.agent_version} was not found"
                ),
            )
        return agent

    def _resolve_runtime_agent_output_schema(
        self,
        agent: Agent | PackageRuntimeAgentSpec,
    ) -> OutputSchema:
        if isinstance(agent, PackageRuntimeAgentSpec):
            return self._package_output_schema_candidate(agent.output_schema)
        output_schema = self.output_schema_repository.get(agent.output_schema_id)
        if output_schema is None or output_schema.version != agent.output_schema_version:
            raise RunExecutionError(
                code="run_output_schema_missing",
                message=f"Agent {agent.key!r} references a missing output schema version",
            )
        return output_schema

    @staticmethod
    def _runtime_agent_input_schema(agent: Agent | PackageRuntimeAgentSpec) -> dict[str, Any]:
        if isinstance(agent, PackageRuntimeAgentSpec):
            return agent.input_schema
        return agent.input_schema

    @staticmethod
    def _package_output_schema_candidate(
        output_schema: PackageLocalOutputSchemaSpec,
    ) -> OutputSchema:
        return OutputSchema(
            key=output_schema.key,
            version=1,
            status="published",
            kind="standalone",
            name=output_schema.name,
            description=output_schema.description,
            json_schema=output_schema.json_schema,
            registry_refs=[],
        )

    def _validate_run_input(
        self,
        *,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
        candidate_key: str,
        resource_name: str,
    ) -> dict[str, Any]:
        input_model = self._build_input_model(input_schema, candidate_key=candidate_key)
        try:
            validated = input_model.model_validate(input_payload)
        except ValidationError as exc:
            raise business_rule_error(
                "run_invalid_input",
                f"Run input failed {resource_name} input schema validation",
                details=self._validation_details_from_pydantic_error(exc),
            ) from exc
        return validated.model_dump(mode="json")

    def _build_input_model(
        self,
        input_schema: dict[str, Any],
        *,
        candidate_key: str,
    ) -> type[BaseModel]:
        candidate = OutputSchema(
            key=candidate_key,
            version=1,
            status="published",
            kind="standalone",
            name="Run Input Schema",
            description="Run input schema validation candidate",
            json_schema=input_schema,
            registry_refs=[],
        )
        return self.schema_compiler.build_runtime_model(candidate)

    def _object_field_map(self, node: SchemaNode) -> dict[str, SchemaField]:
        return {field.name: field for field in self._object_schema(node).fields}

    def _object_schema(self, node: SchemaNode) -> SchemaObject:
        dereferenced = self._dereference_node(node)
        if not isinstance(dereferenced, SchemaObject):
            raise RunExecutionError(
                code="agent_input_schema_invalid",
                message="Agent input schema must be an object schema",
            )
        return dereferenced

    def _dereference_node(self, node: SchemaNode) -> SchemaNode:
        current = node
        while isinstance(current, SchemaRef):
            cache_key = (current.key, current.version)
            cached = self._stored_schema_node_cache.get(cache_key)
            if cached is None:
                row = self.output_schema_repository.resolve_registry_ref(
                    current.key,
                    current.version,
                )
                if row is None:
                    raise RunExecutionError(
                        code="run_registry_ref_missing",
                        message=(
                            f"Shared registry ref {current.key!r} v{current.version} was not found"
                        ),
                    )
                cached = self.schema_compiler.parse_stored_schema_node(row)
                self._stored_schema_node_cache[cache_key] = cached
            current = cached
        return current

    def _dispatch_queue_worker(self) -> None:
        import importlib

        queue_module = importlib.import_module("app.services.run_queue_service")
        with self.session_factory() as session:
            queue_module.RunQueueService(
                session,
                self.session_factory,
                quote_provider=self.quote_provider,
            ).dispatch_pending()

    def _mark_run_failed_in_fresh_session(self, run_id: int, *, code: str, message: str) -> None:
        with self.session_factory() as session:
            service = RunService(session, self.session_factory, quote_provider=self.quote_provider)
            run = service.run_repository.get(run_id)
            if run is None or run.status not in {_RUN_STATUS_QUEUED, _RUN_STATUS_RUNNING}:
                return
            run.status = _RUN_STATUS_FAILED
            run.error = message
            run.finished_at = utcnow()
            session.commit()

    @staticmethod
    def _start_trace_session(*, run: Run, plan: ExecutionPlan) -> Any:
        configure_logfire()
        if plan.target.kind == "workflow":
            return create_logfire_span(
                "Workflow run {workflow_key} v{workflow_version} #{run_id}",
                workflow_id=plan.target.id,
                workflow_key=plan.target.key,
                workflow_version=plan.target.version,
                run_id=run.id,
                run_status=run.status,
            )
        if plan.target.kind == "workflow_package":
            return create_logfire_span(
                "Workflow package run {workflow_package_key} v{workflow_package_version} #{run_id}",
                workflow_package_id=plan.target.id,
                workflow_package_key=plan.target.key,
                workflow_package_version=plan.target.version,
                workflow_key=(
                    plan.package_workflow.key if plan.package_workflow is not None else None
                ),
                run_id=run.id,
                run_status=run.status,
            )
        return create_logfire_span(
            "Agent run {agent_key} v{agent_version} #{run_id}",
            agent_id=plan.target.id,
            agent_key=plan.target.key,
            agent_version=plan.target.version,
            run_id=run.id,
            run_status=run.status,
        )

    @staticmethod
    def _coerce_execution_error(exc: Exception) -> RunExecutionError:
        if isinstance(exc, RunExecutionError):
            return exc
        if isinstance(exc, ApiError):
            return RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details),
            )
        if isinstance(exc, ExecutionPlanBuilderError):
            return RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details),
            )
        return RunExecutionError(code="agent_execution_failed", message=str(exc))

    @staticmethod
    def _error_payload(error: RunExecutionError) -> dict[str, Any]:
        return {"code": error.code, "message": error.message, "details": list(error.details)}

    @staticmethod
    def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, str]]:
        details: list[dict[str, str]] = []
        for error in exc.errors():
            location = error.get("loc", ())
            field = ".".join(str(part) for part in location) if location else "input"
            details.append(
                {
                    "field": field or "input",
                    "issue": str(error.get("msg", "Invalid value")),
                }
            )
        return details

    def _get_run_or_raise(self, run_id: int) -> Run:
        run = self.run_repository.get_detail(run_id)
        if run is None:
            raise not_found_error("Run")
        return run

    @staticmethod
    def _build_step_entry(
        *,
        plan_agent: ExecutionPlanAgent,
        resolved_input: dict[str, Any],
        status: str = _RUN_STATUS_RUNNING,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "slot": plan_agent.slot,
            "agentId": plan_agent.agent_id,
            "agentKey": plan_agent.agent_key,
            "agentVersion": plan_agent.agent_version,
            "outputSchemaId": plan_agent.output_schema_id,
            "outputSchemaVersion": plan_agent.output_schema_version,
            "resolvedInput": resolved_input,
            "output": None,
            "error": error,
            "status": status,
            "tokens": 0,
            "durationMs": None,
            "traceSpanId": None,
        }

    @staticmethod
    def _to_workflow_launch_read(prepared: _PreparedWorkflowLaunch) -> WorkflowLaunchRead:
        return WorkflowLaunchRead.model_validate(
            {
                "workflowId": prepared.workflow.id,
                "key": prepared.workflow.key,
                "version": prepared.workflow.version,
                "name": prepared.workflow.name,
                "description": prepared.workflow.description,
                "inputSchema": prepared.plan.input_schema,
            }
        )

    def _to_workflow_package_launch_read(
        self,
        prepared: _PreparedWorkflowPackageLaunch,
    ) -> WorkflowPackageLaunchRead:
        preflight = WorkflowPackagePreflightService(self.session).run(
            prepared.package_version,
            workflow_key=(
                prepared.plan.package_workflow.key
                if prepared.plan.package_workflow is not None
                else prepared.package.key
            ),
            require_api_key=True,
        )
        package_workflow = prepared.plan.package_workflow
        if package_workflow is None:
            raise validation_error(
                "Workflow package launch validation failed",
                [{"field": "spec.workflows", "issue": "Package workflow plan is missing"}],
            )
        return WorkflowPackageLaunchRead.model_validate(
            {
                "packageId": prepared.package.id,
                "packageKey": prepared.package.key,
                "packageVersion": prepared.package_version.version,
                "manifestHash": prepared.package_version.manifest_hash,
                "workflowKey": package_workflow.key,
                "name": package_workflow.name,
                "description": package_workflow.description,
                "inputSchema": prepared.plan.input_schema,
                "ready": preflight.ready,
                "blockingErrors": preflight.blocking_errors,
                "warnings": preflight.warnings,
            }
        )

    @staticmethod
    def _to_created_read(run: Run) -> RunCreatedRead:
        return RunCreatedRead.model_validate(
            {
                "id": run.id,
                "status": run.status,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "traceId": run.trace_id,
                "createdAt": run.created_at,
            }
        )

    @staticmethod
    def _to_list_item(run: Run) -> RunListItemRead:
        return RunListItemRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "status": run.status,
                "totalTokens": run.total_tokens,
                "traceId": run.trace_id,
                "queuedAt": run.queued_at,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
            }
        )

    def _package_provenance_payload(self, run: Run) -> dict[str, Any] | None:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return None
        if (
            run.workflow_package_id is None
            or run.workflow_package_key is None
            or run.workflow_package_version is None
            or run.workflow_package_hash is None
            or run.workflow_package_workflow_key is None
        ):
            return None
        package = self.workflow_package_repository.get(run.workflow_package_id)
        package_version = self.workflow_package_repository.get_version(
            run.workflow_package_id,
            run.workflow_package_version,
        )
        selected_workflow = self._package_workflow_payload(
            package_version,
            run.workflow_package_workflow_key,
        )
        preflight_payload = None
        resolved_models: list[dict[str, Any]] = []
        if package_version is not None and selected_workflow is not None:
            preflight = WorkflowPackagePreflightService(self.session).run(
                package_version,
                workflow_key=run.workflow_package_workflow_key,
                require_api_key=False,
            )
            preflight_payload = {
                "ready": preflight.ready,
                "blockingErrors": preflight.blocking_errors,
                "warnings": preflight.warnings,
            }
            resolved_models = [
                self._model_binding_payload(binding)
                for binding in sorted(preflight.model_bindings.values(), key=lambda item: item.key)
            ]
        return {
            "workflowPackageId": run.workflow_package_id,
            "workflowPackageKey": run.workflow_package_key,
            "workflowPackageVersionId": run.workflow_package_version_id,
            "workflowPackageVersion": run.workflow_package_version,
            "workflowPackageHash": run.workflow_package_hash,
            "workflowKey": run.workflow_package_workflow_key,
            "launchSnapshot": self._package_launch_snapshot_payload(
                run,
                selected_workflow,
            ),
            "localResourceRefs": self._package_local_resource_refs(package_version),
            "resolvedModelConnections": resolved_models,
            "preflightSummary": preflight_payload,
            "availability": self._package_availability_payload(
                package,
                package_version,
                expected_version_id=run.workflow_package_version_id,
            ),
        }

    @staticmethod
    def _package_workflow_payload(
        package_version: WorkflowPackageVersion | None,
        workflow_key: str,
    ) -> dict[str, Any] | None:
        if package_version is None:
            return None
        workflows = package_version.compiled_plan.get("workflows") or []
        for workflow in workflows if isinstance(workflows, list) else []:
            if isinstance(workflow, dict) and str(workflow.get("key")) == workflow_key:
                return cast(dict[str, Any], workflow)
        return None

    @staticmethod
    def _package_launch_snapshot_payload(
        run: Run,
        workflow: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if workflow is None or run.workflow_package_workflow_key is None:
            return None
        return {
            "workflowKey": run.workflow_package_workflow_key,
            "workflowName": str(workflow.get("name") or run.workflow_package_workflow_key),
            "workflowDescription": str(workflow.get("description") or ""),
            "inputSchema": deepcopy(cast(dict[str, Any], workflow.get("inputSchema") or {})),
            "parameters": deepcopy(run.input),
        }

    @staticmethod
    def _package_local_resource_refs(
        package_version: WorkflowPackageVersion | None,
    ) -> dict[str, list[str]]:
        if package_version is None:
            return {
                "agents": [],
                "outputSchemas": [],
                "capabilityProfiles": [],
                "mcpServers": [],
                "workflows": [],
            }
        compiled_plan = package_version.compiled_plan
        return {
            "agents": RunService._compiled_keys(compiled_plan, "agents"),
            "outputSchemas": RunService._compiled_keys(compiled_plan, "outputSchemas"),
            "capabilityProfiles": RunService._compiled_keys(
                compiled_plan,
                "capabilityProfiles",
            ),
            "mcpServers": RunService._compiled_keys(compiled_plan, "mcpServers"),
            "workflows": RunService._compiled_keys(compiled_plan, "workflows"),
        }

    @staticmethod
    def _compiled_keys(compiled_plan: dict[str, Any], section: str) -> list[str]:
        raw_items = compiled_plan.get(section) or []
        if not isinstance(raw_items, list):
            return []
        return sorted(
            str(item["key"])
            for item in raw_items
            if isinstance(item, dict) and item.get("key") is not None
        )

    @staticmethod
    def _model_binding_payload(binding: PackageResolvedModelBinding) -> dict[str, Any]:
        return {
            "key": binding.key,
            "name": binding.name,
            "connectionKind": binding.connection_kind,
            "baseUrl": binding.base_url,
            "modelId": binding.model_id,
            "reasoningEffort": binding.reasoning_effort,
            "apiStyle": binding.api_style,
            "timeoutSeconds": binding.timeout_seconds,
            "hasApiKey": binding.has_api_key,
        }

    def _package_availability_payload(
        self,
        package: WorkflowPackage | None,
        package_version: WorkflowPackageVersion | None,
        *,
        expected_version_id: int | None,
    ) -> dict[str, Any]:
        unavailable_reason = self._package_unavailable_reason(
            package,
            package_version,
            expected_version_id=expected_version_id,
        )
        return {
            "packageStatus": None if package is None else package.status,
            "packageVersionAvailable": unavailable_reason is None,
            "unavailableReason": unavailable_reason,
        }

    @staticmethod
    def _package_unavailable_reason(
        package: WorkflowPackage | None,
        package_version: WorkflowPackageVersion | None,
        *,
        expected_version_id: int | None,
    ) -> str | None:
        if package is None:
            return "missingPackage"
        if package_version is None:
            return "missingPackageVersion"
        if expected_version_id is not None and package_version.id != expected_version_id:
            return "changedPackageVersionArtifact"
        return None

    def _to_read_model(self, run: Run) -> RunRead:
        return RunRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "targetVersion": run.target_version,
                "input": run.input,
                "sourceRunId": run.source_run_id,
                "lineageRootRunId": run.lineage_root_run_id,
                "replayStepIndex": run.forked_from_step_index,
                "resumeStepIndex": run.resume_step_index,
                "finalOutput": run.final_output,
                "status": run.status,
                "totalTokens": run.total_tokens,
                "inheritedTokens": run.inherited_tokens,
                "executedTokens": run.executed_tokens,
                "traceId": run.trace_id,
                "error": run.error,
                "queuedAt": run.queued_at,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
                "createdAt": run.created_at,
                "updatedAt": run.updated_at,
                "steps": [
                    RunService._to_step_read(step)
                    for step in sorted(
                        cast(list[RunStep], run.steps),
                        key=lambda item: (item.step_index, item.id),
                    )
                ],
                "memoryArtifacts": self._memory_artifact_links(run.id),
                "packageProvenance": self._package_provenance_payload(run),
            }
        )

    def _memory_artifact_links(self, run_id: int) -> list[RunMemoryArtifactRead]:
        return [
            self._memory_artifact_link(artifact)
            for artifact in MemoryService(self.session).list_run_artifacts(run_id)
        ]

    @staticmethod
    def _memory_artifact_link(artifact: MemoryArtifactRead) -> RunMemoryArtifactRead:
        return RunMemoryArtifactRead.model_validate(artifact)

    @staticmethod
    def _to_step_read(step: RunStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "runId": step.run_id,
            "index": step.step_index,
            "status": step.status,
            "origin": step.origin,
            "sourceRunStepId": step.source_run_step_id,
            "sourceRunId": step.source_run_id,
            "sourceStepIndex": step.source_step_index,
            "graphMetadata": deepcopy(step.graph_metadata),
            "error": step.error,
            "startedAt": step.started_at,
            "finishedAt": step.finished_at,
            "persistedAt": step.persisted_at,
            "createdAt": step.created_at,
            "updatedAt": step.updated_at,
            "invocations": [
                RunService._to_invocation_read(invocation)
                for invocation in sorted(
                    cast(list[RunAgentInvocation], step.invocations),
                    key=lambda item: (item.position, item.id),
                )
            ],
        }

    @staticmethod
    def _to_invocation_read(invocation: RunAgentInvocation) -> dict[str, Any]:
        return {
            "id": invocation.id,
            "runStepId": invocation.run_step_id,
            "runId": invocation.run_id,
            "stepIndex": invocation.step_index,
            "slot": invocation.slot,
            "position": invocation.position,
            "agentId": invocation.agent_id,
            "agentKey": invocation.agent_key,
            "agentVersion": invocation.agent_version,
            "outputSchemaId": invocation.output_schema_id,
            "outputSchemaVersion": invocation.output_schema_version,
            "inputMode": invocation.input_mode,
            "wiring": invocation.wiring,
            "graphMetadata": deepcopy(invocation.graph_metadata),
            "optional": invocation.optional,
            "status": invocation.status,
            "resolvedInput": invocation.resolved_input,
            "resolvedInputOrigin": invocation.resolved_input_origin,
            "output": invocation.output,
            "outputOrigin": invocation.output_origin,
            "errorCode": invocation.error_code,
            "errorMessage": invocation.error_message,
            "errorDetails": invocation.error_details,
            "tokens": invocation.tokens,
            "durationMs": invocation.duration_ms,
            "traceSpanId": invocation.trace_span_id,
            "sourceInvocationId": invocation.source_invocation_id,
            "startedAt": invocation.started_at,
            "finishedAt": invocation.finished_at,
            "persistedAt": invocation.persisted_at,
            "createdAt": invocation.created_at,
            "updatedAt": invocation.updated_at,
        }


__all__ = ["RunAgentInvocationResult", "RunExecutionError", "RunService"]
