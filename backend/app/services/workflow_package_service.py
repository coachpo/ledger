# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnannotatedClassAttribute=false, reportMissingImports=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnnecessaryIsInstance=false
from __future__ import annotations

from collections.abc import Callable
from typing import Any, NoReturn, cast
from urllib.parse import quote

from fastapi import Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.agents import ToolCatalog
from app.core.db_errors import is_unique_constraint_violation
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.workflow_package import WorkflowPackage, WorkflowPackageSecretBinding
from app.repositories.workflow_package import WorkflowPackageRepository
from app.repositories.workflow_package_secret_binding import WorkflowPackageSecretBindingRepository
from app.schemas.workflow_package import (
    WorkflowPackageImportRequest,
    WorkflowPackageLaunchCreateRequest,
    WorkflowPackageLaunchCreateResponse,
    WorkflowPackageLaunchRead,
    WorkflowPackageListRead,
    WorkflowPackageManifestRead,
    WorkflowPackageManifestRequest,
    WorkflowPackageRead,
    WorkflowPackageSecretBindingListRead,
    WorkflowPackageSecretBindingRead,
    WorkflowPackageSecretBindingUpdateRequest,
    WorkflowPackageUpdateRequest,
    WorkflowPackageValidationRead,
    normalize_workflow_package_secret_binding_key,
)
from app.schemas.workflow_package_manifest import WorkflowPackageManifestDiagnostic
from app.services.execution_providers import ExecutionProviderBundle
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.run_input_validation import validate_run_input_payload
from app.services.run_service import RunService
from app.services.workflow_package_export import (
    build_workflow_package_manifest_hydration_payload,
    export_workflow_package_yaml,
)
from app.services.workflow_package_manifest_compiler import (
    MCP_SECRET_PROJECTION_REDACTED,
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
    project_package_private_mcp_secrets,
)
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from app.services.workflow_package_preflight import WorkflowPackagePreflightService


class _WorkflowPackageDiagnosticsError(ValueError):
    def __init__(self, diagnostics: list[WorkflowPackageManifestDiagnostic]) -> None:
        super().__init__("Workflow package manifest validation failed")
        self.diagnostics = diagnostics


_WORKFLOW_PACKAGE_KEY_CONSTRAINTS = frozenset({"uq_workflow_packages_key"})


class WorkflowPackageService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        provider_bundle: ExecutionProviderBundle | None = None,
        tool_catalog: ToolCatalog | None = None,
        run_service: RunService | None = None,
        preflight_service: WorkflowPackagePreflightService | None = None,
        preflight_service_factory: Callable[
            [Session], WorkflowPackagePreflightService
        ] = WorkflowPackagePreflightService,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.provider_bundle = provider_bundle or ExecutionProviderBundle()
        self.tool_catalog = self._artifact_tool_catalog(tool_catalog)
        self.repository = WorkflowPackageRepository(session)
        self.secret_binding_repository = WorkflowPackageSecretBindingRepository(session)
        self.schema_compiler = OutputSchemaCompiler()
        self.run_service = run_service
        self.preflight_service = preflight_service or preflight_service_factory(session)

    @staticmethod
    def _artifact_tool_catalog(tool_catalog: ToolCatalog | None) -> ToolCatalog:
        if tool_catalog is None:
            return ToolCatalog()
        return ToolCatalog(tool_registry=tool_catalog.tool_registry)

    def list_packages(self) -> WorkflowPackageListRead:
        packages = self.repository.list_packages()
        return WorkflowPackageListRead(items=[self._to_package_read(item) for item in packages])

    def get_package(self, package_id: int) -> WorkflowPackageRead:
        return self._to_package_read(self._get_package(package_id))

    def get_manifest(
        self,
        package_id: int,
    ) -> WorkflowPackageManifestRead:
        package = self._get_package(package_id)
        hydrated = build_workflow_package_manifest_hydration_payload(
            {"packageDefinition": package.package_definition}
        )
        return WorkflowPackageManifestRead.model_validate(
            {
                "packageId": package.id,
                "packageKey": package.key,
                **hydrated,
            }
        )

    def validate_manifest(
        self,
        payload: WorkflowPackageManifestRequest,
    ) -> WorkflowPackageValidationRead:
        try:
            prepared = self._prepare_manifest(payload.manifest_source)
        except _WorkflowPackageDiagnosticsError as exc:
            return WorkflowPackageValidationRead(diagnostics=exc.diagnostics)
        return self._validation_read(prepared)

    def create_package(self, payload: WorkflowPackageManifestRequest) -> WorkflowPackageRead:
        prepared = self._prepare_manifest_or_raise(payload.manifest_source)
        return self._create_prepared_package(
            prepared,
            manifest_source=payload.manifest_source,
            duplicate_error=self._duplicate_key_error(),
        )

    def update_package(
        self,
        package_id: int,
        payload: WorkflowPackageUpdateRequest,
    ) -> WorkflowPackageRead:
        package = self._get_package(package_id)
        if payload.manifest_source is not None:
            prepared = self._prepare_manifest_or_raise(payload.manifest_source)
            metadata = cast(dict[str, Any], prepared["packageDefinition"])["metadata"]
            if str(cast(dict[str, Any], metadata)["key"]) != package.key:
                raise validation_error(
                    "Workflow package manifest validation failed",
                    [
                        {
                            "field": "manifestSource",
                            "issue": f"Manifest key must remain {package.key!r}",
                            "path": "metadata.key",
                        }
                    ],
                )
            self.repository.update_package(
                package,
                name=str(cast(dict[str, Any], metadata)["name"]),
                description=str(cast(dict[str, Any], metadata).get("description") or ""),
                **self._current_artifact_fields(prepared, payload.manifest_source),
            )
        else:
            raise validation_error(
                "Workflow package update is empty",
                [{"field": "request", "issue": "Provide manifestSource"}],
            )
        try:
            self.session.commit()
            self.session.refresh(package)
        except Exception:
            self.session.rollback()
            raise
        return self._to_package_read(package)

    def delete_package(self, package_id: int) -> None:
        package = self._get_package(package_id)
        try:
            self._run_service().delete_runs_for_workflow_package(
                package_id=package.id,
                commit=False,
            )
            self.session.flush()
            self.repository.delete(package)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def list_secret_bindings(self, package_id: int) -> WorkflowPackageSecretBindingListRead:
        package = self._get_package(package_id)
        bindings = self.secret_binding_repository.list_for_package(package.id)
        return WorkflowPackageSecretBindingListRead(
            items=[self._to_secret_binding_read(binding) for binding in bindings]
        )

    def upsert_secret_binding(
        self,
        package_id: int,
        key: str,
        payload: WorkflowPackageSecretBindingUpdateRequest,
    ) -> WorkflowPackageSecretBindingRead:
        package = self._get_package(package_id)
        normalized_key = self._normalize_secret_binding_key(key)
        try:
            binding = self.secret_binding_repository.upsert(
                package_id=package.id,
                key=normalized_key,
                value=payload.value,
            )
            self.session.commit()
            self.session.refresh(binding)
        except Exception:
            self.session.rollback()
            raise
        return self._to_secret_binding_read(binding)

    def delete_secret_binding(self, package_id: int, key: str) -> None:
        package = self._get_package(package_id)
        normalized_key = self._normalize_secret_binding_key(key)
        binding = self.secret_binding_repository.get_by_key(package.id, normalized_key)
        if binding is None:
            raise not_found_error("Workflow package secret binding")
        try:
            self.secret_binding_repository.delete(binding)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def export_package(self, package_id: int) -> Response:
        package = self._get_package(package_id)
        exported = export_workflow_package_yaml(
            {
                "packageDefinition": package.package_definition,
                "compiledPlan": package.compiled_plan,
            }
        )
        filename = f"{package.key}.yaml"
        encoded_filename = quote(filename, safe="")
        return Response(
            content=exported,
            media_type="application/yaml",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}"
                )
            },
        )

    def import_package(self, payload: WorkflowPackageImportRequest) -> WorkflowPackageRead:
        prepared = self._prepare_manifest_or_raise(payload.manifest_source)
        return self._create_prepared_package(
            prepared,
            manifest_source=payload.manifest_source,
            duplicate_error=self._import_conflict_error(),
        )

    def preflight_package(
        self,
        package_id: int,
        *,
        workflow_key: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> WorkflowPackageLaunchRead:
        package = self._get_package(package_id)
        return self._build_launch_read(
            package,
            workflow_key=workflow_key,
            require_api_key=True,
            parameters=parameters,
        )

    def get_launch(
        self,
        package_id: int,
        *,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        package = self._get_package(package_id)
        return self._build_launch_read(
            package,
            workflow_key=workflow_key,
            require_api_key=False,
        )

    def create_launch(
        self,
        package_id: int,
        payload: WorkflowPackageLaunchCreateRequest,
    ) -> WorkflowPackageLaunchCreateResponse:
        return self._run_service().create_workflow_package_launch(package_id, payload)

    def _run_service(self) -> RunService:
        if self.run_service is None:
            raise RuntimeError("WorkflowPackageService requires RunService for run mutations")
        return self.run_service

    def _build_launch_read(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str | None,
        require_api_key: bool,
        parameters: dict[str, object] | None = None,
    ) -> WorkflowPackageLaunchRead:
        workflow = self._select_compiled_workflow(package, workflow_key)
        selected_workflow_key = str(workflow["key"])
        preflight = (
            self.preflight_service.strict_readiness(package, workflow_key=selected_workflow_key)
            if require_api_key
            else self.preflight_service.launch_metadata(package, workflow_key=selected_workflow_key)
        )
        parameter_errors = (
            self._workflow_input_validation_errors(workflow, parameters)
            if parameters is not None and not preflight.blocking_errors
            else []
        )
        blocking_errors = [*preflight.blocking_errors, *parameter_errors]
        return WorkflowPackageLaunchRead.model_validate(
            {
                "packageId": package.id,
                "packageKey": package.key,
                "manifestHash": package.manifest_hash,
                "workflowKey": selected_workflow_key,
                "name": workflow.get("name") or selected_workflow_key,
                "description": workflow.get("description") or "",
                "inputSchema": workflow.get("inputSchema") or {},
                "ready": preflight.ready and not parameter_errors,
                "blockingErrors": blocking_errors,
                "warnings": preflight.warnings,
            }
        )

    def _workflow_input_validation_errors(
        self,
        workflow: dict[str, Any],
        parameters: dict[str, object],
    ) -> list[dict[str, Any]]:
        try:
            _ = validate_run_input_payload(
                schema_compiler=self.schema_compiler,
                input_schema=cast(dict[str, Any], workflow.get("inputSchema") or {}),
                input_payload=cast(dict[str, Any], parameters),
                candidate_key="workflow_package_input",
                resource_name="workflow_package",
            )
        except ApiError as exc:
            if exc.code != "run_invalid_input":
                raise
            return exc.details
        return []

    def _create_prepared_package(
        self,
        prepared: dict[str, object],
        *,
        manifest_source: str,
        duplicate_error: ApiError,
    ) -> WorkflowPackageRead:
        metadata = cast(dict[str, Any], prepared["packageDefinition"])["metadata"]
        metadata_payload = cast(dict[str, Any], metadata)
        key = str(metadata_payload["key"])
        if self.repository.get_by_key(key) is not None:
            raise duplicate_error
        package = self.repository.create_package(
            key=key,
            name=str(metadata_payload["name"]),
            description=str(metadata_payload.get("description") or ""),
            **self._current_artifact_fields(prepared, manifest_source),
        )
        try:
            self.session.commit()
            self.session.refresh(package)
        except IntegrityError as exc:
            self.session.rollback()
            if is_unique_constraint_violation(exc, _WORKFLOW_PACKAGE_KEY_CONSTRAINTS):
                raise duplicate_error from exc
            raise
        except Exception:
            self.session.rollback()
            raise
        return self._to_package_read(package)

    def _prepare_manifest_or_raise(self, manifest_source: str) -> dict[str, object]:
        try:
            return self._prepare_manifest(manifest_source)
        except _WorkflowPackageDiagnosticsError as exc:
            self._raise_manifest_validation(exc.diagnostics)

    def _prepare_manifest(self, manifest_source: str) -> dict[str, object]:
        parsed = parse_workflow_package_manifest(manifest_source)
        if parsed.manifest is None or parsed.diagnostics:
            raise _WorkflowPackageDiagnosticsError(parsed.diagnostics)
        try:
            compiled = compile_workflow_package_manifest(
                parsed.manifest,
                tool_catalog=self.tool_catalog,
                reject_retired_memory_tools=True,
            )
        except WorkflowPackageManifestCompilerError as exc:
            raise _WorkflowPackageDiagnosticsError(exc.diagnostics) from exc
        return compiled

    def _current_artifact_fields(
        self,
        prepared: dict[str, object],
        manifest_source: str,
    ) -> dict[str, Any]:
        package_definition = cast(dict[str, Any], prepared["packageDefinition"])
        return {
            "manifest_source": manifest_source,
            "manifest_hash": str(prepared["manifestHash"]),
            "package_definition": package_definition,
            "compiled_plan": cast(dict[str, Any], prepared["compiledPlan"]),
            "compiled_hash": str(prepared["compiledHash"]),
            "extension_dependencies": cast(
                list[dict[str, Any]],
                prepared.get("extensionDependencies") or [],
            ),
        }

    @staticmethod
    def _select_compiled_workflow(
        package: WorkflowPackage,
        workflow_key: str | None,
    ) -> dict[str, Any]:
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
        if workflow_key is None:
            return cast(dict[str, Any], workflows[0])
        for workflow in workflows:
            if str(workflow.get("key")) == workflow_key:
                return cast(dict[str, Any], workflow)
        raise not_found_error("Workflow package workflow")

    def _get_package(self, package_id: int) -> WorkflowPackage:
        package = self.repository.get(package_id)
        if package is None:
            raise not_found_error("Workflow package")
        return package

    @staticmethod
    def _duplicate_key_error() -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="workflow_package_duplicate_key",
            message="A workflow package with this key already exists",
        )

    @staticmethod
    def _import_conflict_error() -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="workflow_package_import_conflict",
            message="An active workflow package with this key already exists",
        )

    @staticmethod
    def _normalize_secret_binding_key(key: str) -> str:
        try:
            return normalize_workflow_package_secret_binding_key(key)
        except ValueError as exc:
            raise validation_error(
                "Workflow package secret binding validation failed",
                [{"field": "key", "issue": str(exc)}],
            ) from exc

    def _to_package_read(self, package: WorkflowPackage) -> WorkflowPackageRead:
        return WorkflowPackageRead.model_validate(
            {
                "id": package.id,
                "key": package.key,
                "name": package.name,
                "description": package.description,
                "manifestHash": package.manifest_hash,
                "compiledHash": package.compiled_hash,
                "createdAt": package.created_at,
                "updatedAt": package.updated_at,
            }
        )

    @staticmethod
    def _to_secret_binding_read(
        binding: WorkflowPackageSecretBinding,
    ) -> WorkflowPackageSecretBindingRead:
        payload = binding.secret_payload if isinstance(binding.secret_payload, dict) else {}
        return WorkflowPackageSecretBindingRead.model_validate(
            {
                "packageId": binding.package_id,
                "key": binding.key,
                "hasValue": bool(str(payload.get("value") or "").strip()),
                "createdAt": binding.created_at,
                "updatedAt": binding.updated_at,
            }
        )

    def _validation_read(self, prepared: dict[str, object]) -> WorkflowPackageValidationRead:
        package_definition = cast(dict[str, Any], prepared["packageDefinition"])
        metadata = cast(dict[str, Any], package_definition["metadata"])
        redacted_package_definition = project_package_private_mcp_secrets(
            prepared["packageDefinition"],
            mode=MCP_SECRET_PROJECTION_REDACTED,
        )
        redacted_compiled_plan = project_package_private_mcp_secrets(
            prepared["compiledPlan"],
            mode=MCP_SECRET_PROJECTION_REDACTED,
        )
        return WorkflowPackageValidationRead.model_validate(
            {
                "diagnostics": [],
                "warnings": self.preflight_service.validation_warnings(package_definition),
                "metadata": {
                    "apiVersion": package_definition["apiVersion"],
                    "key": metadata["key"],
                    "name": metadata["name"],
                    "description": metadata.get("description") or "",
                },
                "packageDefinition": redacted_package_definition,
                "compiledPlan": redacted_compiled_plan,
                "manifestHash": prepared["manifestHash"],
                "compiledHash": prepared["compiledHash"],
            }
        )

    @staticmethod
    def _manifest_diagnostic_detail(
        diagnostic: WorkflowPackageManifestDiagnostic,
    ) -> dict[str, object]:
        return {
            "field": "manifestSource",
            "issue": diagnostic.message,
            "severity": diagnostic.severity.value,
            "path": diagnostic.path,
            "line": diagnostic.line,
            "column": diagnostic.column,
        }

    def _raise_manifest_validation(
        self,
        diagnostics: list[WorkflowPackageManifestDiagnostic],
    ) -> NoReturn:
        raise validation_error(
            "Workflow package manifest validation failed",
            [self._manifest_diagnostic_detail(diagnostic) for diagnostic in diagnostics],
        )


__all__ = ["WorkflowPackageService"]
