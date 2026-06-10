# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnnecessaryCast=false, reportUnknownMemberType=false
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from typing import Any, cast

from sqlalchemy.orm import Session

from app.agents import ToolCatalogValidationError
from app.agents.mcp.tool_adapter import SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS
from app.core.errors import ApiError
from app.models.workflow_package import WorkflowPackage
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.workflow_package_secret_binding import WorkflowPackageSecretBindingRepository
from app.schemas.workflow_package_manifest import WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS
from app.services.execution_plan import (
    PackageAgentExecutionRequirements,
    PackageExecutionRequirements,
    PackageResolvedModelBinding,
)
from app.services.extension_dependency_service import ExtensionDependencyService
from app.services.extension_service import ExtensionService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
    package_output_schema_candidate,
)
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)

_MODEL_CAPABILITY_REQUIRED_MISSING_CODE = "model_capability_required_missing"
_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE = "model_capability_probe_inconclusive"
_MODEL_REASONING_UNSUPPORTED_CODE = "model_reasoning_unsupported"


class WorkflowPackageDiagnosticProjectionContext(StrEnum):
    VALIDATION = "validation"
    LAUNCH_METADATA = "launch_metadata"
    STRICT_READINESS = "strict_readiness"


class WorkflowPackageDiagnosticLevel(StrEnum):
    HIDDEN = "hidden"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class WorkflowPackageDiagnosticFact:
    kind: str
    code: str
    issue: str
    field: str | None = None
    path: str | None = None
    subject: str | None = None
    metadata: Mapping[str, Any] = dataclass_field(default_factory=dict)
    levels: Mapping[WorkflowPackageDiagnosticProjectionContext, WorkflowPackageDiagnosticLevel] = (
        dataclass_field(default_factory=dict)
    )

    @property
    def identity(self) -> tuple[str, str, str, str | None]:
        return (
            self.kind,
            self.code,
            self.field or self.path or "",
            self.subject,
        )

    def level_for(
        self,
        context: WorkflowPackageDiagnosticProjectionContext,
    ) -> WorkflowPackageDiagnosticLevel:
        return self.levels.get(context, WorkflowPackageDiagnosticLevel.HIDDEN)

    def to_public_diagnostic(self) -> dict[str, Any]:
        diagnostic: dict[str, Any] = {}
        if self.field is not None:
            diagnostic["field"] = self.field
        if self.path is not None:
            diagnostic["path"] = self.path
        diagnostic["issue"] = self.issue
        for key, value in self.metadata.items():
            diagnostic.setdefault(key, value)
        return diagnostic


@dataclass(frozen=True)
class WorkflowPackagePreflightResult:
    ready: bool
    blocking_errors: list[dict[str, Any]] = dataclass_field(default_factory=list)
    warnings: list[dict[str, Any]] = dataclass_field(default_factory=list)
    model_bindings: dict[str, PackageResolvedModelBinding] = dataclass_field(default_factory=dict)
    package_requirements: PackageExecutionRequirements = dataclass_field(
        default_factory=PackageExecutionRequirements
    )
    agent_requirement_scopes: dict[str, PackageAgentExecutionRequirements] = dataclass_field(
        default_factory=dict
    )


class WorkflowPackagePreflightService:
    def __init__(
        self,
        session: Session,
        *,
        extension_service: ExtensionService | None = None,
        extension_service_factory: Callable[[Session], ExtensionService] = ExtensionService,
    ) -> None:
        self.session = session
        self.extension_service = extension_service or extension_service_factory(session)
        self.model_connection_service = ModelConnectionService(session)
        self.model_connection_repository = ModelConnectionRepository(session)
        self.secret_binding_repository = WorkflowPackageSecretBindingRepository(session)
        self.schema_compiler = OutputSchemaCompiler()

    def validation_warnings(self, package_definition: dict[str, Any]) -> list[dict[str, Any]]:
        warnings = self._project_validation_warning_facts(
            self._validation_warning_facts(package_definition)
        )
        for warning in warnings:
            warning.setdefault("severity", "warning")
        return warnings

    def launch_metadata(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str,
    ) -> WorkflowPackagePreflightResult:
        return self.evaluate_readiness(
            package,
            workflow_key=workflow_key,
            require_api_key=False,
        )

    def strict_readiness(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str,
    ) -> WorkflowPackagePreflightResult:
        return self.evaluate_readiness(
            package,
            workflow_key=workflow_key,
            require_api_key=True,
        )

    def save_warnings(self, package_definition: dict[str, Any]) -> list[dict[str, Any]]:
        return self.validation_warnings(package_definition)

    def run(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str,
        require_api_key: bool,
    ) -> WorkflowPackagePreflightResult:
        if require_api_key:
            return self.strict_readiness(package, workflow_key=workflow_key)
        return self.launch_metadata(package, workflow_key=workflow_key)

    def evaluate_readiness(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str,
        require_api_key: bool,
    ) -> WorkflowPackagePreflightResult:
        compiled_plan = package.compiled_plan or {}
        schema_facts = self._schema_errors(compiled_plan)
        tool_facts = self._tool_errors(compiled_plan)
        mcp_facts = self._mcp_errors(compiled_plan)
        existing_facts = [*schema_facts, *tool_facts, *mcp_facts]
        extension_facts = self._extension_dependency_errors(
            package,
            existing_facts=existing_facts,
        )
        http_facts = self._http_errors(package, compiled_plan)
        package_requirements = PackageExecutionPlanBuilder.derive_package_requirements(
            compiled_plan
        )
        agent_requirement_scopes = PackageExecutionPlanBuilder.derive_workflow_agent_requirements(
            compiled_plan,
            workflow_key,
        )
        model_bindings, model_facts = self._model_bindings(
            agent_requirement_scopes,
            require_api_key=require_api_key,
        )
        execution_plan_facts: list[WorkflowPackageDiagnosticFact] = []
        if not self._has_http_operations(compiled_plan):
            try:
                _ = PackageExecutionPlanBuilder.build_from_compiled_plan(
                    compiled_plan,
                    workflow_key,
                    model_bindings=model_bindings,
                )
            except WorkflowPackageExecutionPlanError as exc:
                execution_plan_facts.extend(self._execution_plan_error_facts(exc.details))
        readiness_context = self._readiness_projection_context(
            require_api_key=require_api_key,
        )
        readiness_facts = [
            *schema_facts,
            *tool_facts,
            *mcp_facts,
            *extension_facts,
            *http_facts,
            *model_facts,
            *execution_plan_facts,
        ]
        blocking_errors, warnings = self._project_diagnostic_facts(
            readiness_facts,
            context=readiness_context,
        )
        return WorkflowPackagePreflightResult(
            ready=not blocking_errors,
            blocking_errors=blocking_errors,
            warnings=warnings,
            model_bindings=model_bindings,
            package_requirements=package_requirements,
            agent_requirement_scopes=agent_requirement_scopes,
        )

    @staticmethod
    def _readiness_projection_context(
        *,
        require_api_key: bool,
    ) -> WorkflowPackageDiagnosticProjectionContext:
        if require_api_key:
            return WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS
        return WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA

    @classmethod
    def _readiness_diagnostic_facts(
        cls,
        diagnostics: Iterable[Mapping[str, Any]],
        *,
        level: WorkflowPackageDiagnosticLevel,
    ) -> list[WorkflowPackageDiagnosticFact]:
        return [
            cls._readiness_diagnostic_fact(diagnostic, level=level) for diagnostic in diagnostics
        ]

    @classmethod
    def _readiness_diagnostic_fact(
        cls,
        diagnostic: Mapping[str, Any],
        *,
        level: WorkflowPackageDiagnosticLevel,
    ) -> WorkflowPackageDiagnosticFact:
        issue = str(diagnostic.get("issue") or diagnostic.get("message") or "")
        kind, code, subject = cls._readiness_diagnostic_identity_components(
            diagnostic,
            issue=issue,
        )
        metadata = {
            key: value
            for key, value in diagnostic.items()
            if key not in {"field", "path", "issue", "message"}
        }
        return WorkflowPackageDiagnosticFact(
            kind=kind,
            code=code,
            issue=issue,
            field=cls._string_or_none(diagnostic.get("field")),
            path=cls._string_or_none(diagnostic.get("path")),
            subject=subject,
            metadata=metadata,
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: level,
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: level,
            },
        )

    @classmethod
    def _readiness_diagnostic_identity_components(
        cls,
        diagnostic: Mapping[str, Any],
        *,
        issue: str,
    ) -> tuple[str, str, str | None]:
        subject = cls._readiness_diagnostic_subject(diagnostic)
        if issue.startswith("Model connection ") and issue.endswith(" was not found"):
            return ("model_connection_not_found", "model_connection_not_found", subject)
        if issue == "API key is not configured":
            return ("model_connection_api_key_missing", "model_connection_api_key_missing", subject)
        code = str(diagnostic.get("code") or issue or "readiness_diagnostic")
        return (code, code, subject)

    @staticmethod
    def _readiness_diagnostic_subject(diagnostic: Mapping[str, Any]) -> str | None:
        subject_parts = [
            f"{key}={value}"
            for key in (
                "subject",
                "modelConnectionKey",
                "extensionKey",
                "toolKey",
                "workflowKey",
                "schemaKey",
                "agentKey",
                "requirement",
                "surface",
            )
            if (value := diagnostic.get(key)) is not None and value != ""
        ]
        if not subject_parts:
            return None
        return "|".join(subject_parts)

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _project_validation_warning_facts(
        facts: Iterable[WorkflowPackageDiagnosticFact],
    ) -> list[dict[str, Any]]:
        _, warnings = WorkflowPackagePreflightService._project_diagnostic_facts(
            facts,
            context=WorkflowPackageDiagnosticProjectionContext.VALIDATION,
        )
        return warnings

    @staticmethod
    def _project_diagnostic_facts(
        facts: Iterable[WorkflowPackageDiagnosticFact],
        *,
        context: WorkflowPackageDiagnosticProjectionContext,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        blocking_errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        seen_identities: set[tuple[str, str, str, str | None]] = set()
        for fact in facts:
            if fact.identity in seen_identities:
                continue
            seen_identities.add(fact.identity)
            diagnostic = fact.to_public_diagnostic()
            level = fact.level_for(context)
            if level == WorkflowPackageDiagnosticLevel.BLOCKING:
                blocking_errors.append(diagnostic)
            elif level == WorkflowPackageDiagnosticLevel.WARNING:
                warnings.append(diagnostic)
        return blocking_errors, warnings

    def _validation_warning_facts(
        self,
        package_definition: dict[str, Any],
    ) -> list[WorkflowPackageDiagnosticFact]:
        facts: list[WorkflowPackageDiagnosticFact] = []
        for index, agent in enumerate(self._agents(package_definition)):
            key = str(agent.get("modelConnection") or "")
            if not key:
                continue
            if self.model_connection_repository.get_by_key(key) is None:
                facts.append(
                    self._model_connection_not_found_fact(
                        field=f"spec.agents[{index}].modelConnection",
                        key=key,
                    )
                )
        return facts

    @staticmethod
    def _readiness_levels(
        level: WorkflowPackageDiagnosticLevel,
    ) -> dict[
        WorkflowPackageDiagnosticProjectionContext,
        WorkflowPackageDiagnosticLevel,
    ]:
        return {
            WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: level,
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: level,
        }

    @classmethod
    def _blocking_diagnostic_fact(
        cls,
        diagnostic: Mapping[str, Any],
        *,
        kind: str,
        code: str | None = None,
        subject: str | None = None,
    ) -> WorkflowPackageDiagnosticFact:
        metadata = {
            key: value
            for key, value in diagnostic.items()
            if key not in {"field", "path", "issue", "message"}
        }
        return WorkflowPackageDiagnosticFact(
            kind=kind,
            code=cls._string_or_none(diagnostic.get("code")) or code or kind,
            issue=str(diagnostic.get("issue") or diagnostic.get("message") or ""),
            field=cls._string_or_none(diagnostic.get("field")),
            path=cls._string_or_none(diagnostic.get("path")),
            subject=subject or cls._readiness_diagnostic_subject(diagnostic),
            metadata=metadata,
            levels=cls._readiness_levels(WorkflowPackageDiagnosticLevel.BLOCKING),
        )

    @classmethod
    def _schema_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        return cls._blocking_diagnostic_fact(diagnostic, kind="schema_invalid")

    @classmethod
    def _tool_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        return cls._blocking_diagnostic_fact(diagnostic, kind="tool_invalid")

    @classmethod
    def _extension_dependency_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        kind = cls._string_or_none(diagnostic.get("code")) or "extension_dependency_invalid"
        return cls._blocking_diagnostic_fact(diagnostic, kind=kind, code=kind)

    @classmethod
    def _mcp_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        return cls._blocking_diagnostic_fact(diagnostic, kind="mcp_invalid")

    @classmethod
    def _http_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
        *,
        subject: str | None = None,
    ) -> WorkflowPackageDiagnosticFact:
        issue = str(diagnostic.get("issue") or diagnostic.get("message") or "")
        kind = (
            "http_secret_missing"
            if issue.startswith("HTTP secret binding ") and issue.endswith(" is not configured")
            else "http_operation_invalid"
        )
        return cls._blocking_diagnostic_fact(diagnostic, kind=kind, subject=subject)

    @classmethod
    def _execution_plan_error_fact(
        cls,
        diagnostic: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        return cls._blocking_diagnostic_fact(
            diagnostic,
            kind="execution_plan_invalid",
            code="execution_plan_invalid",
        )

    @classmethod
    def _execution_plan_error_facts(
        cls,
        diagnostics: Iterable[Mapping[str, Any]],
    ) -> list[WorkflowPackageDiagnosticFact]:
        return [cls._execution_plan_error_fact(diagnostic) for diagnostic in diagnostics]

    @classmethod
    def _model_connection_not_found_fact(
        cls,
        *,
        field: str,
        key: str,
        issue: str | None = None,
    ) -> WorkflowPackageDiagnosticFact:
        return WorkflowPackageDiagnosticFact(
            kind="model_connection_not_found",
            code="model_connection_not_found",
            field=field,
            issue=issue or f"Model connection {key!r} was not found",
            subject=key,
            levels={
                WorkflowPackageDiagnosticProjectionContext.VALIDATION: (
                    WorkflowPackageDiagnosticLevel.WARNING
                ),
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        )

    @classmethod
    def _model_connection_api_key_missing_fact(
        cls,
        *,
        field: str,
        key: str,
    ) -> WorkflowPackageDiagnosticFact:
        return WorkflowPackageDiagnosticFact(
            kind="model_connection_api_key_missing",
            code="model_connection_api_key_missing",
            field=field,
            issue="API key is not configured",
            subject=key,
            levels={
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                )
            },
        )

    @classmethod
    def _model_connection_test_failed_fact(
        cls,
        *,
        field: str,
        key: str,
        issue: str,
    ) -> WorkflowPackageDiagnosticFact:
        return WorkflowPackageDiagnosticFact(
            kind="model_connection_test_failed",
            code="model_connection_test_failed",
            field=field,
            issue=issue,
            subject=key,
            levels=cls._readiness_levels(WorkflowPackageDiagnosticLevel.BLOCKING),
        )

    @classmethod
    def _requirement_fact(
        cls,
        *,
        kind: str,
        code: str,
        field: str,
        issue: str,
        level: WorkflowPackageDiagnosticLevel,
    ) -> WorkflowPackageDiagnosticFact:
        metadata: dict[str, Any] = {"code": code}
        if level == WorkflowPackageDiagnosticLevel.WARNING:
            metadata["severity"] = "warning"
        return WorkflowPackageDiagnosticFact(
            kind=kind,
            code=code,
            field=field,
            issue=issue,
            metadata=metadata,
            levels=cls._readiness_levels(level),
        )

    @classmethod
    def _with_diagnostic_metadata(
        cls,
        fact: WorkflowPackageDiagnosticFact,
        metadata: Mapping[str, Any],
    ) -> WorkflowPackageDiagnosticFact:
        merged_metadata = dict(metadata)
        merged_metadata.update(fact.metadata)
        subject = fact.subject or cls._readiness_diagnostic_subject(merged_metadata)
        return WorkflowPackageDiagnosticFact(
            kind=fact.kind,
            code=fact.code,
            issue=fact.issue,
            field=fact.field,
            path=fact.path,
            subject=subject,
            metadata=merged_metadata,
            levels=fact.levels,
        )

    @staticmethod
    def _facts_block_readiness(
        facts: Iterable[WorkflowPackageDiagnosticFact],
        *,
        context: WorkflowPackageDiagnosticProjectionContext,
    ) -> bool:
        return any(
            fact.level_for(context) == WorkflowPackageDiagnosticLevel.BLOCKING for fact in facts
        )

    @staticmethod
    def _agents(package_definition: dict[str, Any]) -> list[dict[str, Any]]:
        spec = package_definition.get("spec")
        if not isinstance(spec, dict):
            return []
        agents = spec.get("agents")
        return (
            [agent for agent in agents if isinstance(agent, dict)]
            if isinstance(agents, list)
            else []
        )

    @staticmethod
    def _compiled_section(compiled_plan: dict[str, Any], name: str) -> list[dict[str, Any]]:
        raw_items = compiled_plan.get(name) or []
        return (
            [item for item in raw_items if isinstance(item, dict)]
            if isinstance(raw_items, list)
            else []
        )

    def _schema_errors(self, compiled_plan: dict[str, Any]) -> list[WorkflowPackageDiagnosticFact]:
        diagnostics: list[dict[str, Any]] = []
        for index, schema in enumerate(self._compiled_section(compiled_plan, "outputSchemas")):
            diagnostics.extend(
                self._validate_schema(
                    schema.get("jsonSchema"),
                    field=f"spec.outputSchemas[{index}].jsonSchema",
                    candidate_key=str(schema.get("key") or f"output_schema_{index}"),
                )
            )
        for workflow in self._compiled_section(compiled_plan, "workflows"):
            workflow_key = str(workflow.get("key") or "workflow")
            diagnostics.extend(
                self._validate_schema(
                    workflow.get("inputSchema"),
                    field=f"spec.workflows.{workflow_key}.inputSchema",
                    candidate_key=f"{workflow_key}_input",
                )
            )
        for agent in self._compiled_section(compiled_plan, "agents"):
            agent_key = str(agent.get("key") or "agent")
            diagnostics.extend(
                self._validate_schema(
                    agent.get("inputSchema"),
                    field=f"spec.agents.{agent_key}.inputSchema",
                    candidate_key=f"{agent_key}_input",
                )
            )
        return [self._schema_error_fact(diagnostic) for diagnostic in diagnostics]

    def _validate_schema(
        self,
        raw_schema: object,
        *,
        field: str,
        candidate_key: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_schema, dict):
            return [{"field": field, "issue": "Schema must be an object"}]
        try:
            prepared = self.schema_compiler.normalize_payload(
                builder=None,
                json_schema=cast(dict[str, Any], raw_schema),
            )
            candidate = package_output_schema_candidate(
                key=candidate_key,
                name=candidate_key,
                description="Workflow package preflight schema candidate",
                json_schema=prepared.json_schema,
            )
            _ = self.schema_compiler.build_runtime_model(candidate)
        except OutputSchemaValidationFailure as exc:
            return [
                {
                    "field": self._schema_issue_field(field, issue.get("field", "jsonSchema")),
                    "issue": issue.get("issue", "Invalid schema"),
                }
                for issue in exc.issues
            ]
        except OutputSchemaCompilerError as exc:
            return [{"field": field, "issue": str(exc)}]
        return []

    @staticmethod
    def _schema_issue_field(base_field: str, issue_field: str) -> str:
        if issue_field == "jsonSchema":
            return base_field
        if issue_field.startswith("jsonSchema."):
            return issue_field.replace("jsonSchema", base_field, 1)
        return f"{base_field}.{issue_field}"

    def _tool_errors(self, compiled_plan: dict[str, Any]) -> list[WorkflowPackageDiagnosticFact]:
        catalog = self.extension_service.get_tool_catalog()
        known_keys = {tool.key for tool in catalog.list_known_tools()}
        diagnostics: list[dict[str, Any]] = []
        for profile in self._compiled_section(compiled_plan, "capabilityProfiles"):
            profile_key = str(profile.get("key") or "")
            tool_keys = [str(key) for key in profile.get("toolKeys") or []]
            try:
                _ = catalog.resolve_tool_keys(tool_keys)
            except ToolCatalogValidationError as exc:
                for detail in exc.details:
                    diagnostics.append(
                        self._profile_tool_error(profile_key=profile_key, detail=detail)
                    )
            for index, tool_key in enumerate(tool_keys):
                if tool_key not in known_keys and not any(
                    diagnostic["field"]
                    == f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
                    for diagnostic in diagnostics
                ):
                    diagnostics.append(
                        {
                            "field": f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]",
                            "issue": f"Unknown server-declared tool {tool_key!r}",
                        }
                    )
        return [self._tool_error_fact(diagnostic) for diagnostic in diagnostics]

    @classmethod
    def _profile_tool_error(
        cls,
        *,
        profile_key: str,
        detail: dict[str, object],
    ) -> dict[str, Any]:
        error: dict[str, Any] = {
            "field": cls._profile_tool_key_path(
                profile_key,
                str(detail.get("field", "toolKeys")),
            ),
            "issue": detail.get("issue", "Invalid server-declared tool key"),
        }
        for key in ("code", "extensionKey", "surface"):
            if key in detail:
                error[key] = detail[key]
        return error

    @staticmethod
    def _profile_tool_key_path(profile_key: str, field: str) -> str:
        if field.startswith("toolKeys."):
            index = field.removeprefix("toolKeys.")
            return f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
        return f"spec.capabilityProfiles.{profile_key}.toolKeys"

    def _extension_dependency_errors(
        self,
        package: WorkflowPackage,
        *,
        existing_facts: list[WorkflowPackageDiagnosticFact],
    ) -> list[WorkflowPackageDiagnosticFact]:
        dependencies = ExtensionDependencyService.normalize_dependency_payloads(
            package.extension_dependencies
        )
        if not dependencies:
            return []
        existing_disabled_keys = {
            str(fact.metadata.get("extensionKey") or "")
            for fact in existing_facts
            if fact.code == "extension_disabled"
        }
        diagnostics: list[dict[str, Any]] = []
        for dependency in dependencies:
            extension_key = str(dependency.get("extensionKey") or "")
            if not extension_key or extension_key in existing_disabled_keys:
                continue
            surface = self._preferred_dependency_surface(dependency)
            try:
                _ = self.extension_service.require_enabled(extension_key, surface=surface)
            except ApiError as exc:
                diagnostics.extend(dict(detail) for detail in exc.details)
        return [self._extension_dependency_error_fact(diagnostic) for diagnostic in diagnostics]

    @staticmethod
    def _preferred_dependency_surface(dependency: dict[str, Any]) -> str:
        surfaces = dependency.get("surfaces")
        if not isinstance(surfaces, list):
            return "workflowPackage.extensionDependency"
        for prefix in ("tool.", "runtime.tool.", "mcp.", "provider.", "hook."):
            for surface in surfaces:
                if isinstance(surface, str) and surface.startswith(prefix):
                    return surface
        return str(surfaces[0]) if surfaces else "workflowPackage.extensionDependency"

    def _mcp_errors(self, compiled_plan: dict[str, Any]) -> list[WorkflowPackageDiagnosticFact]:
        diagnostics: list[dict[str, Any]] = []
        for server in self._compiled_section(compiled_plan, "mcpServers"):
            key = str(server.get("key") or "")
            transport = str(server.get("transport") or "")
            if transport == "stdio":
                if not server.get("command"):
                    diagnostics.append(
                        {"field": f"spec.mcpServers.{key}.command", "issue": "command is required"}
                    )
                if not isinstance(server.get("args"), list) or not server.get("args"):
                    diagnostics.append(
                        {
                            "field": f"spec.mcpServers.{key}.args",
                            "issue": "args must contain at least one item",
                        }
                    )
            elif transport == "http-sse":
                if not server.get("url"):
                    diagnostics.append(
                        {"field": f"spec.mcpServers.{key}.url", "issue": "url is required"}
                    )
            else:
                diagnostics.append(
                    {
                        "field": f"spec.mcpServers.{key}.transport",
                        "issue": "transport must be stdio or http-sse",
                    }
                )
            tool_keys = server.get("toolKeys") or []
            if not isinstance(tool_keys, list) or not tool_keys:
                diagnostics.append(
                    {
                        "field": f"spec.mcpServers.{key}.toolKeys",
                        "issue": "toolKeys must contain at least one runtime-supported tool",
                    }
                )
            else:
                for index, tool_key in enumerate(tool_keys):
                    normalized_tool_key = str(tool_key)
                    if normalized_tool_key not in SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS:
                        diagnostics.append(
                            {
                                "field": f"spec.mcpServers.{key}.toolKeys[{index}]",
                                "issue": (
                                    f"Unsupported package-private MCP tool {normalized_tool_key!r}"
                                ),
                            }
                        )
        return [self._mcp_error_fact(diagnostic) for diagnostic in diagnostics]

    def _http_errors(
        self,
        package: WorkflowPackage,
        compiled_plan: dict[str, Any],
    ) -> list[WorkflowPackageDiagnosticFact]:
        errors: list[WorkflowPackageDiagnosticFact] = []
        output_schema_keys = {
            str(schema.get("key"))
            for schema in self._compiled_section(compiled_plan, "outputSchemas")
            if schema.get("key")
        }
        configured_secret_keys = self.secret_binding_repository.list_keys_for_package(package.id)
        for workflow in self._compiled_section(compiled_plan, "workflows"):
            workflow_key = str(workflow.get("key") or "workflow")
            seen_operation_keys: set[str] = set()
            for step_position, step in enumerate(cast(list[Any], workflow.get("steps") or [])):
                if not isinstance(step, dict):
                    continue
                step_index = int(step.get("index") or step_position + 1)
                seen_slots: set[str] = set()
                for agent in cast(list[Any], step.get("agents") or []):
                    if isinstance(agent, dict):
                        self._record_step_slot_error(
                            errors,
                            seen_slots,
                            slot=str(agent.get("slot") or ""),
                            field=(
                                f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                                ".agents.slot"
                            ),
                        )
                for operation_index, operation in enumerate(
                    cast(list[Any], step.get("operations") or [])
                ):
                    if not isinstance(operation, dict):
                        step_field = f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                        errors.append(
                            self._http_error_fact(
                                {
                                    "field": f"{step_field}.operations[{operation_index}]",
                                    "issue": "HTTP operation must be an object",
                                }
                            )
                        )
                        continue
                    errors.extend(
                        self._http_operation_errors(
                            operation,
                            workflow_key=workflow_key,
                            step_index=step_index,
                            operation_index=operation_index,
                            output_schema_keys=output_schema_keys,
                            configured_secret_keys=configured_secret_keys,
                            seen_operation_keys=seen_operation_keys,
                            seen_slots=seen_slots,
                        )
                    )
        return errors

    def _http_operation_errors(
        self,
        operation: dict[str, Any],
        *,
        workflow_key: str,
        step_index: int,
        operation_index: int,
        output_schema_keys: set[str],
        configured_secret_keys: set[str],
        seen_operation_keys: set[str],
        seen_slots: set[str],
    ) -> list[WorkflowPackageDiagnosticFact]:
        field_base = (
            f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
            f".operations[{operation_index}]"
        )
        errors: list[WorkflowPackageDiagnosticFact] = []
        if str(operation.get("operationKind") or "") != "http":
            return errors
        operation_key = str(operation.get("operationKey") or "")
        if operation_key in seen_operation_keys:
            errors.append(
                self._http_error_fact(
                    {"field": f"{field_base}.operationKey", "issue": "Duplicate HTTP node id"}
                )
            )
        if operation_key:
            seen_operation_keys.add(operation_key)
        self._record_step_slot_error(
            errors,
            seen_slots,
            slot=str(operation.get("slot") or ""),
            field=f"{field_base}.slot",
        )
        method = str(operation.get("method") or "").upper()
        if method not in WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS:
            allowed = ", ".join(WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS)
            errors.append(
                self._http_error_fact(
                    {
                        "field": f"{field_base}.method",
                        "issue": f"Unsupported HTTP method {method!r}; allowed methods: {allowed}",
                    }
                )
            )
        response = operation.get("response")
        if not isinstance(response, dict):
            errors.append(
                self._http_error_fact(
                    {"field": f"{field_base}.response", "issue": "response is required"}
                )
            )
        else:
            schema_key = str(response.get("outputSchema") or "")
            if schema_key not in output_schema_keys:
                errors.append(
                    self._http_error_fact(
                        {
                            "field": f"{field_base}.response.outputSchema",
                            "issue": f"Package output schema {schema_key!r} was not found",
                        }
                    )
                )
        request = operation.get("request")
        if not isinstance(request, dict):
            errors.append(
                self._http_error_fact(
                    {"field": f"{field_base}.request", "issue": "request is required"}
                )
            )
            return errors
        secret_keys, request_errors = self._collect_http_request_secret_refs(
            request,
            field=f"{field_base}.request",
        )
        errors.extend(request_errors)
        for secret_key in sorted(secret_keys - configured_secret_keys):
            errors.append(
                self._http_error_fact(
                    {
                        "field": f"{field_base}.request",
                        "issue": f"HTTP secret binding {secret_key!r} is not configured",
                    },
                    subject=secret_key,
                )
            )
        return errors

    @classmethod
    def _record_step_slot_error(
        cls,
        errors: list[WorkflowPackageDiagnosticFact],
        seen_slots: set[str],
        *,
        slot: str,
        field: str,
    ) -> None:
        if not slot:
            errors.append(cls._http_error_fact({"field": field, "issue": "slot is required"}))
            return
        if slot in seen_slots:
            errors.append(
                cls._http_error_fact(
                    {
                        "field": field,
                        "issue": "Duplicate output slot name within the same step",
                    }
                )
            )
        seen_slots.add(slot)

    def _collect_http_request_secret_refs(
        self,
        value: object,
        *,
        field: str,
    ) -> tuple[set[str], list[WorkflowPackageDiagnosticFact]]:
        if isinstance(value, dict):
            source = cast(dict[str, Any], value)
            if source.get("from") == "secret":
                key = str(source.get("key") or "")
                if not key:
                    return set(), [
                        self._http_error_fact(
                            {"field": field, "issue": "HTTP secret reference key is required"}
                        )
                    ]
                return {key}, []
            if source.get("from") == "step" and (
                source.get("stepIndex") is None or source.get("slot") is None
            ):
                return set(), [
                    self._http_error_fact(
                        {"field": field, "issue": "HTTP node step reference is malformed"}
                    )
                ]
            secret_keys: set[str] = set()
            errors: list[WorkflowPackageDiagnosticFact] = []
            for key, item in source.items():
                child_keys, child_errors = self._collect_http_request_secret_refs(
                    item,
                    field=f"{field}.{key}",
                )
                secret_keys.update(child_keys)
                errors.extend(child_errors)
            return secret_keys, errors
        if isinstance(value, list):
            listed_secret_keys: set[str] = set()
            listed_errors: list[WorkflowPackageDiagnosticFact] = []
            for index, item in enumerate(value):
                child_keys, child_errors = self._collect_http_request_secret_refs(
                    item,
                    field=f"{field}[{index}]",
                )
                listed_secret_keys.update(child_keys)
                listed_errors.extend(child_errors)
            return listed_secret_keys, listed_errors
        return set(), []

    @staticmethod
    def _has_http_operations(compiled_plan: dict[str, Any]) -> bool:
        workflows = WorkflowPackagePreflightService._compiled_section(
            compiled_plan,
            "workflows",
        )
        for workflow in workflows:
            for step in cast(list[Any], workflow.get("steps") or []):
                if isinstance(step, dict) and step.get("operations"):
                    return True
        return False

    def _model_bindings(
        self,
        agent_requirement_scopes: Mapping[str, PackageAgentExecutionRequirements],
        *,
        require_api_key: bool,
    ) -> tuple[
        dict[str, PackageResolvedModelBinding],
        list[WorkflowPackageDiagnosticFact],
    ]:
        bindings: dict[str, PackageResolvedModelBinding] = {}
        facts: list[WorkflowPackageDiagnosticFact] = []
        readiness_context = self._readiness_projection_context(
            require_api_key=require_api_key,
        )
        for scope in agent_requirement_scopes.values():
            key = scope.model_connection_key
            path = scope.model_connection_field
            scope_facts: list[WorkflowPackageDiagnosticFact] = []
            try:
                binding = self.model_connection_service.resolve_package_model_connection_binding(
                    key,
                    path=path,
                    require_api_key=False,
                )
            except ApiError as exc:
                scope_facts.extend(
                    self._model_binding_error_facts(
                        exc.details,
                        key=key,
                        field=path,
                    )
                )
                facts.extend(scope_facts)
                continue
            connection = self.model_connection_repository.get_by_key(binding.key)
            if connection is None:
                scope_facts.append(
                    self._model_connection_not_found_fact(
                        field=path,
                        key=binding.key,
                    )
                )
                facts.extend(scope_facts)
                continue
            if not binding.has_api_key:
                scope_facts.append(
                    self._model_connection_api_key_missing_fact(
                        field=path,
                        key=binding.key,
                    )
                )
            if connection.last_test_ok is False:
                scope_facts.append(
                    self._model_connection_test_failed_fact(
                        field=path,
                        key=binding.key,
                        issue=connection.last_test_message or "Connection test failed",
                    )
                )
            if not self._facts_block_readiness(scope_facts, context=readiness_context):
                scope_facts.extend(
                    self._package_requirement_issues(
                        binding=binding,
                        scope=scope,
                    )
                )
            facts.extend(scope_facts)
            if self._facts_block_readiness(scope_facts, context=readiness_context):
                continue
            bindings[binding.key] = binding
        return bindings, facts

    @classmethod
    def _model_binding_error_facts(
        cls,
        diagnostics: Iterable[Mapping[str, Any]],
        *,
        key: str,
        field: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        facts: list[WorkflowPackageDiagnosticFact] = []
        for diagnostic in diagnostics:
            issue = str(diagnostic.get("issue") or diagnostic.get("message") or "")
            diagnostic_field = cls._string_or_none(diagnostic.get("field")) or field
            if issue == f"Model connection {key!r} was not found":
                facts.append(
                    cls._model_connection_not_found_fact(
                        field=diagnostic_field,
                        key=key,
                        issue=issue,
                    )
                )
                continue
            if issue == "API key is not configured":
                facts.append(
                    cls._model_connection_api_key_missing_fact(
                        field=diagnostic_field,
                        key=key,
                    )
                )
                continue
            facts.append(
                cls._blocking_diagnostic_fact(
                    {**dict(diagnostic), "field": diagnostic_field},
                    kind=cls._string_or_none(diagnostic.get("code"))
                    or "model_connection_test_failed",
                    code=cls._string_or_none(diagnostic.get("code"))
                    or "model_connection_test_failed",
                    subject=key,
                )
            )
        return facts

    def _package_requirement_issues(
        self,
        *,
        binding: PackageResolvedModelBinding,
        scope: PackageAgentExecutionRequirements,
    ) -> list[WorkflowPackageDiagnosticFact]:
        requirements = scope.requirements
        path = scope.model_connection_field
        facts: list[WorkflowPackageDiagnosticFact] = []
        if requirements.requires_native_tool_calls:
            facts.extend(
                self._record_requirement_diagnostics(
                    binding=binding,
                    scope=scope,
                    requirement="nativeToolCalls",
                    collect=lambda: self._native_tool_requirement_issues(
                        binding=binding,
                        requirements=requirements,
                        path=path,
                    ),
                )
            )
        if requirements.requires_structured_output:
            facts.extend(
                self._record_requirement_diagnostics(
                    binding=binding,
                    scope=scope,
                    requirement="structuredOutput",
                    collect=lambda: self._structured_output_requirement_issues(
                        binding=binding,
                        requirements=requirements,
                        path=path,
                    ),
                )
            )
        if requirements.requires_parallel_tool_calls:
            facts.extend(
                self._record_requirement_diagnostics(
                    binding=binding,
                    scope=scope,
                    requirement="parallelToolCalls",
                    collect=lambda: self._parallel_tool_requirement_warnings(
                        binding=binding,
                        requirements=requirements,
                        path=path,
                    ),
                )
            )
        if requirements.requires_streaming:
            facts.extend(
                self._record_requirement_diagnostics(
                    binding=binding,
                    scope=scope,
                    requirement="streaming",
                    collect=lambda: self._streaming_requirement_issues(
                        binding=binding,
                        requirements=requirements,
                        path=path,
                    ),
                )
            )
        if requirements.requires_reasoning_hints:
            facts.extend(
                self._record_requirement_diagnostics(
                    binding=binding,
                    scope=scope,
                    requirement="reasoningHints",
                    collect=lambda: self._reasoning_requirement_issues(
                        binding=binding,
                        requirements=requirements,
                        path=path,
                    ),
                )
            )
        return facts

    @staticmethod
    def _requirement_diagnostic_context(
        *,
        binding: PackageResolvedModelBinding,
        scope: PackageAgentExecutionRequirements,
        requirement: str,
    ) -> dict[str, Any]:
        return {
            "agentKey": scope.agent_key,
            "modelConnectionKey": binding.key,
            "requirement": requirement,
        }

    def _record_requirement_diagnostics(
        self,
        *,
        binding: PackageResolvedModelBinding,
        scope: PackageAgentExecutionRequirements,
        requirement: str,
        collect: Callable[[], Iterable[WorkflowPackageDiagnosticFact]],
    ) -> list[WorkflowPackageDiagnosticFact]:
        context = self._requirement_diagnostic_context(
            binding=binding,
            scope=scope,
            requirement=requirement,
        )
        return [self._with_diagnostic_metadata(fact, context) for fact in collect()]

    def _native_tool_requirement_issues(
        self,
        *,
        binding: PackageResolvedModelBinding,
        requirements: PackageExecutionRequirements,
        path: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        field = requirements.native_tool_sources[0] if requirements.native_tool_sources else path
        status = self._capability_status(binding, "nativeToolCalls")
        if binding.parallel_tool_calls_policy == "forbid":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow requires native tool calls, but the selected model "
                        "connection forbids tool calls."
                    ),
                    level=WorkflowPackageDiagnosticLevel.BLOCKING,
                )
            ]
        if status in {"unsupported", "notApplicable"}:
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow requires native tool calls, but the selected model "
                        "connection does not support them."
                    ),
                    level=WorkflowPackageDiagnosticLevel.BLOCKING,
                )
            ]
        if status == "unknown":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    field=field,
                    issue=(
                        "This workflow requires native tool calls, but support has not been "
                        "proven yet."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        return []

    def _structured_output_requirement_issues(
        self,
        *,
        binding: PackageResolvedModelBinding,
        requirements: PackageExecutionRequirements,
        path: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        field = (
            requirements.structured_output_sources[0]
            if requirements.structured_output_sources
            else path
        )
        strict_status = self._capability_status(binding, "strictJsonSchemaOutput")
        json_status = self._capability_status(binding, "jsonObjectOutput")
        policy = binding.output_strategy_policy
        if policy == "allow_plain_text":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow requires structured JSON output, but the selected "
                        "model connection is configured for plain text."
                    ),
                    level=WorkflowPackageDiagnosticLevel.BLOCKING,
                )
            ]
        if policy == "require_strict_schema":
            if strict_status in {"unsupported", "notApplicable"}:
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but strict "
                            "JSON-schema output is not supported."
                        ),
                        level=WorkflowPackageDiagnosticLevel.BLOCKING,
                    )
                ]
            if strict_status == "unknown":
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but strict "
                            "JSON-schema output has not been proven yet."
                        ),
                        level=WorkflowPackageDiagnosticLevel.WARNING,
                    )
                ]
            return []
        if policy == "allow_json_object_validation":
            if json_status in {"unsupported", "notApplicable"}:
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but JSON object "
                            "output is not supported."
                        ),
                        level=WorkflowPackageDiagnosticLevel.BLOCKING,
                    )
                ]
            if json_status == "unknown":
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but JSON object "
                            "output has not been proven yet."
                        ),
                        level=WorkflowPackageDiagnosticLevel.WARNING,
                    )
                ]
            return []
        if strict_status in {"unsupported", "notApplicable"}:
            if json_status in {"unsupported", "notApplicable"}:
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but neither strict "
                            "JSON-schema output nor JSON object output is supported."
                        ),
                        level=WorkflowPackageDiagnosticLevel.BLOCKING,
                    )
                ]
            if json_status == "unknown":
                return [
                    self._requirement_fact(
                        kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                        field=field,
                        issue=(
                            "This workflow requires structured JSON output, but strict "
                            "JSON-schema output is unavailable and JSON object output has not "
                            "been proven yet."
                        ),
                        level=WorkflowPackageDiagnosticLevel.WARNING,
                    )
                ]
            return [
                self._requirement_fact(
                    kind="structured_output_json_object_fallback",
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow requires structured JSON output, but strict JSON-schema "
                        "output is unavailable so JSON object validation will be used."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        if strict_status == "unknown":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    field=field,
                    issue=(
                        "This workflow requires structured JSON output, but strict "
                        "JSON-schema output has not been proven yet."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        return []

    def _parallel_tool_requirement_warnings(
        self,
        *,
        binding: PackageResolvedModelBinding,
        requirements: PackageExecutionRequirements,
        path: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        field = (
            requirements.parallel_tool_sources[0] if requirements.parallel_tool_sources else path
        )
        status = self._capability_status(binding, "parallelToolCalls")
        if status in {"unsupported", "notApplicable"}:
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow uses parallel tool behavior, but the selected model "
                        "connection will serialize tool calls instead."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        if status == "unknown":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    field=field,
                    issue=(
                        "This workflow uses parallel tool behavior, but parallel tool-call "
                        "support has not been proven yet."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        return []

    def _streaming_requirement_issues(
        self,
        *,
        binding: PackageResolvedModelBinding,
        requirements: PackageExecutionRequirements,
        path: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        field = requirements.streaming_sources[0] if requirements.streaming_sources else path
        status = self._capability_status(binding, "streaming")
        if status in {"unsupported", "notApplicable"}:
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    code=_MODEL_CAPABILITY_REQUIRED_MISSING_CODE,
                    field=field,
                    issue=(
                        "This workflow requires streamed UI updates, but the selected model "
                        "connection does not support streaming."
                    ),
                    level=WorkflowPackageDiagnosticLevel.BLOCKING,
                )
            ]
        if status == "unknown":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    field=field,
                    issue=(
                        "This workflow requires streamed UI updates, but streaming support "
                        "has not been proven yet."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        return []

    def _reasoning_requirement_issues(
        self,
        *,
        binding: PackageResolvedModelBinding,
        requirements: PackageExecutionRequirements,
        path: str,
    ) -> list[WorkflowPackageDiagnosticFact]:
        field = requirements.reasoning_sources[0] if requirements.reasoning_sources else path
        status = self._capability_status(binding, "reasoningHints")
        if status in {"unsupported", "notApplicable"}:
            return [
                self._requirement_fact(
                    kind=_MODEL_REASONING_UNSUPPORTED_CODE,
                    code=_MODEL_REASONING_UNSUPPORTED_CODE,
                    field=field,
                    issue=(
                        "This workflow requires reasoning hints, but the selected model "
                        "connection does not support them."
                    ),
                    level=WorkflowPackageDiagnosticLevel.BLOCKING,
                )
            ]
        if status == "unknown":
            return [
                self._requirement_fact(
                    kind=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    code=_MODEL_CAPABILITY_PROBE_INCONCLUSIVE_CODE,
                    field=field,
                    issue=(
                        "This workflow requires reasoning hints, but reasoning support has "
                        "not been proven yet."
                    ),
                    level=WorkflowPackageDiagnosticLevel.WARNING,
                )
            ]
        return []

    @staticmethod
    def _capability_status(binding: PackageResolvedModelBinding, capability_key: str) -> str:
        capability = binding.capabilities.get(capability_key)
        if isinstance(capability, dict):
            status = capability.get("status")
            if isinstance(status, str):
                return status
        return "unknown"


__all__ = ["WorkflowPackagePreflightResult", "WorkflowPackagePreflightService"]
