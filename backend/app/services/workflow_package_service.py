# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnannotatedClassAttribute=false, reportMissingImports=false, reportUnusedCallResult=false, reportUnnecessaryCast=false, reportUnnecessaryIsInstance=false
from __future__ import annotations

from typing import Any, NoReturn, cast

from fastapi import Response, status
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, not_found_error, validation_error
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.model_connection import normalize_model_connection_key
from app.schemas.workflow_package import (
    WorkflowPackageImportMode,
    WorkflowPackageImportRequest,
    WorkflowPackageLaunchCreateRequest,
    WorkflowPackageLaunchCreateResponse,
    WorkflowPackageLaunchRead,
    WorkflowPackageListRead,
    WorkflowPackageManifestRequest,
    WorkflowPackageRead,
    WorkflowPackageStatus,
    WorkflowPackageUpdateRequest,
    WorkflowPackageValidationRead,
    WorkflowPackageVersionListRead,
    WorkflowPackageVersionRead,
)
from app.schemas.workflow_package_manifest import WorkflowPackageManifestDiagnostic
from app.services.model_connection_service import ModelConnectionService
from app.services.quote_provider import QuoteProvider
from app.services.run_service import RunService
from app.services.workflow_package_export import export_workflow_package_yaml
from app.services.workflow_package_manifest_compiler import (
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
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
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.quote_provider = quote_provider
        self.repository = WorkflowPackageRepository(session)
        self.model_connection_service = ModelConnectionService(session)

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
        model_connection_refs = self._resolve_model_connection_refs(prepared)
        package = self.repository.create_package(
            key=key,
            name=str(cast(dict[str, Any], metadata)["name"]),
            description=str(cast(dict[str, Any], metadata).get("description") or ""),
            status="active",
            draft_source=payload.manifest_source,
        )
        try:
            version = self._create_version(
                package,
                prepared,
                payload.manifest_source,
                model_connection_refs=model_connection_refs,
            )
            self.session.commit()
            self.session.refresh(package)
            self.session.refresh(version)
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
            model_connection_refs = self._resolve_model_connection_refs(prepared)
            self.repository.update_package(
                package,
                name=str(cast(dict[str, Any], metadata)["name"]),
                description=str(cast(dict[str, Any], metadata).get("description") or ""),
                draft_source=payload.manifest_source,
                status="active" if payload.status is None else payload.status.value,
            )
            _ = self._create_version(
                package,
                prepared,
                payload.manifest_source,
                model_connection_refs=model_connection_refs,
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
        RunService(
            self.session,
            self.session_factory,
            quote_provider=self.quote_provider,
        ).delete_runs_for_target(
            target_kind="workflowPackage",
            target_id=package.id,
            workflow_package_id=package.id,
        )
        try:
            self.repository.delete(package)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def list_versions(self, package_id: int) -> WorkflowPackageVersionListRead:
        package = self._get_package(package_id)
        return WorkflowPackageVersionListRead(
            items=[
                self._to_version_read(item) for item in self.repository.list_versions(package.id)
            ]
        )

    def create_version(
        self,
        package_id: int,
        payload: WorkflowPackageManifestRequest,
    ) -> WorkflowPackageRead:
        package = self._get_package(package_id)
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
        model_connection_refs = self._resolve_model_connection_refs(prepared)
        try:
            self.repository.update_package(
                package,
                name=str(cast(dict[str, Any], metadata)["name"]),
                description=str(cast(dict[str, Any], metadata).get("description") or ""),
                status="active",
                draft_source=payload.manifest_source,
            )
            _ = self._create_version(
                package,
                prepared,
                payload.manifest_source,
                model_connection_refs=model_connection_refs,
            )
            self.session.commit()
            self.session.refresh(package)
        except Exception:
            self.session.rollback()
            raise
        return self._to_package_read(package)

    def export_package(self, package_id: int, *, version: int | None = None) -> Response:
        package, package_version = self._resolve_package_version(package_id, version=version)
        del package
        exported = export_workflow_package_yaml(
            {
                "packageDefinition": package_version.package_definition,
                "compiledPlan": package_version.compiled_plan,
            }
        )
        return Response(content=exported, media_type="application/yaml")

    def import_package(self, payload: WorkflowPackageImportRequest) -> WorkflowPackageRead:
        prepared = self._prepare_manifest_or_raise(payload.manifest_source)
        metadata = cast(dict[str, Any], prepared["packageDefinition"])["metadata"]
        key = str(cast(dict[str, Any], metadata)["key"])
        existing = self.repository.get_by_key(key)
        if existing is not None and payload.mode != WorkflowPackageImportMode.CREATE_VERSION:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_package_import_conflict",
                message="An active workflow package with this key already exists",
            )
        if existing is None:
            request = WorkflowPackageManifestRequest(manifest_source=payload.manifest_source)
            return self.create_package(request)
        return self.create_version(
            existing.id,
            WorkflowPackageManifestRequest(manifest_source=payload.manifest_source),
        )

    def preflight_package(
        self,
        package_id: int,
        *,
        version: int | None = None,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        package, package_version = self._resolve_package_version(package_id, version=version)
        workflow = self._select_compiled_workflow(package_version, workflow_key)
        selected_workflow_key = str(workflow["key"])
        preflight = WorkflowPackagePreflightService(self.session).run(
            package_version,
            workflow_key=selected_workflow_key,
            require_api_key=True,
        )
        return WorkflowPackageLaunchRead.model_validate(
            {
                "packageId": package.id,
                "packageKey": package.key,
                "packageVersion": package_version.version,
                "manifestHash": package_version.manifest_hash,
                "workflowKey": selected_workflow_key,
                "name": workflow.get("name") or selected_workflow_key,
                "description": workflow.get("description") or "",
                "inputSchema": workflow.get("inputSchema") or {},
                "ready": preflight.ready,
                "blockingErrors": preflight.blocking_errors,
                "warnings": preflight.warnings,
            }
        )

    def get_launch(
        self,
        package_id: int,
        *,
        version: int | None = None,
        workflow_key: str | None = None,
    ) -> WorkflowPackageLaunchRead:
        return RunService(
            self.session,
            self.session_factory,
            quote_provider=self.quote_provider,
        ).get_workflow_package_launch(
            package_id,
            version=version,
            workflow_key=workflow_key,
        )

    def create_launch(
        self,
        package_id: int,
        payload: WorkflowPackageLaunchCreateRequest,
    ) -> WorkflowPackageLaunchCreateResponse:
        return RunService(
            self.session,
            self.session_factory,
            quote_provider=self.quote_provider,
        ).create_workflow_package_launch(package_id, payload)

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
            compiled = compile_workflow_package_manifest(parsed.manifest)
        except WorkflowPackageManifestCompilerError as exc:
            raise _WorkflowPackageDiagnosticsError(exc.diagnostics) from exc
        return compiled

    def _create_version(
        self,
        package: WorkflowPackage,
        prepared: dict[str, object],
        manifest_source: str,
        *,
        model_connection_refs: list[tuple[int, str]],
    ) -> WorkflowPackageVersion:
        return self.repository.create_version(
            package,
            manifest_source=manifest_source,
            manifest_hash=str(prepared["manifestHash"]),
            package_definition=cast(dict[str, Any], prepared["packageDefinition"]),
            compiled_plan=cast(dict[str, Any], prepared["compiledPlan"]),
            compiled_hash=str(prepared["compiledHash"]),
            validation_summary={
                "diagnostics": [],
                "warnings": WorkflowPackagePreflightService(self.session).save_warnings(
                    cast(dict[str, Any], prepared["packageDefinition"])
                ),
            },
            model_connection_refs=model_connection_refs,
        )

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

    def _resolve_package_version(
        self,
        package_id: int,
        *,
        version: int | None,
    ) -> tuple[WorkflowPackage, WorkflowPackageVersion]:
        package = self._get_package(package_id)
        package_version = (
            self.repository.get_latest_version(package.id)
            if version is None
            else self.repository.get_version(package.id, version)
        )
        if package_version is None:
            raise not_found_error("Workflow package version")
        return package, package_version

    @staticmethod
    def _select_compiled_workflow(
        package_version: WorkflowPackageVersion,
        workflow_key: str | None,
    ) -> dict[str, Any]:
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

    def _to_package_read(self, package: WorkflowPackage) -> WorkflowPackageRead:
        latest = package.latest_version or self.repository.get_latest_version(package.id)
        return WorkflowPackageRead.model_validate(
            {
                "id": package.id,
                "key": package.key,
                "name": package.name,
                "description": package.description,
                "status": package.status,
                "latestVersion": latest.version if latest is not None else None,
                "latestVersionId": latest.id if latest is not None else None,
                "manifestHash": latest.manifest_hash if latest is not None else None,
                "compiledHash": latest.compiled_hash if latest is not None else None,
                "warnings": self._version_warnings(latest),
                "createdAt": package.created_at,
                "updatedAt": package.updated_at,
            }
        )

    @staticmethod
    def _to_version_read(version: WorkflowPackageVersion) -> WorkflowPackageVersionRead:
        return WorkflowPackageVersionRead.model_validate(
            {
                "id": version.id,
                "packageId": version.package_id,
                "version": version.version,
                "manifestHash": version.manifest_hash,
                "compiledHash": version.compiled_hash,
                "validationSummary": version.validation_summary,
                "warnings": WorkflowPackageService._version_warnings(version),
                "createdAt": version.created_at,
                "launchedAt": version.launched_at,
            }
        )

    def _validation_read(self, prepared: dict[str, object]) -> WorkflowPackageValidationRead:
        package_definition = cast(dict[str, Any], prepared["packageDefinition"])
        metadata = cast(dict[str, Any], package_definition["metadata"])
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
                "packageDefinition": prepared["packageDefinition"],
                "compiledPlan": prepared["compiledPlan"],
                "manifestHash": prepared["manifestHash"],
                "compiledHash": prepared["compiledHash"],
            }
        )

    @staticmethod
    def _version_warnings(version: WorkflowPackageVersion | None) -> list[dict[str, Any]]:
        if version is None or not isinstance(version.validation_summary, dict):
            return []
        warnings = version.validation_summary.get("warnings")
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
