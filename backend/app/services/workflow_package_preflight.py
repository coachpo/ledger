# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnnecessaryCast=false, reportUnknownMemberType=false
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.orm import Session

from app.agents import ToolCatalogValidationError
from app.agents.mcp.tool_adapter import SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS
from app.core.errors import ApiError
from app.models.output_schema import OutputSchema
from app.models.workflow_package import WorkflowPackage
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.workflow_package_secret_binding import WorkflowPackageSecretBindingRepository
from app.schemas.workflow_package_manifest import WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS
from app.services.execution_plan import PackageResolvedModelBinding
from app.services.extension_dependency_service import ExtensionDependencyService
from app.services.extension_service import ExtensionService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
)
from app.services.package_execution_plan_builder import (
    PackageExecutionPlanBuilder,
    WorkflowPackageExecutionPlanError,
)


@dataclass(frozen=True)
class WorkflowPackagePreflightResult:
    ready: bool
    blocking_errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    model_bindings: dict[str, PackageResolvedModelBinding] = field(default_factory=dict)


class WorkflowPackagePreflightService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.model_connection_service = ModelConnectionService(session)
        self.model_connection_repository = ModelConnectionRepository(session)
        self.secret_binding_repository = WorkflowPackageSecretBindingRepository(session)
        self.schema_compiler = OutputSchemaCompiler(OutputSchemaRepository(session))

    def save_warnings(self, package_definition: dict[str, Any]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        for index, agent in enumerate(self._agents(package_definition)):
            key = str(agent.get("modelConnection") or "")
            if not key:
                continue
            connection = self.model_connection_repository.get_by_key(key)
            if connection is None:
                warnings.append(
                    {
                        "field": f"spec.agents[{index}].modelConnection",
                        "issue": f"Model connection {key!r} was not found",
                        "severity": "warning",
                    }
                )
        return warnings

    def run(
        self,
        package: WorkflowPackage,
        *,
        workflow_key: str,
        require_api_key: bool,
    ) -> WorkflowPackagePreflightResult:
        blocking_errors: list[dict[str, Any]] = []
        package_definition = package.package_definition or {}
        compiled_plan = package.compiled_plan or {}
        blocking_errors.extend(self._schema_errors(compiled_plan))
        blocking_errors.extend(self._tool_errors(compiled_plan))
        blocking_errors.extend(self._mcp_errors(compiled_plan))
        blocking_errors.extend(
            self._extension_dependency_errors(
                package,
                existing_errors=blocking_errors,
            )
        )
        blocking_errors.extend(self._http_errors(package, compiled_plan))
        model_bindings, model_warnings, model_errors = self._model_bindings(
            compiled_plan,
            require_api_key=require_api_key,
        )
        blocking_errors.extend(model_errors)
        if not self._has_http_operations(compiled_plan):
            try:
                _ = PackageExecutionPlanBuilder.build_from_compiled_plan(
                    compiled_plan,
                    workflow_key,
                    model_bindings=model_bindings,
                )
            except WorkflowPackageExecutionPlanError as exc:
                blocking_errors.extend(dict(detail) for detail in exc.details)
        warnings = self.save_warnings(package_definition)
        warnings.extend(model_warnings)
        return WorkflowPackagePreflightResult(
            ready=not blocking_errors,
            blocking_errors=blocking_errors,
            warnings=warnings,
            model_bindings=model_bindings,
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

    def _schema_errors(self, compiled_plan: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for index, schema in enumerate(self._compiled_section(compiled_plan, "outputSchemas")):
            errors.extend(
                self._validate_schema(
                    schema.get("jsonSchema"),
                    field=f"spec.outputSchemas[{index}].jsonSchema",
                    candidate_key=str(schema.get("key") or f"output_schema_{index}"),
                )
            )
        for workflow in self._compiled_section(compiled_plan, "workflows"):
            workflow_key = str(workflow.get("key") or "workflow")
            errors.extend(
                self._validate_schema(
                    workflow.get("inputSchema"),
                    field=f"spec.workflows.{workflow_key}.inputSchema",
                    candidate_key=f"{workflow_key}_input",
                )
            )
        for agent in self._compiled_section(compiled_plan, "agents"):
            agent_key = str(agent.get("key") or "agent")
            errors.extend(
                self._validate_schema(
                    agent.get("inputSchema"),
                    field=f"spec.agents.{agent_key}.inputSchema",
                    candidate_key=f"{agent_key}_input",
                )
            )
        return errors

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
            candidate = OutputSchema(
                key=candidate_key,
                version=1,
                status="published",
                kind="standalone",
                name=candidate_key,
                description="Workflow package preflight schema candidate",
                json_schema=prepared.json_schema,
                registry_refs=[],
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

    def _tool_errors(self, compiled_plan: dict[str, Any]) -> list[dict[str, Any]]:
        catalog = ExtensionService(self.session).get_tool_catalog()
        known_keys = {tool.key for tool in catalog.list_known_tools()}
        errors: list[dict[str, Any]] = []
        for profile in self._compiled_section(compiled_plan, "capabilityProfiles"):
            profile_key = str(profile.get("key") or "")
            tool_keys = [str(key) for key in profile.get("toolKeys") or []]
            try:
                _ = catalog.resolve_tool_keys(tool_keys)
            except ToolCatalogValidationError as exc:
                for detail in exc.details:
                    errors.append(self._profile_tool_error(profile_key=profile_key, detail=detail))
            for index, tool_key in enumerate(tool_keys):
                if tool_key not in known_keys and not any(
                    error["field"] == f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
                    for error in errors
                ):
                    errors.append(
                        {
                            "field": f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]",
                            "issue": f"Unknown server-declared tool {tool_key!r}",
                        }
                    )
        return errors

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
        existing_errors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dependencies = ExtensionDependencyService.normalize_dependency_payloads(
            package.extension_dependencies
        )
        if not dependencies:
            return []
        existing_disabled_keys = {
            str(error.get("extensionKey") or "")
            for error in existing_errors
            if error.get("code") == "extension_disabled"
        }
        extension_service = ExtensionService(self.session)
        errors: list[dict[str, Any]] = []
        for dependency in dependencies:
            extension_key = str(dependency.get("extensionKey") or "")
            if not extension_key or extension_key in existing_disabled_keys:
                continue
            surface = self._preferred_dependency_surface(dependency)
            try:
                _ = extension_service.require_enabled(extension_key, surface=surface)
            except ApiError as exc:
                errors.extend(dict(detail) for detail in exc.details)
        return errors

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

    def _mcp_errors(self, compiled_plan: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for server in self._compiled_section(compiled_plan, "mcpServers"):
            key = str(server.get("key") or "")
            transport = str(server.get("transport") or "")
            if transport == "stdio":
                if not server.get("command"):
                    errors.append(
                        {"field": f"spec.mcpServers.{key}.command", "issue": "command is required"}
                    )
                if not isinstance(server.get("args"), list) or not server.get("args"):
                    errors.append(
                        {
                            "field": f"spec.mcpServers.{key}.args",
                            "issue": "args must contain at least one item",
                        }
                    )
            elif transport == "http-sse":
                if not server.get("url"):
                    errors.append(
                        {"field": f"spec.mcpServers.{key}.url", "issue": "url is required"}
                    )
            else:
                errors.append(
                    {
                        "field": f"spec.mcpServers.{key}.transport",
                        "issue": "transport must be stdio or http-sse",
                    }
                )
            tool_keys = server.get("toolKeys") or []
            if not isinstance(tool_keys, list) or not tool_keys:
                errors.append(
                    {
                        "field": f"spec.mcpServers.{key}.toolKeys",
                        "issue": "toolKeys must contain at least one runtime-supported tool",
                    }
                )
            else:
                for index, tool_key in enumerate(tool_keys):
                    normalized_tool_key = str(tool_key)
                    if normalized_tool_key not in SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS:
                        errors.append(
                            {
                                "field": f"spec.mcpServers.{key}.toolKeys[{index}]",
                                "issue": (
                                    f"Unsupported package-private MCP tool {normalized_tool_key!r}"
                                ),
                            }
                        )
        return errors

    def _http_errors(
        self,
        package: WorkflowPackage,
        compiled_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
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
                        errors.append(
                            {
                                "field": (
                                    f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                                    f".operations[{operation_index}]"
                                ),
                                "issue": "HTTP operation must be an object",
                            }
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
    ) -> list[dict[str, Any]]:
        field_base = (
            f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
            f".operations[{operation_index}]"
        )
        errors: list[dict[str, Any]] = []
        if str(operation.get("operationKind") or "") != "http":
            return errors
        operation_key = str(operation.get("operationKey") or "")
        if operation_key in seen_operation_keys:
            errors.append(
                {"field": f"{field_base}.operationKey", "issue": "Duplicate HTTP node id"}
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
                {
                    "field": f"{field_base}.method",
                    "issue": f"Unsupported HTTP method {method!r}; allowed methods: {allowed}",
                }
            )
        response = operation.get("response")
        if not isinstance(response, dict):
            errors.append({"field": f"{field_base}.response", "issue": "response is required"})
        else:
            schema_key = str(response.get("outputSchema") or "")
            if schema_key not in output_schema_keys:
                errors.append(
                    {
                        "field": f"{field_base}.response.outputSchema",
                        "issue": f"Package output schema {schema_key!r} was not found",
                    }
                )
        request = operation.get("request")
        if not isinstance(request, dict):
            errors.append({"field": f"{field_base}.request", "issue": "request is required"})
            return errors
        secret_keys, request_errors = self._collect_http_request_secret_refs(
            request,
            field=f"{field_base}.request",
        )
        errors.extend(request_errors)
        for secret_key in sorted(secret_keys - configured_secret_keys):
            errors.append(
                {
                    "field": f"{field_base}.request",
                    "issue": f"HTTP secret binding {secret_key!r} is not configured",
                }
            )
        return errors

    @staticmethod
    def _record_step_slot_error(
        errors: list[dict[str, Any]],
        seen_slots: set[str],
        *,
        slot: str,
        field: str,
    ) -> None:
        if not slot:
            errors.append({"field": field, "issue": "slot is required"})
            return
        if slot in seen_slots:
            errors.append(
                {
                    "field": field,
                    "issue": "Duplicate output slot name within the same step",
                }
            )
        seen_slots.add(slot)

    def _collect_http_request_secret_refs(
        self,
        value: object,
        *,
        field: str,
    ) -> tuple[set[str], list[dict[str, Any]]]:
        if isinstance(value, dict):
            source = cast(dict[str, Any], value)
            if source.get("from") == "secret":
                key = str(source.get("key") or "")
                if not key:
                    return set(), [
                        {"field": field, "issue": "HTTP secret reference key is required"}
                    ]
                return {key}, []
            if source.get("from") == "step" and (
                source.get("stepIndex") is None or source.get("slot") is None
            ):
                return set(), [{"field": field, "issue": "HTTP node step reference is malformed"}]
            secret_keys: set[str] = set()
            errors: list[dict[str, Any]] = []
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
            listed_errors: list[dict[str, Any]] = []
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
        compiled_plan: dict[str, Any],
        *,
        require_api_key: bool,
    ) -> tuple[
        dict[str, PackageResolvedModelBinding],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        bindings: dict[str, PackageResolvedModelBinding] = {}
        warnings: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, agent in enumerate(self._compiled_section(compiled_plan, "agents")):
            key = str(agent.get("modelConnection") or "")
            path = f"spec.agents[{index}].modelConnection"
            try:
                binding = self.model_connection_service.resolve_package_model_connection_binding(
                    key,
                    path=path,
                    require_api_key=False,
                )
            except ApiError as exc:
                errors.extend(dict(detail) for detail in exc.details)
                continue
            connection = self.model_connection_repository.get_by_key(binding.key)
            if connection is None:
                errors.append({"field": path, "issue": f"Model connection {key!r} was not found"})
                continue
            payload = (
                connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
            )
            has_api_key = bool(str(payload.get("apiKey") or "").strip())
            model_binding = PackageResolvedModelBinding(
                key=connection.key,
                name=connection.name,
                connection_kind=connection.connection_kind,
                base_url=connection.base_url,
                model_id=connection.model_id,
                reasoning_effort=connection.reasoning_effort,
                api_style=connection.api_style,
                timeout_seconds=connection.timeout_seconds,
                has_api_key=has_api_key,
            )
            if connection.connection_kind == "deterministic_smoke":
                warnings.append(
                    {
                        "field": path,
                        "issue": "Deterministic smoke connection will run offline",
                        "severity": "warning",
                        "connectionKind": connection.connection_kind,
                    }
                )
                bindings[connection.key] = model_binding
                continue
            if require_api_key and not has_api_key:
                errors.append({"field": path, "issue": "API key is not configured"})
                continue
            if connection.last_test_ok is False:
                errors.append(
                    {
                        "field": path,
                        "issue": connection.last_test_message or "Connection test failed",
                    }
                )
                continue
            bindings[connection.key] = model_binding
        return bindings, warnings, errors


__all__ = ["WorkflowPackagePreflightResult", "WorkflowPackagePreflightService"]
