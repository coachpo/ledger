# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnannotatedClassAttribute=false, reportUnnecessaryCast=false, reportUnknownMemberType=false
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy.orm import Session

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.mcp.runtime import SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS
from app.core.errors import ApiError
from app.models.output_schema import OutputSchema
from app.models.workflow_package import WorkflowPackageVersion
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.services.execution_plan import PackageResolvedModelBinding
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
        package_version: WorkflowPackageVersion,
        *,
        workflow_key: str,
        require_api_key: bool,
    ) -> WorkflowPackagePreflightResult:
        blocking_errors: list[dict[str, Any]] = []
        package_definition = package_version.package_definition or {}
        compiled_plan = package_version.compiled_plan or {}
        blocking_errors.extend(self._schema_errors(compiled_plan))
        blocking_errors.extend(self._tool_errors(compiled_plan))
        blocking_errors.extend(self._mcp_errors(compiled_plan))
        model_bindings, model_errors = self._model_bindings(
            compiled_plan,
            require_api_key=require_api_key,
        )
        blocking_errors.extend(model_errors)
        try:
            _ = PackageExecutionPlanBuilder.build_from_compiled_plan(
                compiled_plan,
                workflow_key,
                model_bindings=model_bindings,
                package_version=package_version.version,
            )
        except WorkflowPackageExecutionPlanError as exc:
            blocking_errors.extend(dict(detail) for detail in exc.details)
        return WorkflowPackagePreflightResult(
            ready=not blocking_errors,
            blocking_errors=blocking_errors,
            warnings=self.save_warnings(package_definition),
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
        catalog = get_default_tool_catalog()
        registered_keys = {tool.key for tool in catalog.list_registered_tools()}
        errors: list[dict[str, Any]] = []
        for profile in self._compiled_section(compiled_plan, "capabilityProfiles"):
            profile_key = str(profile.get("key") or "")
            tool_keys = [str(key) for key in profile.get("toolKeys") or []]
            try:
                _ = catalog.resolve_tool_keys(tool_keys)
            except ToolCatalogValidationError as exc:
                for detail in exc.details:
                    errors.append(
                        {
                            "field": self._profile_tool_key_path(
                                profile_key,
                                str(detail.get("field", "toolKeys")),
                            ),
                            "issue": detail.get("issue", "Invalid server-declared tool key"),
                        }
                    )
            for index, tool_key in enumerate(tool_keys):
                if tool_key not in registered_keys and not any(
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

    @staticmethod
    def _profile_tool_key_path(profile_key: str, field: str) -> str:
        if field.startswith("toolKeys."):
            index = field.removeprefix("toolKeys.")
            return f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
        return f"spec.capabilityProfiles.{profile_key}.toolKeys"

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
                                    "Unsupported package-private MCP tool "
                                    f"{normalized_tool_key!r}"
                                ),
                            }
                        )
            required_bindings = server.get("requiredBindings") or []
            if isinstance(required_bindings, list):
                for index, binding in enumerate(required_bindings):
                    errors.append(
                        {
                            "field": f"spec.mcpServers.{key}.requiredBindings[{index}]",
                            "issue": f"MCP secret binding {str(binding)!r} is not configured",
                        }
                    )
        return errors

    def _model_bindings(
        self,
        compiled_plan: dict[str, Any],
        *,
        require_api_key: bool,
    ) -> tuple[dict[str, PackageResolvedModelBinding], list[dict[str, Any]]]:
        bindings: dict[str, PackageResolvedModelBinding] = {}
        errors: list[dict[str, Any]] = []
        for index, agent in enumerate(self._compiled_section(compiled_plan, "agents")):
            key = str(agent.get("modelConnection") or "")
            path = f"spec.agents[{index}].modelConnection"
            try:
                binding = self.model_connection_service.resolve_package_model_connection_binding(
                    key,
                    path=path,
                    require_api_key=require_api_key,
                )
            except ApiError as exc:
                errors.extend(dict(detail) for detail in exc.details)
                continue
            connection = self.model_connection_repository.get_by_key(binding.key)
            if connection is None:
                errors.append({"field": path, "issue": f"Model connection {key!r} was not found"})
                continue
            bindings[binding.key] = PackageResolvedModelBinding(
                key=binding.key,
                name=binding.name,
                base_url=binding.base_url,
                model_id=binding.model_id,
                reasoning_effort=binding.reasoning_effort,
                api_style=binding.api_style,
                timeout_seconds=binding.timeout_seconds,
                has_api_key=binding.has_api_key,
            )
        return bindings, errors


__all__ = ["WorkflowPackagePreflightResult", "WorkflowPackagePreflightService"]
