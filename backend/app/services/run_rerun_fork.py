from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error, validation_error
from app.core.formatting import utcnow
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.repositories.run import RunRepository
from app.repositories.run_agent_invocation import RunAgentInvocationRepository
from app.repositories.run_operation_invocation import RunOperationInvocationRepository
from app.schemas.model_connection import ModelConnectionCompatibilityResolution
from app.schemas.run import (
    RunForkCreateRequest,
    RunForkDraftRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunTargetKind,
)
from app.services.execution_ownership import PackageExecutionOwnership
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanStep,
    ExecutionPlanTarget,
    PackageResolvedModelBinding,
    PackageRuntimeAgentSpec,
)
from app.services.execution_plan_builder import ExecutionPlanBuilderError
from app.services.legacy_authoring import raise_legacy_global_authoring_runtime_blocked
from app.services.model_connection_compatibility import CompatibilityResolutionService
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)
from app.services.run_input_validation import (
    build_run_input_model,
    validate_run_input_payload,
    validation_details_from_pydantic_error,
)
from app.services.run_read_projection import RunReadProjection
from app.services.workflow_package_preflight import (
    WorkflowPackagePreflightResult,
    WorkflowPackagePreflightService,
)

_RUN_STATUS_SUCCEEDED = "succeeded"
_RUN_STATUS_FAILED = "failed"

_WorkflowPackageSnapshotResolver = Callable[[Run], RunWorkflowPackageSnapshot]
_RuntimeAgentResolver = Callable[[ExecutionPlanAgent], PackageRuntimeAgentSpec]


@dataclass(frozen=True)
class PreparedRunRerun:
    source_run: Run
    plan: ExecutionPlan
    validated_input: dict[str, Any]
    readiness: WorkflowPackagePreflightResult


@dataclass(frozen=True)
class PreparedRunFork:
    source_run: Run
    plan: ExecutionPlan
    copied_steps: list[RunStep]
    source_invocation: RunAgentInvocation
    plan_agent: ExecutionPlanAgent


@dataclass(frozen=True)
class PreparedRunForkCreate:
    prepared_fork: PreparedRunFork
    invocation_input: dict[str, Any]
    readiness: WorkflowPackagePreflightResult


class RunRerunForkPreparation:
    def __init__(
        self,
        *,
        session: Session,
        run_repository: RunRepository,
        run_agent_invocation_repository: RunAgentInvocationRepository,
        run_operation_invocation_repository: RunOperationInvocationRepository,
        schema_compiler: OutputSchemaCompiler,
        read_projection: RunReadProjection,
        preflight_service: WorkflowPackagePreflightService,
        workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver,
        resolve_runtime_agent: _RuntimeAgentResolver,
    ) -> None:
        self.session: Session = session
        self.run_repository: RunRepository = run_repository
        self.run_agent_invocation_repository: RunAgentInvocationRepository = (
            run_agent_invocation_repository
        )
        self.run_operation_invocation_repository: RunOperationInvocationRepository = (
            run_operation_invocation_repository
        )
        self.schema_compiler: OutputSchemaCompiler = schema_compiler
        self.read_projection: RunReadProjection = read_projection
        self.preflight_service: WorkflowPackagePreflightService = preflight_service
        self._workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver = (
            workflow_package_snapshot_for_run
        )
        self._resolve_runtime_agent: _RuntimeAgentResolver = resolve_runtime_agent

    def build_rerun_draft(self, source_run_id: int) -> RunRerunDraftRead:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            raise_legacy_global_authoring_runtime_blocked(source_run.target_kind)
        _ = self.build_plan_for_run(source_run)
        readiness = self._current_readiness_for_run(source_run)
        return RunRerunDraftRead.model_validate(
            {
                "sourceRunId": source_run.id,
                "targetKind": source_run.target_kind,
                "targetId": source_run.target_id,
                "targetKey": source_run.target_key,
                "parameters": deepcopy(source_run.input),
                **self._readiness_payload(readiness),
                "packageProvenance": self.read_projection.package_provenance_payload(source_run),
            }
        )

    def prepare_rerun_create(
        self,
        source_run_id: int,
        payload: RunRerunCreateRequest,
    ) -> PreparedRunRerun:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            raise_legacy_global_authoring_runtime_blocked(source_run.target_kind)
        readiness = self._current_readiness_for_run(source_run)
        self._assert_current_readiness(readiness)
        plan = self.build_plan_for_run(source_run)
        validated_input = self.validate_run_input(
            input_schema=plan.input_schema,
            input_payload=payload.parameters,
            candidate_key=f"{plan.target.kind}_input",
            resource_name=plan.target.kind,
        )
        return PreparedRunRerun(
            source_run=source_run,
            plan=plan,
            validated_input=validated_input,
            readiness=readiness,
        )

    def build_fork_draft(
        self,
        source_run_id: int,
        source_invocation_id: int,
    ) -> RunForkDraftRead:
        prepared = self.prepare_fork_source(source_run_id, source_invocation_id)
        source_run = prepared.source_run
        readiness = self._current_readiness_for_run(source_run)
        return RunForkDraftRead.model_validate(
            {
                "sourceRunId": source_run.id,
                "sourceInvocationId": prepared.source_invocation.id,
                "targetKind": source_run.target_kind,
                "targetId": source_run.target_id,
                "targetKey": source_run.target_key,
                "invocationInput": deepcopy(prepared.source_invocation.resolved_input),
                **self._readiness_payload(readiness),
                "packageProvenance": self.read_projection.package_provenance_payload(source_run),
            }
        )

    def prepare_fork_create(
        self,
        source_run_id: int,
        payload: RunForkCreateRequest,
    ) -> PreparedRunForkCreate:
        prepared_fork = self.prepare_fork_source(source_run_id, payload.source_invocation_id)
        readiness = self._current_readiness_for_run(prepared_fork.source_run)
        self._assert_current_readiness(readiness)
        invocation_input = self.validate_fork_invocation_input(
            plan_agent=prepared_fork.plan_agent,
            invocation_input=cast(dict[str, Any], deepcopy(payload.invocation_input)),
        )
        return PreparedRunForkCreate(
            prepared_fork=prepared_fork,
            invocation_input=invocation_input,
            readiness=readiness,
        )

    def build_plan_for_run(self, run: Run) -> ExecutionPlan:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            raise_legacy_global_authoring_runtime_blocked(run.target_kind)
        # Rebuild the plan from the stored run snapshot so rerun/fork keeps the
        # frozen effective runtime profile by default instead of rebinding live.
        snapshot = self._workflow_package_snapshot_for_run(run)
        ownership = self._package_execution_ownership_from_snapshot(snapshot)
        workflow_key = ownership.workflow_key
        try:
            model_bindings = self._snapshot_model_bindings(snapshot)
            package_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
                snapshot.compiled_plan,
                workflow_key,
                model_bindings=model_bindings,
                ownership=ownership,
            )
        except ValueError as exc:
            raise validation_error(
                "Run descendant validation failed",
                [
                    {
                        "field": "packageProvenance.resolvedModelConnections",
                        "issue": str(exc),
                    }
                ],
            ) from exc
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
                version=None,
            ),
        )

    def _current_readiness_for_run(self, run: Run) -> WorkflowPackagePreflightResult:
        snapshot = self._workflow_package_snapshot_for_run(run)
        return self.preflight_service.strict_readiness(
            self._workflow_package_from_snapshot(snapshot),
            workflow_key=snapshot.workflow_key,
        )

    @staticmethod
    def _assert_current_readiness(readiness: WorkflowPackagePreflightResult) -> None:
        if readiness.ready:
            return
        details = readiness.blocking_errors or [
            {
                "field": "workflowPackage",
                "issue": "Workflow package is not ready to run",
            }
        ]
        raise validation_error("Run descendant validation failed", details)

    @staticmethod
    def _readiness_payload(readiness: WorkflowPackagePreflightResult) -> dict[str, Any]:
        return {
            "ready": readiness.ready,
            "blockingErrors": deepcopy(readiness.blocking_errors),
            "warnings": deepcopy(readiness.warnings),
        }

    @staticmethod
    def _workflow_package_from_snapshot(snapshot: RunWorkflowPackageSnapshot) -> WorkflowPackage:
        return WorkflowPackage(
            id=snapshot.workflow_package_id,
            key=snapshot.workflow_package_key,
            name=snapshot.workflow_package_name,
            description=snapshot.workflow_package_description,
            manifest_source=snapshot.manifest_source,
            manifest_hash=snapshot.manifest_hash,
            package_definition=deepcopy(snapshot.package_definition),
            compiled_plan=deepcopy(snapshot.compiled_plan),
            compiled_hash=snapshot.compiled_hash,
            extension_dependencies=deepcopy(snapshot.extension_dependencies),
        )

    def prepare_fork_source(
        self,
        source_run_id: int,
        source_invocation_id: int,
    ) -> PreparedRunFork:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            raise_legacy_global_authoring_runtime_blocked(source_run.target_kind)
        if source_run.status != _RUN_STATUS_SUCCEEDED:
            raise business_rule_error(
                "run_fork_source_not_succeeded",
                "Only succeeded runs can be forked",
            )

        source_invocation = self._source_agent_invocation_for_id(
            source_run,
            source_invocation_id,
        )
        if source_invocation is None:
            source_operation = self._source_operation_invocation_for_id(
                source_run,
                source_invocation_id,
            )
            if source_operation is not None:
                raise self._unsupported_fork_target_error(source_invocation_id)
            raise not_found_error("Run agent invocation")

        plan = self.build_plan_for_run(source_run)
        plan_step = self._plan_step_for_index(plan, source_invocation.step_index)
        if plan_step is None:
            raise business_rule_error(
                "run_fork_step_not_found",
                f"Fork step {source_invocation.step_index} does not exist on the source run plan",
            )
        plan_agent = next(
            (agent for agent in plan_step.agents if agent.slot == source_invocation.slot),
            None,
        )
        if plan_agent is None:
            if any(operation.slot == source_invocation.slot for operation in plan_step.operations):
                raise self._unsupported_fork_target_error(source_invocation_id)
            raise business_rule_error(
                "run_fork_target_not_found",
                "Source invocation does not map to a forkable planned agent target",
                details=[
                    {
                        "field": "sourceInvocationId",
                        "issue": "Source invocation does not map to a planned agent target",
                    }
                ],
            )

        source_steps_by_index = {
            step.step_index: step for step in cast(list[RunStep], source_run.steps)
        }
        fork_step = source_steps_by_index.get(source_invocation.step_index)
        if fork_step is None:
            raise business_rule_error(
                "run_fork_step_not_found",
                f"Fork step {source_invocation.step_index} does not exist on the source run",
            )
        if fork_step.status != _RUN_STATUS_SUCCEEDED or fork_step.persisted_at is None:
            raise business_rule_error(
                "run_fork_step_not_persisted",
                f"Fork step {source_invocation.step_index} must be succeeded and persisted",
            )

        copied_steps = self.validated_copied_context_steps(
            plan=plan,
            source_steps_by_index=source_steps_by_index,
            resume_step_index=source_invocation.step_index,
            error_code_prefix="run_fork",
        )
        return PreparedRunFork(
            source_run=source_run,
            plan=plan,
            copied_steps=copied_steps,
            source_invocation=source_invocation,
            plan_agent=plan_agent,
        )

    def validate_fork_invocation_input(
        self,
        *,
        plan_agent: ExecutionPlanAgent,
        invocation_input: dict[str, Any],
    ) -> dict[str, Any]:
        agent = self._resolve_runtime_agent(plan_agent)
        input_schema = self._runtime_agent_input_schema(agent)
        return validate_run_input_payload(
            schema_compiler=self.schema_compiler,
            input_schema=input_schema,
            input_payload=invocation_input,
            candidate_key=f"{agent.key}_input",
            resource_name="agent",
            error_code="run_fork_invalid_invocation_input",
            failure_message="Fork invocation input failed agent input schema validation",
        )

    def validate_run_input(
        self,
        *,
        input_schema: dict[str, Any],
        input_payload: dict[str, Any],
        candidate_key: str,
        resource_name: str,
    ) -> dict[str, Any]:
        return validate_run_input_payload(
            schema_compiler=self.schema_compiler,
            input_schema=input_schema,
            input_payload=input_payload,
            candidate_key=candidate_key,
            resource_name=resource_name,
        )

    def validated_copied_context_steps(
        self,
        *,
        plan: ExecutionPlan,
        source_steps_by_index: dict[int, RunStep],
        resume_step_index: int,
        error_code_prefix: str,
    ) -> list[RunStep]:
        plan_step_indexes = {step.index for step in plan.steps}
        if resume_step_index not in plan_step_indexes:
            raise business_rule_error(
                f"{error_code_prefix}_step_not_found",
                f"Resume step {resume_step_index} does not exist on the source run plan",
            )

        copied_steps: list[RunStep] = []
        for step_index in sorted(index for index in plan_step_indexes if index < resume_step_index):
            step = source_steps_by_index.get(step_index)
            if step is None or step.status != _RUN_STATUS_SUCCEEDED or step.persisted_at is None:
                raise business_rule_error(
                    f"{error_code_prefix}_context_not_persisted",
                    "All source context steps must be succeeded and persisted",
                    details=[{"field": f"steps.{step_index}", "issue": "Step is not persisted"}],
                )
            invocations = cast(list[RunAgentInvocation], step.invocations)
            for invocation in invocations:
                if not self._source_context_invocation_is_persisted(invocation):
                    raise business_rule_error(
                        f"{error_code_prefix}_context_output_not_persisted",
                        "All source context invocation outputs must be succeeded and persisted",
                        details=[
                            {
                                "field": f"steps.{step_index}.{invocation.slot}",
                                "issue": "Invocation output is not persisted",
                            }
                        ],
                    )
            operations = cast(list[RunOperationInvocation], step.operation_invocations)
            for operation in operations:
                if not self._source_context_operation_is_persisted(operation):
                    raise business_rule_error(
                        f"{error_code_prefix}_context_operation_not_persisted",
                        "All source context operation outputs must be succeeded and persisted",
                        details=[
                            {
                                "field": f"steps.{step_index}.{operation.slot}",
                                "issue": "Operation output is not persisted",
                            }
                        ],
                    )
            copied_steps.append(step)
        return copied_steps

    @staticmethod
    def copied_invocation_token_totals(source_steps: list[RunStep]) -> int:
        tokens = 0
        for step in source_steps:
            for invocation in cast(list[RunAgentInvocation], step.invocations):
                tokens += int(invocation.tokens or 0)
        return tokens

    def copy_lineage_context_rows(
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
            for source_operation in cast(
                list[RunOperationInvocation],
                source_step.operation_invocations,
            ):
                copied_operation = self.run_operation_invocation_repository.create_operation(
                    run_step_id=copied_step.id,
                    run_id=run.id,
                    step_index=source_operation.step_index,
                    slot=source_operation.slot,
                    position=source_operation.position,
                    operation_key=source_operation.operation_key,
                    operation_kind=source_operation.operation_kind,
                    output_schema_id=source_operation.output_schema_id,
                    output_schema_version=source_operation.output_schema_version,
                    method=source_operation.method,
                    timeout_seconds=source_operation.timeout_seconds,
                    request_metadata=deepcopy(source_operation.request_metadata),
                    response_metadata=deepcopy(source_operation.response_metadata),
                    graph_metadata=deepcopy(source_operation.graph_metadata),
                    optional=source_operation.optional,
                    status=source_operation.status,
                    output=deepcopy(source_operation.output),
                    output_origin=(
                        "copied" if source_operation.output_origin is not None else None
                    ),
                    source_operation_invocation_id=source_operation.id,
                    source_run_id=source_operation.run_id,
                    source_run_step_id=source_operation.run_step_id,
                    source_step_index=source_operation.step_index,
                )
                copied_operation.error_code = source_operation.error_code
                copied_operation.error_message = source_operation.error_message
                copied_operation.error_details = deepcopy(source_operation.error_details)
                copied_operation.duration_ms = source_operation.duration_ms
                copied_operation.trace_span_id = source_operation.trace_span_id
                copied_operation.started_at = source_operation.started_at
                copied_operation.finished_at = source_operation.finished_at
                copied_operation.persisted_at = copied_at

    def _get_run_or_raise(self, run_id: int) -> Run:
        run = self.run_repository.get_detail(run_id)
        if run is None:
            raise not_found_error("Run")
        return run

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
    def _snapshot_model_bindings(
        snapshot: RunWorkflowPackageSnapshot,
    ) -> dict[str, PackageResolvedModelBinding]:
        bindings: dict[str, PackageResolvedModelBinding] = {}
        for raw_binding in snapshot.resolved_model_connections or []:
            if not isinstance(raw_binding, dict):
                continue
            key = str(raw_binding.get("key") or "").strip()
            if not key:
                continue
            try:
                resolution = ModelConnectionCompatibilityResolution.model_validate(raw_binding)
            except ValidationError as exc:
                raise ValueError("Model connection snapshot is invalid") from exc
            bindings[key] = CompatibilityResolutionService.to_package_resolved_model_binding(
                resolution,
            )
        return bindings

    @staticmethod
    def _source_agent_invocation_for_id(
        source_run: Run,
        source_invocation_id: int,
    ) -> RunAgentInvocation | None:
        for step in cast(list[RunStep], source_run.steps):
            for invocation in cast(list[RunAgentInvocation], step.invocations):
                if invocation.id == source_invocation_id:
                    return invocation
        return None

    @staticmethod
    def _source_operation_invocation_for_id(
        source_run: Run,
        source_invocation_id: int,
    ) -> RunOperationInvocation | None:
        for step in cast(list[RunStep], source_run.steps):
            for operation in cast(list[RunOperationInvocation], step.operation_invocations):
                if operation.id == source_invocation_id:
                    return operation
        return None

    @staticmethod
    def _unsupported_fork_target_error(source_invocation_id: int) -> ApiError:
        return business_rule_error(
            "run_fork_target_unsupported",
            "Only agent invocation targets can be forked in this phase",
            details=[
                {
                    "field": "sourceInvocationId",
                    "issue": (
                        f"Invocation target {source_invocation_id} is an operation/tool target; "
                        "only agent invocations are supported"
                    ),
                }
            ],
        )

    @staticmethod
    def _plan_step_for_index(
        plan: ExecutionPlan,
        step_index: int,
    ) -> ExecutionPlanStep | None:
        return next((step for step in plan.steps if step.index == step_index), None)

    @staticmethod
    def _source_context_invocation_is_persisted(invocation: RunAgentInvocation) -> bool:
        if invocation.persisted_at is None:
            return False
        if invocation.status == _RUN_STATUS_SUCCEEDED:
            return invocation.output_origin is not None
        return invocation.optional and invocation.status in {_RUN_STATUS_FAILED, "skipped"}

    @staticmethod
    def _source_context_operation_is_persisted(operation: RunOperationInvocation) -> bool:
        if operation.persisted_at is None:
            return False
        if operation.status == _RUN_STATUS_SUCCEEDED:
            return operation.output_origin is not None
        return operation.optional and operation.status in {_RUN_STATUS_FAILED, "skipped"}

    @staticmethod
    def _runtime_agent_input_schema(agent: PackageRuntimeAgentSpec) -> dict[str, Any]:
        return agent.input_schema

    def _build_input_model(
        self,
        input_schema: dict[str, Any],
        *,
        candidate_key: str,
    ) -> type[BaseModel]:
        return build_run_input_model(
            self.schema_compiler,
            input_schema,
            candidate_key=candidate_key,
        )

    @staticmethod
    def _validation_details_from_pydantic_error(
        exc: ValidationError,
    ) -> list[dict[str, str]]:
        return validation_details_from_pydantic_error(exc)


__all__ = [
    "PreparedRunFork",
    "PreparedRunForkCreate",
    "PreparedRunRerun",
    "RunRerunForkPreparation",
]
