from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from app.core.errors import business_rule_error, not_found_error, validation_error
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.workflow_package import WorkflowPackage
from app.repositories.run import RunRepository
from app.schemas.model_connection import ModelConnectionRuntimeProfile
from app.schemas.run import RunRerunCreateRequest, RunRerunDraftRead, RunTargetKind
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanBuilderError,
    ExecutionPlanTarget,
    PackageExecutionOwnership,
    PackageResolvedModelBinding,
)
from app.services.model_connection_resolution import ModelConnectionResolutionService
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)
from app.services.run_input_validation import validate_run_input_payload
from app.services.run_read_projection import RunReadProjection
from app.services.workflow_package_preflight import (
    WorkflowPackagePreflightResult,
    WorkflowPackagePreflightService,
)

_WorkflowPackageSnapshotResolver = Callable[[Run], RunWorkflowPackageSnapshot]


def _raise_package_run_required(target_kind: str) -> None:
    raise business_rule_error(
        "run_descendant_target_not_supported",
        "Run descendants are supported only for Workflow Package runs.",
        details=[
            {
                "field": "targetKind",
                "issue": f"Expected workflowPackage, got {target_kind}.",
            }
        ],
    )


@dataclass(frozen=True)
class PreparedRunRerun:
    source_run: Run
    plan: ExecutionPlan
    validated_input: dict[str, Any]
    readiness: WorkflowPackagePreflightResult


class RunRerunPreparation:
    def __init__(
        self,
        *,
        run_repository: RunRepository,
        schema_compiler: OutputSchemaCompiler,
        read_projection: RunReadProjection,
        preflight_service: WorkflowPackagePreflightService,
        workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver,
    ) -> None:
        self.run_repository: RunRepository = run_repository
        self.schema_compiler: OutputSchemaCompiler = schema_compiler
        self.read_projection: RunReadProjection = read_projection
        self.preflight_service: WorkflowPackagePreflightService = preflight_service
        self._workflow_package_snapshot_for_run: _WorkflowPackageSnapshotResolver = (
            workflow_package_snapshot_for_run
        )

    def build_rerun_draft(self, source_run_id: int) -> RunRerunDraftRead:
        source_run = self._get_run_or_raise(source_run_id)
        if source_run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            _raise_package_run_required(source_run.target_kind)
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
            _raise_package_run_required(source_run.target_kind)
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

    def build_plan_for_run(self, run: Run) -> ExecutionPlan:
        if run.target_kind != RunTargetKind.WORKFLOW_PACKAGE.value:
            _raise_package_run_required(run.target_kind)
        # Rebuild the plan from the stored run snapshot so rerun keeps the
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
                resolution = ModelConnectionRuntimeProfile.model_validate(raw_binding)
            except ValidationError as exc:
                raise ValueError("Model connection snapshot is invalid") from exc
            bindings[key] = ModelConnectionResolutionService.to_package_resolved_model_binding(
                resolution,
            )
        return bindings


__all__ = [
    "PreparedRunRerun",
    "RunRerunPreparation",
]
