# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnannotatedClassAttribute=false, reportMissingImports=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnnecessaryIsInstance=false
from __future__ import annotations

from typing import Any, NoReturn, cast

from fastapi import Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import ToolCatalog
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.workflow_package import WorkflowPackage, WorkflowPackageSecretBinding
from app.repositories.workflow_package import WorkflowPackageRepository
from app.repositories.workflow_package_secret_binding import WorkflowPackageSecretBindingRepository
from app.schemas.model_connection import normalize_model_connection_key
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
    WorkflowPackageStatus,
    WorkflowPackageUpdateRequest,
    WorkflowPackageValidationRead,
    normalize_workflow_package_secret_binding_key,
)
from app.schemas.workflow_package_manifest import WorkflowPackageManifestDiagnostic
from app.services.execution_providers import ExecutionProviderBundle
from app.services.extension_service import ExtensionService
from app.services.model_connection_service import ModelConnectionService
from app.services.quote_provider import QuoteProvider
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


class WorkflowPackageService:
    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session] | None = None,
        quote_provider: QuoteProvider | None = None,
        provider_bundle: ExecutionProviderBundle | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.provider_bundle = self._provider_bundle(
            provider_bundle=provider_bundle,
            quote_provider=quote_provider,
        )
        self.quote_provider = self.provider_bundle.quote_provider
        self.tool_catalog = tool_catalog or ExtensionService(session).get_tool_catalog()
        self.repository = WorkflowPackageRepository(session)
        self.secret_binding_repository = WorkflowPackageSecretBindingRepository(session)
        self.model_connection_service = ModelConnectionService(session)

    @staticmethod
    def _provider_bundle(
        *,
        provider_bundle: ExecutionProviderBundle | None,
        quote_provider: QuoteProvider | None,
    ) -> ExecutionProviderBundle:
        base_bundle = provider_bundle or ExecutionProviderBundle()
        if quote_provider is None:
            return base_bundle
        return ExecutionProviderBundle(
            quote_provider=quote_provider,
            fallback_quote_provider=base_bundle.fallback_quote_provider,
            social_sentiment_adapters=base_bundle.social_sentiment_adapters,
        )

    def list_packages(
        self,
        *,
        status_filter: WorkflowPackageStatus | None = None,
    ) -> WorkflowPackageListRead:
        packages = self.repository.list_packages(
            status=status_filter.value if status_filter is not None else None,
        )
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
        metadata = cast(dict[str, Any], prepared["packageDefinition"])["metadata"]
        key = str(cast(dict[str, Any], metadata)["key"])
        if self.repository.get_by_key(key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_package_duplicate_key",
                message="A workflow package with this key already exists",
            )
        self._resolve_model_connection_refs(prepared)
        package = self.repository.create_package(
            key=key,
            name=str(cast(dict[str, Any], metadata)["name"]),
            description=str(cast(dict[str, Any], metadata).get("description") or ""),
            status="active",
            **self._current_artifact_fields(prepared, payload.manifest_source),
        )
        try:
            self.session.commit()
            self.session.refresh(package)
        except Exception:
            self.session.rollback()
            raise
        return self._to_package_read(package)

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
            self._resolve_model_connection_refs(prepared)
            self.repository.update_package(
                package,
                name=str(cast(dict[str, Any], metadata)["name"]),
                description=str(cast(dict[str, Any], metadata).get("description") or ""),
                status="active" if payload.status is None else payload.status.value,
                **self._current_artifact_fields(prepared, payload.manifest_source),
            )
        elif payload.status is not None:
            self.repository.update_package(package, status=payload.status.value)
        else:
            raise validation_error(
                "Workflow package update is empty",
                [{"field": "request", "issue": "Provide manifestSource or status"}],
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
        reference_details = self._secret_binding_reference_details(package, normalized_key)
        if reference_details:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_package_secret_binding_in_use",
                message="Workflow package secret binding is in use",
                details=reference_details,
            )
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
        return Response(content=exported, media_type="application/yaml")

    def import_package(self, payload: WorkflowPackageImportRequest) -> WorkflowPackageRead:
        prepared = self._prepare_manifest_or_raise(payload.manifest_source)
        metadata = cast(dict[str, Any], prepared["packageDefinition"])["metadata"]
        key = str(cast(dict[str, Any], metadata)["key"])
        existing = self.repository.get_by_key(key)
        if existing is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_package_import_conflict",
                message="An active workflow package with this key already exists",
            )
        request = WorkflowPackageManifestRequest(manifest_source=payload.manifest_source)
        return self.create_package(request)

    def preflight_package(
        self,
        package_id: int,
        *,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        package = self._get_package(package_id)
        return self._build_launch_read(
            package,
            workflow_key=workflow_key,
            require_api_key=True,
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
        return RunService(
            self.session,
            self.session_factory,
            provider_bundle=self.provider_bundle,
        ).create_workflow_package_launch(package_id, payload)

    def _build_launch_read(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str | None,
        require_api_key: bool,
    ) -> WorkflowPackageLaunchRead:
        workflow = self._select_compiled_workflow(package, workflow_key)
        selected_workflow_key = str(workflow["key"])
        preflight = WorkflowPackagePreflightService(self.session).run(
            package,
            workflow_key=selected_workflow_key,
            require_api_key=require_api_key,
        )
        return WorkflowPackageLaunchRead.model_validate(
            {
                "packageId": package.id,
                "packageKey": package.key,
                "manifestHash": package.manifest_hash,
                "workflowKey": selected_workflow_key,
                "name": workflow.get("name") or selected_workflow_key,
                "description": workflow.get("description") or "",
                "inputSchema": workflow.get("inputSchema") or {},
                "ready": preflight.ready,
                "blockingErrors": preflight.blocking_errors,
                "warnings": preflight.warnings,
            }
        )

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
            "validation_summary": {
                "diagnostics": [],
                "warnings": WorkflowPackagePreflightService(self.session).save_warnings(
                    package_definition
                ),
            },
        }

    def _resolve_model_connection_refs(
        self,
        prepared: dict[str, object],
    ) -> list[tuple[int, str]]:
        compiled_plan = cast(dict[str, Any], prepared["compiledPlan"])
        agents = compiled_plan.get("agents")
        if not isinstance(agents, list):
            return []
        refs_by_id: dict[int, str] = {}
        errors: list[dict[str, str]] = []
        for index, raw_agent in enumerate(agents):
            if not isinstance(raw_agent, dict):
                continue
            path = f"spec.agents[{index}].modelConnection"
            try:
                model_connection_key = normalize_model_connection_key(
                    raw_agent.get("modelConnection")
                )
            except ValueError as exc:
                errors.append({"field": path, "issue": str(exc)})
                continue
            model_connection = self.model_connection_service.repository.get_by_key(
                model_connection_key
            )
            if model_connection is None:
                errors.append(
                    {
                        "field": path,
                        "issue": f"Model connection {model_connection_key!r} was not found",
                    }
                )
                continue
            refs_by_id[model_connection.id] = model_connection.key
        if errors:
            raise validation_error("Workflow package manifest validation failed", errors)
        return list(refs_by_id.items())

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
    def _normalize_secret_binding_key(key: str) -> str:
        try:
            return normalize_workflow_package_secret_binding_key(key)
        except ValueError as exc:
            raise validation_error(
                "Workflow package secret binding validation failed",
                [{"field": "key", "issue": str(exc)}],
            ) from exc

    def _secret_binding_reference_details(
        self,
        package: WorkflowPackage,
        key: str,
    ) -> list[dict[str, object]]:
        references: dict[tuple[str, int], dict[str, object]] = {}
        if self._compiled_plan_references_secret(package.compiled_plan, key):
            references[("workflowPackage", package.id)] = self._secret_reference_detail(
                ref_type="workflowPackage",
                ref_id=package.id,
                ref_key=package.key,
            )
        snapshot_statement = (
            select(RunWorkflowPackageSnapshot)
            .join(Run, Run.id == RunWorkflowPackageSnapshot.run_id)
            .where(
                Run.target_kind == "workflowPackage",
                RunWorkflowPackageSnapshot.workflow_package_id == package.id,
            )
            .order_by(
                RunWorkflowPackageSnapshot.workflow_package_key.asc(),
                RunWorkflowPackageSnapshot.workflow_key.asc(),
                RunWorkflowPackageSnapshot.run_id.asc(),
            )
        )
        for snapshot in self.session.scalars(snapshot_statement):
            if not self._compiled_plan_references_secret(snapshot.compiled_plan, key):
                continue
            ref_key = snapshot.workflow_package_key
            if snapshot.workflow_key:
                ref_key = f"{ref_key}:{snapshot.workflow_key}"
            references[("workflowPackageRunSnapshot", snapshot.run_id)] = (
                self._secret_reference_detail(
                    ref_type="workflowPackageRunSnapshot",
                    ref_id=snapshot.run_id,
                    ref_key=ref_key,
                )
            )
        return sorted(
            references.values(),
            key=lambda item: (
                str(item["refType"]),
                str(item["refKey"]),
                cast(int, item["refId"]),
            ),
        )

    @staticmethod
    def _secret_reference_detail(
        *,
        ref_type: str,
        ref_id: int,
        ref_key: str,
    ) -> dict[str, object]:
        return {
            "field": "secretBinding",
            "issue": "Secret binding is referenced",
            "refType": ref_type,
            "refId": ref_id,
            "refKey": ref_key,
        }

    @classmethod
    def _compiled_plan_references_secret(cls, value: object, key: str) -> bool:
        if isinstance(value, dict):
            raw_source = value.get("from", value.get("source"))
            if (
                isinstance(raw_source, str)
                and raw_source.strip().lower() in {"secret", "secrets"}
                and value.get("key") == key
            ):
                return True
            return any(cls._compiled_plan_references_secret(item, key) for item in value.values())
        if isinstance(value, list):
            return any(cls._compiled_plan_references_secret(item, key) for item in value)
        return False

    def _to_package_read(self, package: WorkflowPackage) -> WorkflowPackageRead:
        return WorkflowPackageRead.model_validate(
            {
                "id": package.id,
                "key": package.key,
                "name": package.name,
                "description": package.description,
                "status": package.status,
                "manifestHash": package.manifest_hash,
                "compiledHash": package.compiled_hash,
                "warnings": self._package_warnings(package),
                "createdAt": package.created_at,
                "updatedAt": package.updated_at,
                "lastLaunchedAt": package.last_launched_at,
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
                "warnings": WorkflowPackagePreflightService(self.session).save_warnings(
                    package_definition
                ),
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
    def _package_warnings(package: WorkflowPackage) -> list[dict[str, Any]]:
        if not isinstance(package.validation_summary, dict):
            return []
        warnings = package.validation_summary.get("warnings")
        return (
            [dict(item) for item in warnings if isinstance(item, dict)]
            if isinstance(warnings, list)
            else []
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
