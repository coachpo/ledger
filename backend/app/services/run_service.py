from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, cast

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
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackage
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.report import ReportRepository
from app.repositories.run import RunRepository
from app.repositories.run_agent_invocation import RunAgentInvocationRepository
from app.repositories.run_fork import RunForkRepository
from app.repositories.run_operation_invocation import RunOperationInvocationRepository
from app.repositories.run_step import RunStepRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.memory_report import (
    AgentMemoryReportCreateMetadata,
    AgentMemoryTrustedCreateContext,
)
from app.schemas.run import (
    RunCreatedRead,
    RunForkCreateRequest,
    RunForkDraftRead,
    RunListItemRead,
    RunListRead,
    RunProgressRead,
    RunQueueRead,
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunTargetKind,
)
from app.schemas.workflow import (
    WorkflowLaunchCreateRequest,
    WorkflowLaunchCreateResponse,
    WorkflowLaunchRead,
    WorkflowVersionListRead,
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
from app.services.execution_ownership import PackageExecutionOwnership
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanGraphMetadata,
    ExecutionPlanOperation,
    ExecutionPlanSource,
    ExecutionPlanStep,
    ExecutionPlanTarget,
    PackageLocalOutputSchemaSpec,
    PackageResolvedModelBinding,
    PackageRuntimeAgentSpec,
)
from app.services.execution_plan_builder import ExecutionPlanBuilder, ExecutionPlanBuilderError
from app.services.execution_providers import ExecutionProviderBundle
from app.services.extension_dependency_service import ExtensionDependencyService
from app.services.extension_service import ExtensionService
from app.services.http_operation_execution_service import (
    HttpOperationExecutionError,
    HttpOperationExecutionResult,
    HttpOperationExecutionService,
)
from app.services.legacy_authoring import raise_legacy_global_authoring_runtime_blocked
from app.services.memory_follow_up_service import MemoryFollowUpEvaluator, MemoryFollowUpService
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_openai import (
    DEFAULT_OPENAI_CLIENT_FACTORY as OpenAI,
)
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
from app.services.quote_provider import QuoteProvider
from app.services.run_lifecycle import WorkflowPackageStartContext
from app.services.run_read_projection import RunReadProjection
from app.services.run_rerun_fork import PreparedRunFork, RunRerunForkPreparation
from app.services.workflow_package_preflight import (
    WorkflowPackagePreflightResult,
    WorkflowPackagePreflightService,
)
from app.services.workflow_package_runtime_input_registry import (
    WorkflowPackageRuntimeInputRegistryService,
)

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
    workflow_version: int | None = None
    workflow_key: str | None = None
    package_ownership: PackageExecutionOwnership | None = None


@dataclass(frozen=True)
class _PreparedWorkflowLaunch:
    workflow: Workflow
    plan: ExecutionPlan


@dataclass(frozen=True)
class _PreparedWorkflowPackageLaunch:
    package: WorkflowPackage
    plan: ExecutionPlan
    preflight: WorkflowPackagePreflightResult


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


@dataclass
class _PreparedOperationInvocation:
    operation: ExecutionPlanOperation
    output_model: type[BaseModel]
    invocation: RunOperationInvocation
    optional: bool
    step_index: int
    slot: str
    package_ownership: PackageExecutionOwnership | None


_CURRENT_RUNTIME_INVOCATION_CONTEXT: ContextVar[_RuntimeInvocationContext | None] = ContextVar(
    "signaldeck_runtime_invocation_context",
    default=None,
)


class RunService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        quote_provider: QuoteProvider | None = None,
        provider_bundle: ExecutionProviderBundle | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or get_session_factory()
        self.provider_bundle: ExecutionProviderBundle = self._provider_bundle(
            provider_bundle=provider_bundle,
            quote_provider=quote_provider,
        )
        self.quote_provider: QuoteProvider | None = self.provider_bundle.quote_provider
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.report_repository = ReportRepository(session)
        self.run_repository = RunRepository(session)
        self.workflow_package_repository = WorkflowPackageRepository(session)
        self._run_read_projection = RunReadProjection(
            session=session,
            run_repository=self.run_repository,
            workflow_package_repository=self.workflow_package_repository,
            workflow_package_snapshot_for_run=self._workflow_package_snapshot_for_run,
        )
        self.run_step_repository = RunStepRepository(session)
        self.run_agent_invocation_repository = RunAgentInvocationRepository(session)
        self.run_fork_repository = RunForkRepository(session)
        self.run_operation_invocation_repository = RunOperationInvocationRepository(session)
        self.execution_plan_builder = ExecutionPlanBuilder(session)
        self.agent_execution_service = AgentExecutionService(
            self.session_factory,
            provider_bundle=self.provider_bundle,
            model_gateway=ModelExecutionGateway(client_factory=OpenAI),
        )
        self.http_operation_execution_service = HttpOperationExecutionService(session)
        self.schema_compiler = OutputSchemaCompiler(self.output_schema_repository)
        self._stored_schema_node_cache: dict[tuple[str, int], SchemaNode] = {}
        self._run_rerun_fork_preparation = RunRerunForkPreparation(
            session=session,
            run_repository=self.run_repository,
            run_agent_invocation_repository=self.run_agent_invocation_repository,
            run_operation_invocation_repository=self.run_operation_invocation_repository,
            schema_compiler=self.schema_compiler,
            read_projection=self._run_read_projection,
            workflow_package_snapshot_for_run=self._workflow_package_snapshot_for_run,
            resolve_runtime_agent=self._resolve_runtime_agent,
        )

    @staticmethod
    def _provider_bundle(
        *,
        provider_bundle: ExecutionProviderBundle | None,
        quote_provider: QuoteProvider | None,
    ) -> ExecutionProviderBundle:
        base_bundle = provider_bundle or ExecutionProviderBundle()
        if quote_provider is None:
            return base_bundle
        return replace(base_bundle, quote_provider=quote_provider)

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
        run_ids = [run.id for run in runs]
        progress_counts_by_run_id = self.run_repository.invocation_status_counts_by_run_id(run_ids)
        serial_blockers_by_run_id = self.run_repository.serial_queue_blocker_run_ids_by_run_id(
            run_ids
        )
        return RunListRead(
            items=[
                self._to_list_item(
                    run,
                    progress=self._run_read_projection.progress_from_status_counts(
                        progress_counts_by_run_id.get(run.id, {}),
                        run_status=run.status,
                    ),
                    queue=self._run_read_projection.queue_from_run(
                        run,
                        serial_blocker_run_id=serial_blockers_by_run_id.get(run.id),
                    ),
                )
                for run in runs
            ]
        )

    def get_run(self, run_id: int) -> RunRead:
        return self._run_read_projection.to_read_model(self._get_run_or_raise(run_id))

    def delete_run(self, run_id: int) -> None:
        run = self.run_repository.get(run_id)
        if run is None:
            raise not_found_error("Run")
        try:
            self._delete_run_rows([run])
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
        commit: bool = True,
    ) -> None:
        runs = self.run_repository.list_for_target_owner(
            target_kind=target_kind,
            target_id=target_id,
            workflow_package_id=workflow_package_id,
        )
        if not runs:
            return
        if not commit:
            self._delete_run_rows(runs)
            return
        try:
            self._delete_run_rows(runs)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _delete_run_rows(self, runs: list[Run]) -> None:
        run_ids = [run.id for run in runs]
        _ = self.report_repository.delete_agent_memory_by_run_ids(run_ids)
        for run in runs:
            self.run_repository.delete(run)

    def get_workflow_launch(
        self,
        workflow_id: int,
        *,
        version: int | None = None,
    ) -> WorkflowLaunchRead:
        del workflow_id, version
        raise_legacy_global_authoring_runtime_blocked("workflow")

    def list_workflow_versions(self, workflow_id: int) -> WorkflowVersionListRead:
        del workflow_id
        raise_legacy_global_authoring_runtime_blocked("workflow")

    def create_workflow_launch(
        self,
        workflow_id: int,
        payload: WorkflowLaunchCreateRequest,
    ) -> WorkflowLaunchCreateResponse:
        del workflow_id, payload
        raise_legacy_global_authoring_runtime_blocked("workflow")

    def get_workflow_package_launch(
        self,
        package_id: int,
        *,
        version: int | None = None,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        del version
        prepared = self._prepare_workflow_package_launch(
            package_id,
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
            workflow_key=payload.workflow_key,
            require_api_key=True,
        )
        created = self._create_run_from_plan(
            prepared.plan,
            payload.parameters,
            workflow_package=prepared.package,
            preflight=prepared.preflight,
        )
        return WorkflowPackageLaunchCreateResponse.model_validate(
            {
                "id": created.id,
                "status": created.status,
                "workflowPackageId": prepared.package.id,
                "workflowPackageKey": prepared.package.key,
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
        del target_id, input_payload, version
        raise_legacy_global_authoring_runtime_blocked(target_kind)

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
        workflow_key: str | None,
        require_api_key: bool,
    ) -> _PreparedWorkflowPackageLaunch:
        package = self._resolve_workflow_package(package_id)
        selected_workflow_key = self._resolve_workflow_package_workflow_key(
            package,
            workflow_key,
        )
        preflight = WorkflowPackagePreflightService(self.session).run(
            package,
            workflow_key=selected_workflow_key,
            require_api_key=require_api_key,
        )
        if require_api_key and preflight.blocking_errors:
            raise validation_error(
                "Workflow package launch validation failed",
                preflight.blocking_errors,
            )
        ownership = self._package_execution_ownership(
            package=package,
            workflow_key=selected_workflow_key,
        )
        try:
            package_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
                package.compiled_plan,
                selected_workflow_key,
                model_bindings=preflight.model_bindings,
                ownership=ownership,
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
                version=None,
            ),
        )
        return _PreparedWorkflowPackageLaunch(
            package=package,
            plan=plan,
            preflight=preflight,
        )

    def _resolve_workflow_package(self, package_id: int) -> WorkflowPackage:
        package = self.workflow_package_repository.get(package_id)
        if package is None:
            raise not_found_error("Workflow package")
        return package

    def _workflow_package_snapshot_for_run(self, run: Run) -> RunWorkflowPackageSnapshot:
        snapshot = run.workflow_package_snapshot
        if snapshot is None:
            raise self._package_artifact_unavailable_error(
                "Workflow package run is missing executable snapshot provenance"
            )
        return snapshot

    @staticmethod
    def _package_artifact_unavailable_error(message: str) -> ApiError:
        return business_rule_error(
            "workflow_package_run_artifact_unavailable",
            message,
            details=[{"field": "packageProvenance", "issue": message}],
        )

    @staticmethod
    def _package_execution_ownership(
        *,
        package: WorkflowPackage,
        workflow_key: str,
    ) -> PackageExecutionOwnership:
        return PackageExecutionOwnership(
            package_id=package.id,
            package_key=package.key,
            manifest_hash=package.manifest_hash,
            compiled_hash=package.compiled_hash,
            workflow_key=workflow_key,
        )

    @staticmethod
    def _package_execution_ownership_from_snapshot(
        snapshot: RunWorkflowPackageSnapshot,
    ) -> PackageExecutionOwnership:
        return PackageExecutionOwnership(
            package_id=snapshot.workflow_package_id,
            package_key=snapshot.workflow_package_key,
            manifest_hash=snapshot.manifest_hash,
            compiled_hash=snapshot.compiled_hash,
            workflow_key=snapshot.workflow_key,
        )

    @staticmethod
    def _resolve_workflow_package_workflow_key(
        package: WorkflowPackage,
        workflow_key: str | None,
    ) -> str:
        workflows = [
            workflow
            for workflow in package.compiled_plan.get("workflows") or []
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

    @staticmethod
    def _run_target_kind(plan: ExecutionPlan) -> str:
        if plan.target.kind == "workflow_package":
            return RunTargetKind.WORKFLOW_PACKAGE.value
        return plan.target.kind

    @staticmethod
    def _run_storage_target_version(plan: ExecutionPlan) -> int:
        if plan.target.version is not None:
            return plan.target.version
        if plan.target.kind == "workflow_package":
            return 1
        raise ValueError(f"Execution plan target {plan.target.kind!r} is missing a version")

    @staticmethod
    def _run_target_fk_identity(plan: ExecutionPlan) -> dict[str, int | None]:
        if plan.target.kind == "agent":
            return {
                "agent_id": plan.target.id,
                "target_workflow_id": None,
                "workflow_package_id": None,
            }
        if plan.target.kind == "workflow":
            return {
                "agent_id": None,
                "target_workflow_id": plan.target.id,
                "workflow_package_id": None,
            }
        return {
            "agent_id": None,
            "target_workflow_id": None,
            "workflow_package_id": plan.target.id,
        }

    @staticmethod
    def _extension_dependencies_for_package(
        workflow_package: WorkflowPackage | None,
    ) -> list[dict[str, Any]]:
        if workflow_package is None:
            return []
        return ExtensionDependencyService.normalize_dependency_payloads(
            workflow_package.extension_dependencies
        )

    def _workflow_package_snapshot_for_plan(
        self,
        *,
        plan: ExecutionPlan,
        workflow_package: WorkflowPackage | None,
        preflight: WorkflowPackagePreflightResult | None,
        validated_input: dict[str, Any],
    ) -> RunWorkflowPackageSnapshot | None:
        package_workflow = plan.package_workflow
        if workflow_package is None or preflight is None or package_workflow is None:
            return None
        return RunWorkflowPackageSnapshot(
            workflow_package_id=workflow_package.id,
            workflow_package_key=workflow_package.key,
            workflow_package_name=workflow_package.name,
            workflow_package_description=workflow_package.description,
            workflow_package_status=None,
            workflow_key=package_workflow.key,
            workflow_name=package_workflow.name,
            workflow_description=package_workflow.description,
            manifest_hash=workflow_package.manifest_hash,
            compiled_hash=workflow_package.compiled_hash,
            manifest_source=workflow_package.manifest_source,
            package_definition=deepcopy(workflow_package.package_definition),
            compiled_plan=deepcopy(workflow_package.compiled_plan),
            extension_dependencies=self._extension_dependencies_for_package(workflow_package),
            local_resource_refs=self._package_local_resource_refs(workflow_package.compiled_plan),
            input_schema=deepcopy(plan.input_schema),
            launch_parameters=deepcopy(validated_input),
            # Capture the live effective runtime profile only when the run is created.
            # Later rerun/fork provenance reads this frozen snapshot instead of rebinding.
            resolved_model_connections=[
                self._model_binding_payload(binding)
                for binding in sorted(preflight.model_bindings.values(), key=lambda item: item.key)
            ],
            preflight_summary=self._preflight_summary_payload(preflight),
        )

    def _assert_run_extension_dependencies_enabled(self, run: Run) -> None:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return
        dependencies = ExtensionDependencyService.normalize_dependency_payloads(
            run.extension_dependencies
        )
        if not dependencies:
            return
        extension_service = ExtensionService(self.session)
        for dependency in dependencies:
            extension_key = str(dependency.get("extensionKey") or "")
            if not extension_key:
                continue
            extension_service.require_enabled(
                extension_key,
                surface=self._preferred_extension_dependency_surface(
                    dependency,
                    fallback=f"workflowPackage.{run.target_key}",
                ),
            )

    @staticmethod
    def _preferred_extension_dependency_surface(
        dependency: dict[str, Any],
        *,
        fallback: str,
    ) -> str:
        surfaces = dependency.get("surfaces")
        if not isinstance(surfaces, list):
            return fallback
        for prefix in ("tool.", "runtime.tool.", "mcp.", "provider.", "hook."):
            for surface in surfaces:
                if isinstance(surface, str) and surface.startswith(prefix):
                    return surface
        return str(surfaces[0]) if surfaces else fallback

    @staticmethod
    def _run_extension_dependency_keys(run: Run) -> set[str]:
        return {
            str(dependency.get("extensionKey") or "")
            for dependency in ExtensionDependencyService.normalize_dependency_payloads(
                run.extension_dependencies
            )
            if str(dependency.get("extensionKey") or "")
        }

    def _create_run_from_plan(
        self,
        plan: ExecutionPlan,
        input_payload: dict[str, Any],
        *,
        workflow_package: WorkflowPackage | None = None,
        preflight: WorkflowPackagePreflightResult | None = None,
    ) -> RunCreatedRead:
        validated_input = self._validate_run_input(
            input_schema=plan.input_schema,
            input_payload=input_payload,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        package_ownership = plan.package_ownership
        package_workflow_key = (
            package_ownership.workflow_key if package_ownership is not None else None
        )
        target_fk_identity = self._run_target_fk_identity(plan)
        extension_dependencies = self._extension_dependencies_for_package(workflow_package)
        workflow_package_snapshot = self._workflow_package_snapshot_for_plan(
            plan=plan,
            workflow_package=workflow_package,
            preflight=preflight,
            validated_input=validated_input,
        )
        run = Run(
            **target_fk_identity,
            target_kind=self._run_target_kind(plan),
            target_id=plan.target.id,
            target_key=plan.target.key,
            target_version=self._run_storage_target_version(plan),
            workflow_package_key=(
                package_ownership.package_key if package_ownership is not None else None
            ),
            workflow_package_workflow_key=package_workflow_key,
            extension_dependencies=extension_dependencies,
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
        if workflow_package_snapshot is not None:
            run.workflow_package_snapshot = workflow_package_snapshot
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
            )
            if plan.target.kind == "workflow_package":
                if workflow_package is None or package_workflow_key is None:
                    raise ValueError(
                        "Workflow package launch history requires package and workflow context"
                    )
                _ = WorkflowPackageRuntimeInputRegistryService(
                    self.session
                ).append_history_entry_for_launch(
                    package_id=workflow_package.id,
                    workflow_key=package_workflow_key,
                    payload=validated_input,
                    source_run_id=run.id,
                )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        return self._to_created_read(run)

    def build_rerun_draft(self, source_run_id: int) -> RunRerunDraftRead:
        return self._run_rerun_fork_preparation.build_rerun_draft(source_run_id)

    def create_rerun(
        self,
        source_run_id: int,
        payload: RunRerunCreateRequest,
    ) -> RunCreatedRead:
        prepared = self._run_rerun_fork_preparation.prepare_rerun_create(
            source_run_id,
            payload,
        )
        return self._create_queued_rerun_run(
            source_run=prepared.source_run,
            plan=prepared.plan,
            validated_input=prepared.validated_input,
            preflight=prepared.readiness,
        )

    def build_fork_draft(
        self,
        source_run_id: int,
        source_invocation_id: int,
    ) -> RunForkDraftRead:
        return self._run_rerun_fork_preparation.build_fork_draft(
            source_run_id,
            source_invocation_id,
        )

    def create_fork(
        self,
        source_run_id: int,
        payload: RunForkCreateRequest,
    ) -> RunCreatedRead:
        prepared = self._run_rerun_fork_preparation.prepare_fork_create(
            source_run_id,
            payload,
        )
        return self._create_queued_fork_run(
            prepared=prepared.prepared_fork,
            invocation_input=prepared.invocation_input,
            preflight=prepared.readiness,
        )

    def _create_queued_rerun_run(
        self,
        *,
        source_run: Run,
        plan: ExecutionPlan,
        validated_input: dict[str, Any],
        preflight: WorkflowPackagePreflightResult,
    ) -> RunCreatedRead:
        run = Run(
            agent_id=source_run.agent_id,
            target_workflow_id=source_run.target_workflow_id,
            target_kind=source_run.target_kind,
            target_id=source_run.target_id,
            target_key=source_run.target_key,
            target_version=source_run.target_version,
            workflow_package_id=source_run.workflow_package_id,
            workflow_package_key=source_run.workflow_package_key,
            workflow_package_workflow_key=source_run.workflow_package_workflow_key,
            extension_dependencies=ExtensionDependencyService.normalize_dependency_payloads(
                source_run.extension_dependencies
            ),
            input=validated_input,
            status=_RUN_STATUS_QUEUED,
            queued_at=utcnow(),
            started_at=None,
            source_run_id=source_run.id,
            lineage_root_run_id=source_run.lineage_root_run_id or source_run.id,
            forked_from_step_index=None,
            resume_step_index=1,
            final_output=None,
            total_tokens=0,
            inherited_tokens=0,
            executed_tokens=0,
            trace_id=None,
            error=None,
            finished_at=None,
        )
        run.workflow_package_snapshot = self._lineage_workflow_package_snapshot(
            source_run=source_run,
            launch_parameters=validated_input,
            preflight=preflight,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._create_planned_run_rows(
                run=run,
                plan=plan,
                validated_input=validated_input,
            )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        return self._to_created_read(run)

    def _create_queued_fork_run(
        self,
        *,
        prepared: PreparedRunFork,
        invocation_input: dict[str, Any],
        preflight: WorkflowPackagePreflightResult,
    ) -> RunCreatedRead:
        source_run = prepared.source_run
        source_invocation = prepared.source_invocation
        resume_step_index = source_invocation.step_index
        inherited_tokens = self._run_rerun_fork_preparation.copied_invocation_token_totals(
            prepared.copied_steps
        )
        lineage_root_run_id = source_run.lineage_root_run_id or source_run.id
        run = Run(
            agent_id=source_run.agent_id,
            target_workflow_id=source_run.target_workflow_id,
            target_kind=source_run.target_kind,
            target_id=source_run.target_id,
            target_key=source_run.target_key,
            target_version=source_run.target_version,
            workflow_package_id=source_run.workflow_package_id,
            workflow_package_key=source_run.workflow_package_key,
            workflow_package_workflow_key=source_run.workflow_package_workflow_key,
            extension_dependencies=ExtensionDependencyService.normalize_dependency_payloads(
                source_run.extension_dependencies
            ),
            input=deepcopy(source_run.input),
            status=_RUN_STATUS_QUEUED,
            queued_at=utcnow(),
            started_at=None,
            source_run_id=source_run.id,
            lineage_root_run_id=lineage_root_run_id,
            forked_from_step_index=source_invocation.step_index,
            resume_step_index=resume_step_index,
            final_output=None,
            total_tokens=inherited_tokens,
            inherited_tokens=inherited_tokens,
            executed_tokens=0,
            trace_id=None,
            error=None,
            finished_at=None,
        )
        source_snapshot = self._workflow_package_snapshot_for_run(source_run)
        run.workflow_package_snapshot = self._lineage_workflow_package_snapshot(
            source_run=source_run,
            launch_parameters=deepcopy(source_snapshot.launch_parameters),
            preflight=preflight,
        )
        try:
            _ = self.run_repository.add(run)
            self.session.flush()
            self._copy_lineage_context_rows(run=run, source_steps=prepared.copied_steps)
            self._create_planned_run_rows(
                run=run,
                plan=prepared.plan,
                validated_input=deepcopy(source_run.input),
                min_step_index=resume_step_index,
            )
            self.session.flush()
            target_invocation = self.run_agent_invocation_repository.get_by_run_step_slot(
                run.id,
                source_invocation.step_index,
                source_invocation.slot,
            )
            if target_invocation is None:
                raise business_rule_error(
                    "run_fork_target_not_found",
                    "Fork target invocation was not found in the planned descendant run",
                    details=[
                        {
                            "field": "sourceInvocationId",
                            "issue": (
                                "Source invocation does not map to a planned target invocation"
                            ),
                        }
                    ],
                )
            _ = self.run_agent_invocation_repository.mark_edited_input(
                target_invocation,
                resolved_input=deepcopy(invocation_input),
                source_invocation_id=source_invocation.id,
            )
            _ = self.run_fork_repository.create_fork(
                run_id=run.id,
                source_run_id=source_run.id,
                lineage_root_run_id=lineage_root_run_id,
                source_invocation_id=source_invocation.id,
                source_step_index=source_invocation.step_index,
                resume_step_index=resume_step_index,
                invocation_input=deepcopy(invocation_input),
            )
            self.session.commit()
            self.session.refresh(run)
        except Exception:
            self.session.rollback()
            raise

        return self._to_created_read(run)

    def _lineage_workflow_package_snapshot(
        self,
        *,
        source_run: Run,
        launch_parameters: dict[str, Any],
        preflight: WorkflowPackagePreflightResult,
    ) -> RunWorkflowPackageSnapshot:
        source_snapshot = self._workflow_package_snapshot_for_run(source_run)
        return RunWorkflowPackageSnapshot(
            workflow_package_id=source_snapshot.workflow_package_id,
            workflow_package_key=source_snapshot.workflow_package_key,
            workflow_package_name=source_snapshot.workflow_package_name,
            workflow_package_description=source_snapshot.workflow_package_description,
            workflow_package_status=None,
            workflow_key=source_snapshot.workflow_key,
            workflow_name=source_snapshot.workflow_name,
            workflow_description=source_snapshot.workflow_description,
            manifest_hash=source_snapshot.manifest_hash,
            compiled_hash=source_snapshot.compiled_hash,
            manifest_source=source_snapshot.manifest_source,
            package_definition=deepcopy(source_snapshot.package_definition),
            compiled_plan=deepcopy(source_snapshot.compiled_plan),
            extension_dependencies=deepcopy(source_snapshot.extension_dependencies),
            local_resource_refs=deepcopy(source_snapshot.local_resource_refs),
            input_schema=deepcopy(source_snapshot.input_schema),
            launch_parameters=deepcopy(launch_parameters),
            resolved_model_connections=deepcopy(source_snapshot.resolved_model_connections),
            preflight_summary=self._preflight_summary_payload(preflight),
        )

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
            for position, plan_operation in enumerate(plan_step.operations):
                _ = self.run_operation_invocation_repository.create_operation(
                    run_step_id=run_step.id,
                    run_id=run.id,
                    step_index=plan_step.index,
                    slot=plan_operation.slot,
                    position=position,
                    operation_key=plan_operation.operation_key,
                    operation_kind=plan_operation.operation_kind,
                    output_schema_id=plan_operation.output_schema_id,
                    output_schema_version=plan_operation.output_schema_version,
                    method=plan_operation.method,
                    timeout_seconds=plan_operation.timeout_seconds,
                    request_metadata=deepcopy(plan_operation.request),
                    graph_metadata=self._graph_metadata_payload(plan_operation.graph_metadata),
                    optional=plan_operation.optional,
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
        return self._run_rerun_fork_preparation.build_plan_for_run(run)

    def _prepare_fork_source(
        self,
        source_run_id: int,
        source_invocation_id: int,
    ) -> PreparedRunFork:
        return self._run_rerun_fork_preparation.prepare_fork_source(
            source_run_id,
            source_invocation_id,
        )

    def _copy_lineage_context_rows(
        self,
        *,
        run: Run,
        source_steps: list[RunStep],
    ) -> None:
        self._run_rerun_fork_preparation.copy_lineage_context_rows(
            run=run,
            source_steps=source_steps,
        )

    def execute_run(self, run_id: int) -> None:
        import importlib

        queue_module = importlib.import_module("app.services.run_queue_service")
        _ = queue_module.RunQueueService(
            self.session,
            self.session_factory,
            provider_bundle=self.provider_bundle,
        ).drain_once(run_id=run_id)

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
        run = self.run_repository.get_detail(run_id)
        if run is None or run.status != _RUN_STATUS_RUNNING:
            return
        self._assert_run_extension_dependencies_enabled(run)
        if run.started_at is None:
            started_at = utcnow()
            run.started_at = started_at
            self.session.commit()
            self._run_workflow_package_start_lifecycle(run, now=started_at)
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

    def _run_workflow_package_start_lifecycle(self, run: Run, *, now: datetime) -> None:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            return
        extension_keys = self._run_extension_dependency_keys(run)
        context = WorkflowPackageStartContext(
            session=self.session,
            provider_bundle=self.provider_bundle,
            now=now,
        )
        hooks = ExtensionService(self.session).get_run_lifecycle_hooks(extension_keys)
        evaluators: list[MemoryFollowUpEvaluator] = []
        for hook in hooks:
            if hook.memory_follow_up_evaluators is not None:
                evaluators.extend(hook.memory_follow_up_evaluators(context))
        _ = MemoryFollowUpService(
            self.session,
            evaluators=tuple(evaluators),
        ).run_due(now)
        for hook in hooks:
            if hook.on_workflow_package_start is not None:
                hook.on_workflow_package_start(context)

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
        memory_service = MemoryService(
            self.session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                workflow_key=run.target_key,
                agent_key=context_invocation.agent_key,
                run_step_id=context_invocation.run_step_id,
                run_agent_invocation_id=context_invocation.id,
                step_id=trusted_context.step_id,
                trace_span_id=context_invocation.trace_span_id,
            ),
        )
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
        slot_outputs.update(
            self.run_operation_invocation_repository.hydrate_successful_outputs(
                run_id,
                before_step_index=before_step_index,
            )
        )
        for invocation in self.run_agent_invocation_repository.list_by_run(run_id):
            if before_step_index is not None and invocation.step_index >= before_step_index:
                continue
            if invocation.optional and invocation.status in {"failed", "skipped"}:
                slot_outputs[(invocation.step_index, invocation.slot)] = None
        for operation in self.run_operation_invocation_repository.list_by_run(run_id):
            if before_step_index is not None and operation.step_index >= before_step_index:
                continue
            if operation.optional and operation.status in {"failed", "skipped"}:
                slot_outputs[(operation.step_index, operation.slot)] = None
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

    def _get_planned_operation_or_raise(
        self,
        *,
        run_id: int,
        step_index: int,
        slot: str,
    ) -> RunOperationInvocation:
        operation = self.run_operation_invocation_repository.get_by_run_step_slot(
            run_id,
            step_index,
            slot,
        )
        if operation is None:
            raise RunExecutionError(
                code="run_planned_operation_missing",
                message=f"Run {run_id} is missing planned operation {step_index}.{slot}",
            )
        return operation

    def _assert_planned_invocations_exist(self, *, run_id: int, step: ExecutionPlanStep) -> None:
        for plan_agent in step.agents:
            _ = self._get_planned_invocation_or_raise(
                run_id=run_id,
                step_index=step.index,
                slot=plan_agent.slot,
            )
        for plan_operation in step.operations:
            _ = self._get_planned_operation_or_raise(
                run_id=run_id,
                step_index=step.index,
                slot=plan_operation.slot,
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
        self._merge_invocation_runtime_metadata(
            invocation,
            failure.runtime_metadata,
        )
        _ = self.run_agent_invocation_repository.persist_failure(
            invocation,
            error_code=failure.code,
            error_message=failure.message,
            error_details=list(failure.details),
            tokens=tokens,
            duration_ms=duration_ms,
            trace_span_id=trace_span_id,
        )

    def _persist_failed_operation(
        self,
        operation: RunOperationInvocation,
        failure: RunExecutionError,
        *,
        request_metadata: dict[str, Any] | None,
        response_metadata: dict[str, Any] | None,
        duration_ms: int | None,
        trace_span_id: str | None,
    ) -> None:
        if request_metadata is not None:
            operation.request_metadata = deepcopy(request_metadata)
        _ = self.run_operation_invocation_repository.persist_failure(
            operation,
            error_code=failure.code,
            error_message=failure.message,
            error_details=list(failure.details),
            response_metadata=response_metadata,
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
            for operation in self.run_operation_invocation_repository.list_by_run_step(
                run_id,
                step.step_index,
            ):
                if operation.status == "pending":
                    _ = self.run_operation_invocation_repository.persist_skipped(
                        operation,
                        error_code="run_step_skipped",
                        error_message="Run failed before this operation started",
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
        prepared_operations: list[_PreparedOperationInvocation] = []
        step_slot_outputs: dict[str, Any] = {}
        fatal_error: str | None = None
        package_ownership = plan.package_ownership

        for plan_agent in step.agents:
            invocation = self._get_planned_invocation_or_raise(
                run_id=run.id,
                step_index=step_index,
                slot=plan_agent.slot,
            )
            prepared_agent, agent_failure = self._prepare_agent_invocation(
                runtime_context=_RuntimeInvocationContext(
                    run_id=run.id,
                    target_kind=self._run_target_kind(plan),
                    target_key=plan.target.key,
                    workflow_version=(
                        None if package_ownership is not None else plan.target.version
                    ),
                    workflow_key=(
                        package_ownership.workflow_key if package_ownership is not None else None
                    ),
                    package_ownership=package_ownership,
                ),
                step_index=step_index,
                plan_agent=plan_agent,
                invocation=invocation,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            if prepared_agent is None:
                assert agent_failure is not None
                self._persist_failed_invocation(
                    invocation,
                    agent_failure,
                    tokens=0,
                    duration_ms=None,
                    trace_span_id=agent_failure.trace_span_id,
                )
                step_slot_outputs[plan_agent.slot] = None
                if not plan_agent.optional and fatal_error is None:
                    fatal_error = agent_failure.message
                continue
            resolved_input_origin = (
                "edited"
                if invocation.resolved_input_origin == "edited"
                else self._runtime_resolved_input_origin(plan_agent)
            )
            _ = self.run_agent_invocation_repository.mark_running(
                invocation,
                resolved_input=prepared_agent.resolved_input,
                resolved_input_origin=resolved_input_origin,
            )
            prepared_invocations.append(prepared_agent)

        for plan_operation in step.operations:
            operation = self._get_planned_operation_or_raise(
                run_id=run.id,
                step_index=step_index,
                slot=plan_operation.slot,
            )
            prepared_operation, operation_failure = self._prepare_operation_invocation(
                step_index=step_index,
                plan_operation=plan_operation,
                invocation=operation,
                package_ownership=package_ownership,
            )
            if prepared_operation is None:
                assert operation_failure is not None
                self._persist_failed_operation(
                    operation,
                    operation_failure,
                    request_metadata=None,
                    response_metadata=None,
                    duration_ms=None,
                    trace_span_id=operation_failure.trace_span_id,
                )
                step_slot_outputs[plan_operation.slot] = None
                if not plan_operation.optional and fatal_error is None:
                    fatal_error = operation_failure.message
                continue
            _ = self.run_operation_invocation_repository.mark_running(operation)
            prepared_operations.append(prepared_operation)

        self.session.commit()
        invocation_results = await asyncio.gather(
            *(
                self._execute_invocation(prepared_agent, trace_id=trace_id)
                for prepared_agent in prepared_invocations
            ),
            return_exceptions=True,
        )
        operation_results = await asyncio.gather(
            *(
                self._execute_operation(
                    prepared_operation,
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                    trace_id=trace_id,
                )
                for prepared_operation in prepared_operations
            ),
            return_exceptions=True,
        )

        step_tokens = 0
        for index, prepared_agent in enumerate(prepared_invocations):
            agent_result = invocation_results[index]
            if isinstance(agent_result, BaseException):
                failure = self._coerce_execution_error(agent_result)
                self._persist_failed_invocation(
                    prepared_agent.invocation,
                    failure,
                    tokens=0,
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[prepared_agent.slot] = None
                if not prepared_agent.optional and fatal_error is None:
                    fatal_error = failure.message
                continue

            assert isinstance(agent_result, RunAgentInvocationResult)
            step_tokens += agent_result.tokens
            self._merge_invocation_runtime_metadata(
                prepared_agent.invocation,
                agent_result.runtime_metadata,
            )
            _ = self.run_agent_invocation_repository.persist_success(
                prepared_agent.invocation,
                output=agent_result.output,
                output_origin="executed",
                tokens=agent_result.tokens,
                duration_ms=agent_result.duration_ms,
                trace_span_id=agent_result.trace_span_id,
            )
            step_slot_outputs[prepared_agent.slot] = agent_result.output

        for index, prepared_operation in enumerate(prepared_operations):
            operation_result_entry = operation_results[index]
            if isinstance(operation_result_entry, BaseException):
                failure = self._coerce_operation_execution_error(operation_result_entry)
                self._persist_failed_operation(
                    prepared_operation.invocation,
                    failure,
                    request_metadata=None,
                    response_metadata=None,
                    duration_ms=None,
                    trace_span_id=failure.trace_span_id,
                )
                step_slot_outputs[prepared_operation.slot] = None
                if not prepared_operation.optional and fatal_error is None:
                    fatal_error = failure.message
                continue

            operation_result, trace_span_id = operation_result_entry
            if operation_result.error is not None:
                failure = RunExecutionError(
                    code=operation_result.error.code,
                    message=operation_result.error.message,
                    details=operation_result.error.details,
                    trace_span_id=trace_span_id,
                )
                self._persist_failed_operation(
                    prepared_operation.invocation,
                    failure,
                    request_metadata=operation_result.request_metadata,
                    response_metadata=operation_result.response_metadata,
                    duration_ms=operation_result.duration_ms,
                    trace_span_id=trace_span_id,
                )
                step_slot_outputs[prepared_operation.slot] = None
                if not prepared_operation.optional and fatal_error is None:
                    fatal_error = failure.message
                continue

            prepared_operation.invocation.request_metadata = deepcopy(
                operation_result.request_metadata
            )
            _ = self.run_operation_invocation_repository.persist_success(
                prepared_operation.invocation,
                output=operation_result.output,
                output_origin="executed",
                response_metadata=operation_result.response_metadata,
                duration_ms=operation_result.duration_ms,
                trace_span_id=trace_span_id,
            )
            step_slot_outputs[prepared_operation.slot] = operation_result.output

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
            if invocation.resolved_input_origin == "edited":
                resolved_input = self._validate_runtime_edited_invocation_input(
                    input_model=input_model,
                    invocation=invocation,
                )
            else:
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

    def _prepare_operation_invocation(
        self,
        *,
        step_index: int,
        plan_operation: ExecutionPlanOperation,
        invocation: RunOperationInvocation,
        package_ownership: PackageExecutionOwnership | None,
    ) -> tuple[_PreparedOperationInvocation | None, RunExecutionError | None]:
        try:
            output_model = self._resolve_runtime_operation_output_model(plan_operation)
            return (
                _PreparedOperationInvocation(
                    operation=plan_operation,
                    output_model=output_model,
                    invocation=invocation,
                    optional=plan_operation.optional,
                    step_index=step_index,
                    slot=plan_operation.slot,
                    package_ownership=package_ownership,
                ),
                None,
            )
        except RunExecutionError as exc:
            return None, exc
        except OutputSchemaCompilerError as exc:
            failure = RunExecutionError(
                code="operation_schema_build_failed",
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
            if target_name not in target_fields:
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

    @staticmethod
    def _merge_invocation_runtime_metadata(
        invocation: RunAgentInvocation,
        runtime_metadata: dict[str, Any] | None,
    ) -> None:
        if not runtime_metadata:
            return
        metadata = deepcopy(invocation.graph_metadata or {})
        gateway_metadata = metadata.get("modelGateway")
        if isinstance(gateway_metadata, dict):
            merged_gateway_metadata = deepcopy(gateway_metadata)
            merged_gateway_metadata.update(runtime_metadata)
        else:
            merged_gateway_metadata = deepcopy(runtime_metadata)
        metadata["modelGateway"] = merged_gateway_metadata
        invocation.graph_metadata = metadata

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
                    invocation=prepared.invocation,
                    resolved_input=prepared.resolved_input,
                    output_model=prepared.output_model,
                    trace_id=trace_id,
                    trace_span_id=trace_span_id,
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
            runtime_metadata=result.runtime_metadata,
        )

    async def _execute_operation(
        self,
        prepared: _PreparedOperationInvocation,
        *,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        trace_id: str | None,
    ) -> tuple[HttpOperationExecutionResult, str | None]:
        if trace_id is None:
            return await self._execute_operation_with_trace_span(
                prepared,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
                trace_span_id=None,
            )

        with create_logfire_span(
            "Run step {step_index} slot {slot} operation {operation_key}",
            step_index=prepared.step_index,
            slot=prepared.slot,
            operation_key=prepared.operation.operation_key,
            run_trace_id=trace_id,
        ) as operation_span:
            return await self._execute_operation_with_trace_span(
                prepared,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
                trace_span_id=format_current_span_id(operation_span),
            )

    async def _execute_operation_with_trace_span(
        self,
        prepared: _PreparedOperationInvocation,
        *,
        initial_input: dict[str, Any],
        slot_outputs: dict[tuple[int, str], Any],
        trace_span_id: str | None,
    ) -> tuple[HttpOperationExecutionResult, str | None]:
        try:
            result = await self.http_operation_execution_service.invoke(
                operation=prepared.operation,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
                package_ownership=prepared.package_ownership,
                output_model=prepared.output_model,
            )
        except HttpOperationExecutionError as exc:
            result = HttpOperationExecutionResult(
                output=None,
                request_metadata=deepcopy(exc.request_metadata or {}),
                response_metadata=deepcopy(exc.response_metadata or {}),
                duration_ms=0 if exc.duration_ms is None else exc.duration_ms,
                status_code=exc.status_code,
                error=exc,
            )
        return result, trace_span_id

    async def _invoke_agent(
        self,
        *,
        agent: Agent | PackageRuntimeAgentSpec,
        invocation: RunAgentInvocation,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        trace_span_id: str | None,
        step_index: int,
        slot: str,
    ) -> RunAgentInvocationResult:
        runtime_context = _CURRENT_RUNTIME_INVOCATION_CONTEXT.get()
        workflow_key = None
        workflow_version = None
        package_ownership = None
        if runtime_context is not None:
            workflow_version = runtime_context.workflow_version
            package_ownership = runtime_context.package_ownership
            if package_ownership is not None:
                workflow_key = package_ownership.workflow_key
        return await self.agent_execution_service.invoke(
            agent=agent,
            resolved_input=resolved_input,
            output_model=output_model,
            trace_id=trace_id,
            step_index=step_index,
            slot=slot,
            run_id=None if runtime_context is None else runtime_context.run_id,
            run_step_id=invocation.run_step_id,
            run_agent_invocation_id=invocation.id,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
            package_ownership=package_ownership,
            trace_span_id=trace_span_id,
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

    def _resolve_runtime_operation_output_model(
        self,
        operation: ExecutionPlanOperation,
    ) -> type[BaseModel]:
        output_schema = self._resolve_runtime_operation_output_schema(operation)
        return self.schema_compiler.build_runtime_model(output_schema)

    def _resolve_runtime_operation_output_schema(
        self,
        operation: ExecutionPlanOperation,
    ) -> OutputSchema:
        if operation.package_runtime_operation is not None:
            return self._package_output_schema_candidate(
                operation.package_runtime_operation.output_schema
            )
        output_schema = self.output_schema_repository.get(operation.output_schema_id)
        if output_schema is None or output_schema.version != operation.output_schema_version:
            raise RunExecutionError(
                code="run_operation_output_schema_missing",
                message=(
                    f"Operation {operation.operation_key!r} references a missing "
                    "output schema version"
                ),
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

    def _validate_fork_invocation_input(
        self,
        *,
        plan_agent: ExecutionPlanAgent,
        invocation_input: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run_rerun_fork_preparation.validate_fork_invocation_input(
            plan_agent=plan_agent,
            invocation_input=invocation_input,
        )

    def _validate_runtime_edited_invocation_input(
        self,
        *,
        input_model: type[BaseModel],
        invocation: RunAgentInvocation,
    ) -> dict[str, Any]:
        try:
            validated = input_model.model_validate(invocation.resolved_input)
        except ValidationError as exc:
            raise RunExecutionError(
                code="agent_input_validation_failed",
                message="Edited agent input failed schema validation",
                details=self._validation_details_from_pydantic_error(exc),
            ) from exc
        return validated.model_dump(mode="json", exclude_none=True)

    def _validate_run_input(
        self,
        *,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
        candidate_key: str,
        resource_name: str,
    ) -> dict[str, Any]:
        return self._run_rerun_fork_preparation.validate_run_input(
            input_schema=input_schema,
            input_payload=input_payload,
            candidate_key=candidate_key,
            resource_name=resource_name,
        )

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

    def _mark_run_failed_in_fresh_session(self, run_id: int, *, code: str, message: str) -> None:
        with self.session_factory() as session:
            service = RunService(
                session,
                self.session_factory,
                provider_bundle=self.provider_bundle,
            )
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
                "Workflow package run {workflow_package_key} snapshot {compiled_hash} #{run_id}",
                workflow_package_id=plan.target.id,
                workflow_package_key=plan.target.key,
                compiled_hash=(
                    plan.package_ownership.compiled_hash
                    if plan.package_ownership is not None
                    else None
                ),
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
    def _coerce_execution_error(exc: BaseException) -> RunExecutionError:
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
    def _coerce_operation_execution_error(exc: BaseException) -> RunExecutionError:
        if isinstance(exc, RunExecutionError):
            return exc
        if isinstance(exc, HttpOperationExecutionError):
            return RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details),
            )
        if isinstance(exc, ApiError):
            return RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details),
            )
        return RunExecutionError(code="operation_execution_failed", message=str(exc))

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
        preflight = prepared.preflight
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
                "manifestHash": prepared.package.manifest_hash,
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
                "traceId": run.trace_id,
                "createdAt": run.created_at,
            }
        )

    @staticmethod
    def _to_list_item(
        run: Run,
        *,
        progress: RunProgressRead,
        queue: RunQueueRead | None,
    ) -> RunListItemRead:
        return RunListItemRead.model_validate(
            {
                "id": run.id,
                "targetKind": run.target_kind,
                "targetId": run.target_id,
                "targetKey": run.target_key,
                "status": run.status,
                "progress": progress,
                "queue": queue,
                "totalTokens": run.total_tokens,
                "traceId": run.trace_id,
                "queuedAt": run.queued_at,
                "startedAt": run.started_at,
                "finishedAt": run.finished_at,
            }
        )

    @staticmethod
    def _package_local_resource_refs(compiled_plan: dict[str, Any]) -> dict[str, list[str]]:
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
            "protocolProfile": binding.protocol_profile,
            "baseUrl": binding.base_url,
            "modelId": binding.model_id,
            "reasoningEffort": binding.reasoning_effort,
            "capabilities": deepcopy(binding.capabilities),
            "outputStrategyPolicy": binding.output_strategy_policy,
            "parallelToolCallsPolicy": binding.parallel_tool_calls_policy,
            "reasoningPolicy": binding.reasoning_policy,
            "streamingPolicy": binding.streaming_policy,
            "probeCacheTtlSeconds": binding.probe_cache_ttl_seconds,
            "apiStyle": binding.api_style,
            "timeoutSeconds": binding.timeout_seconds,
            "hasApiKey": binding.has_api_key,
        }

    @staticmethod
    def _preflight_summary_payload(
        preflight: WorkflowPackagePreflightResult,
    ) -> dict[str, Any]:
        return {
            "ready": preflight.ready,
            "blockingErrors": deepcopy(preflight.blocking_errors),
            "warnings": deepcopy(preflight.warnings),
        }


__all__ = ["RunAgentInvocationResult", "RunExecutionError", "RunService"]
