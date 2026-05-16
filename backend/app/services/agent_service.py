from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import NoReturn, cast

from fastapi import status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.agents.mcp import McpClientBoundary, McpConnectionTester
from app.core.errors import ApiError, business_rule_error, not_found_error, validation_error
from app.db.session import get_session_factory
from app.models.agent import AGENT_MANIFEST_COMPILER_VERSION, Agent
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.platform_reference import WorkflowAgentRef
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.capability import CapabilityRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.schemas.agent import (
    AgentCapabilityRefWrite,
    AgentCreate,
    AgentListRead,
    AgentManifestValidationMetadata,
    AgentManifestValidationRead,
    AgentManifestValidationRequest,
    AgentMcpServerRead,
    AgentMcpServerRefWrite,
    AgentRead,
    AgentStatus,
    AgentUpdate,
)
from app.schemas.agent_manifest import AgentManifestDiagnostic, AgentManifestDiagnosticSeverity
from app.schemas.mcp_server import McpClientBoundaryRead
from app.schemas.model_connection import ModelConnectionListItemRead
from app.schemas.run import RunCreatedRead
from app.services.agent_manifest_compiler import AgentManifestCompiler, AgentManifestCompilerError
from app.services.agent_manifest_parser import locate_agent_manifest_path, parse_agent_manifest
from app.services.capability_service import CapabilityService
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_snapshot import (
    build_model_connection_runtime_snapshot,
    parse_model_connection_runtime_snapshot,
    snapshot_to_json,
)
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
)
from app.services.output_schema_service import OutputSchemaService
from app.services.run_service import RunService

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


@dataclass
class _PreparedAgentManifestWrite:
    payload: AgentCreate
    state: dict[str, object]
    manifest_api_version: str
    manifest_source: str
    manifest_hash: str
    compiler_version: str
    compiled_payload: dict[str, object]


class _AgentManifestDiagnosticsError(ValueError):
    def __init__(self, diagnostics: list[AgentManifestDiagnostic]) -> None:
        super().__init__("Agent manifest validation failed")
        self.diagnostics: list[AgentManifestDiagnostic] = diagnostics


class AgentService:
    def __init__(
        self,
        session: Session,
        tool_catalog: ToolCatalog,
        connection_tester: McpConnectionTester,
    ) -> None:
        self.session: Session = session
        self.repository: AgentRepository = AgentRepository(session)
        self.output_schema_repository: OutputSchemaRepository = OutputSchemaRepository(session)
        self.capability_repository: CapabilityRepository = CapabilityRepository(session)
        self.mcp_server_repository: McpServerRepository = McpServerRepository(session)
        self.model_connection_repository: ModelConnectionRepository = ModelConnectionRepository(
            session
        )
        self.capability_service: CapabilityService = CapabilityService(session, tool_catalog)
        self.mcp_server_service: McpServerService = McpServerService(session, connection_tester)
        self.output_schema_service: OutputSchemaService = OutputSchemaService(session)
        self.schema_compiler: OutputSchemaCompiler = OutputSchemaCompiler(
            self.output_schema_repository
        )
        self.manifest_compiler: AgentManifestCompiler = AgentManifestCompiler(session)

    def list_agents(
        self,
        *,
        status_filter: AgentStatus | None = None,
        model_name: str | None = None,
    ) -> AgentListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None,
            model=model_name,
        )
        return AgentListRead(items=[self._to_read_model(item) for item in items])

    def get_agent(self, agent_id: int, *, version: int | None = None) -> AgentRead:
        return self._to_read_model(self._resolve_model(agent_id, version=version))

    def validate_agent_manifest(
        self,
        payload: AgentManifestValidationRequest,
    ) -> AgentManifestValidationRead:
        try:
            prepared = self._prepare_manifest_write(payload.manifest_source)
        except _AgentManifestDiagnosticsError as exc:
            return AgentManifestValidationRead(diagnostics=exc.diagnostics)
        return AgentManifestValidationRead(
            diagnostics=[],
            metadata=AgentManifestValidationMetadata(
                api_version=prepared.manifest_api_version,
                key=prepared.payload.key,
                name=prepared.payload.name,
                description=prepared.payload.description,
            ),
            compiled_payload=prepared.compiled_payload,
            run_input_schema=cast(dict[str, object], prepared.state["input_schema"]),
        )

    def create_agent(self, payload: AgentCreate) -> AgentRead:
        del payload
        self._raise_structured_write_unsupported()

    def create_agent_from_manifest(self, manifest_source: str) -> AgentRead:
        prepared = self._prepare_manifest_write_or_raise(manifest_source)
        if self.repository.list_versions(prepared.payload.key):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="agent_duplicate_key",
                message="An agent with this key already exists",
            )

        agent = Agent(
            key=prepared.payload.key,
            version=1,
            status=AgentStatus.PUBLISHED.value,
            **prepared.state,
        )
        try:
            _ = self.repository.add(agent)
            self.session.commit()
            self.session.refresh(agent)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(agent)

    def update_agent(self, agent_id: int, payload: AgentUpdate) -> AgentRead:
        del agent_id, payload
        self._raise_structured_write_unsupported()

    def update_agent_from_manifest(self, agent_id: int, manifest_source: str) -> AgentRead:
        source = self._get_model(agent_id)
        prepared = self._prepare_manifest_write_or_raise(manifest_source)
        if prepared.payload.key != source.key:
            diagnostic = self._manifest_diagnostic(
                manifest_source,
                "metadata.key",
                f"Manifest key must remain {source.key!r} for agent updates",
            )
            self._raise_manifest_validation([diagnostic])

        agent = Agent(
            key=source.key,
            version=self._next_version(source.key),
            status=AgentStatus.PUBLISHED.value,
            **prepared.state,
        )

        current_published = self.repository.get_published_by_key(source.key)
        try:
            if current_published is not None:
                current_published.status = AgentStatus.DEPRECATED.value
                self.session.flush()
            _ = self.repository.add(agent)
            self.session.commit()
            self.session.refresh(agent)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(agent)

    def delete_agent(self, agent_id: int) -> None:
        agent = self._get_model(agent_id)
        workflow_refs = self._workflow_reference_details(agent.id)
        if workflow_refs:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="agent_delete_blocked",
                message="Agent is referenced by workflows",
                details=workflow_refs,
            )

        RunService(self.session).delete_runs_for_target(
            target_kind="agent",
            target_id=agent.id,
        )
        try:
            self.repository.delete(agent)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _workflow_reference_details(self, agent_id: int) -> list[dict[str, object]]:
        statement = (
            select(Workflow)
            .join(WorkflowAgentRef, Workflow.id == WorkflowAgentRef.workflow_id)
            .where(WorkflowAgentRef.agent_id == agent_id)
            .order_by(Workflow.key.asc(), Workflow.version.desc(), Workflow.id.asc())
        )
        return [
            {
                "field": "workflowId",
                "issue": "Agent is referenced by workflow",
                "workflowId": workflow.id,
                "workflowKey": workflow.key,
                "workflowVersion": workflow.version,
            }
            for workflow in self.session.scalars(statement)
        ]

    def create_run(
        self,
        agent_id: int,
        payload: JsonObject,
        *,
        version: int | None = None,
    ) -> RunCreatedRead:
        return RunService(self.session, get_session_factory()).create_target_run(
            "agent",
            agent_id,
            payload,
            version=version,
        )

    def _build_state(
        self,
        *,
        name: str,
        description: str,
        model_connection_id: int,
        system_prompt: str,
        input_schema: JsonObject,
        output_schema_key: str,
        output_schema_version: int | None,
        capabilities: Sequence[AgentCapabilityRefWrite],
        mcp_servers: Sequence[AgentMcpServerRefWrite],
        budget_usd: Decimal,
        manifest_api_version: str,
        manifest_source: str,
        manifest_hash: str,
        compiler_version: str,
    ) -> dict[str, object]:
        normalized_input_schema = self._normalize_input_schema(input_schema)
        output_schema = self._resolve_output_schema(output_schema_key, output_schema_version)
        capability_rows = self._resolve_capability_rows(capabilities)
        mcp_server_rows = self._resolve_mcp_server_rows(mcp_servers)
        model_connection = self._resolve_model_connection_for_save(model_connection_id)
        model_connection_snapshot = build_model_connection_runtime_snapshot(model_connection)
        return {
            "name": name,
            "description": description,
            "manifest_api_version": manifest_api_version,
            "manifest_source": manifest_source,
            "manifest_hash": manifest_hash,
            "compiler_version": compiler_version,
            "model_connection_id": model_connection.id,
            "model_connection_snapshot": model_connection_snapshot,
            "model": model_connection_snapshot["model_id"],
            "system_prompt": system_prompt,
            "input_schema": normalized_input_schema,
            "output_schema_id": output_schema.id,
            "output_schema_version": output_schema.version,
            "capabilities": [
                {
                    "capabilityId": item.id,
                    "capabilityKey": item.key,
                    "capabilityVersion": item.version,
                }
                for item in capability_rows
            ],
            "mcp_servers": [
                {
                    "mcpServerId": item.id,
                    "mcpServerKey": item.key,
                    "mcpServerVersion": item.version,
                }
                for item in mcp_server_rows
            ],
            "budget_usd": budget_usd,
        }

    def _prepare_manifest_write_or_raise(
        self,
        manifest_source: str,
    ) -> _PreparedAgentManifestWrite:
        try:
            return self._prepare_manifest_write(manifest_source)
        except _AgentManifestDiagnosticsError as exc:
            self._raise_manifest_validation(exc.diagnostics)

    def _prepare_manifest_write(self, manifest_source: str) -> _PreparedAgentManifestWrite:
        parse_result = parse_agent_manifest(manifest_source)
        if parse_result.manifest is None or parse_result.diagnostics:
            raise _AgentManifestDiagnosticsError(parse_result.diagnostics)

        manifest = parse_result.manifest
        try:
            compiled_payload = self.manifest_compiler.compile(manifest_source)
            payload = AgentCreate.model_validate(compiled_payload)
            state = self._build_state(
                name=payload.name,
                description=payload.description,
                model_connection_id=payload.model_connection_id,
                system_prompt=payload.system_prompt,
                input_schema=payload.input_schema,
                output_schema_key=payload.output_schema_key,
                output_schema_version=payload.output_schema_version,
                capabilities=payload.capabilities,
                mcp_servers=payload.mcp_servers,
                budget_usd=payload.budget_usd,
                manifest_api_version=manifest.api_version,
                manifest_source=manifest_source,
                manifest_hash=self._manifest_hash(manifest_source),
                compiler_version=AGENT_MANIFEST_COMPILER_VERSION,
            )
        except AgentManifestCompilerError as exc:
            raise _AgentManifestDiagnosticsError(exc.diagnostics) from exc
        except ApiError as exc:
            raise _AgentManifestDiagnosticsError(
                self._api_error_to_manifest_diagnostics(manifest_source, exc.details)
            ) from exc

        return _PreparedAgentManifestWrite(
            payload=payload,
            state=state,
            manifest_api_version=manifest.api_version,
            manifest_source=manifest_source,
            manifest_hash=self._manifest_hash(manifest_source),
            compiler_version=AGENT_MANIFEST_COMPILER_VERSION,
            compiled_payload=compiled_payload,
        )

    def _api_error_to_manifest_diagnostics(
        self,
        manifest_source: str,
        details: list[dict[str, object]],
    ) -> list[AgentManifestDiagnostic]:
        if not details:
            return [
                self._manifest_diagnostic(
                    manifest_source,
                    "$",
                    "Agent manifest validation failed",
                )
            ]

        diagnostics: list[AgentManifestDiagnostic] = []
        for detail in details:
            field = str(detail.get("field") or "$")
            issue = str(detail.get("issue") or "Invalid agent manifest value")
            diagnostics.append(
                self._manifest_diagnostic(
                    manifest_source,
                    self._agent_field_to_manifest_path(field),
                    issue,
                )
            )
        return diagnostics

    @staticmethod
    def _agent_field_to_manifest_path(field: str) -> str:
        field_map = {
            "modelConnectionId": "spec.modelConnection",
            "inputSchema": "spec.inputSchema",
            "outputSchemaKey": "spec.outputSchema",
            "outputSchemaVersion": "spec.outputSchema",
            "systemPrompt": "spec.systemPrompt",
            "budgetUsd": "spec.budgetUsd",
        }
        if field.startswith("inputSchema."):
            return field.replace("inputSchema", "spec.inputSchema", 1)
        if field.startswith("capabilities["):
            return field.replace("capabilities", "spec.capabilities", 1)
        if field.startswith("mcpServers["):
            return field.replace("mcpServers", "spec.mcpServers", 1)
        return field_map.get(field, field)

    @staticmethod
    def _manifest_diagnostic(
        manifest_source: str,
        path: str,
        message: str,
    ) -> AgentManifestDiagnostic:
        line, column = locate_agent_manifest_path(manifest_source, path)
        return AgentManifestDiagnostic(
            severity=AgentManifestDiagnosticSeverity.ERROR,
            message=message,
            path=path,
            line=line,
            column=column,
        )

    @staticmethod
    def _manifest_diagnostic_detail(diagnostic: AgentManifestDiagnostic) -> dict[str, object]:
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
        diagnostics: list[AgentManifestDiagnostic],
    ) -> NoReturn:
        raise validation_error(
            "Agent manifest validation failed",
            [self._manifest_diagnostic_detail(diagnostic) for diagnostic in diagnostics],
        )

    @staticmethod
    def _manifest_hash(manifest_source: str) -> str:
        return hashlib.sha256(manifest_source.encode("utf-8")).hexdigest()

    def _normalize_input_schema(self, input_schema: JsonObject) -> JsonObject:
        try:
            prepared = self.schema_compiler.normalize_payload(
                builder=None,
                json_schema=input_schema,
            )
        except OutputSchemaValidationFailure as exc:
            raise validation_error(
                "Agent validation failed",
                [self._rewrite_schema_issue(issue) for issue in exc.issues],
            ) from exc

        if prepared.json_schema.get("type") != "object":
            raise validation_error(
                "Agent validation failed",
                [{"field": "inputSchema", "issue": "Input schema must be an object schema"}],
            )

        try:
            _ = self._build_input_model(prepared.json_schema)
        except OutputSchemaCompilerError as exc:
            raise validation_error(
                "Agent validation failed",
                [{"field": "inputSchema", "issue": str(exc)}],
            ) from exc
        return cast(JsonObject, prepared.json_schema)

    def _resolve_output_schema(self, key: str, version: int | None) -> OutputSchema:
        schema = self.output_schema_repository.resolve_version(key, version)
        if schema is None:
            raise validation_error(
                "Agent validation failed",
                [
                    {
                        "field": "outputSchemaKey",
                        "issue": (
                            f"Output schema {key!r} was not found"
                            if version is None
                            else f"Output schema {key!r} version {version} was not found"
                        ),
                    }
                ],
            )
        try:
            _ = self.output_schema_service.compile_schema_model(schema.id)
        except ApiError as exc:
            raise validation_error("Agent validation failed", exc.details) from exc
        return schema

    def _resolve_capability_rows(self, refs: Sequence[AgentCapabilityRefWrite]) -> list[Capability]:
        resolved: list[Capability] = []
        seen: set[tuple[str, int]] = set()
        for index, ref in enumerate(refs):
            field = f"capabilities[{index}].capabilityKey"
            capability = self.capability_repository.resolve_version(
                ref.capability_key,
                ref.capability_version,
            )
            if capability is None:
                issue = (
                    f"Capability {ref.capability_key!r} was not found"
                    if ref.capability_version is None
                    else (
                        f"Capability {ref.capability_key!r} version "
                        f"{ref.capability_version} was not found"
                    )
                )
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": issue}],
                )
            _ = self.capability_service.resolve_toolset_version(
                capability.key,
                capability.version,
            )
            identity = (capability.key, capability.version)
            if identity in seen:
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": "Duplicate capability selection"}],
                )
            seen.add(identity)
            resolved.append(capability)
        return resolved

    def _resolve_mcp_server_rows(self, refs: Sequence[AgentMcpServerRefWrite]) -> list[McpServer]:
        resolved: list[McpServer] = []
        seen: set[tuple[str, int]] = set()
        for index, ref in enumerate(refs):
            server = self.mcp_server_repository.resolve_version(
                ref.mcp_server_key,
                ref.mcp_server_version,
            )
            field = f"mcpServers[{index}].mcpServerKey"
            if server is None:
                issue = (
                    f"MCP server {ref.mcp_server_key!r} version "
                    f"{ref.mcp_server_version} was not found"
                )
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": issue}],
                )
            if server.status not in {"published", "deprecated"}:
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": "MCP server must be published or deprecated"}],
                )
            _ = self.mcp_server_service.build_client_boundary_version(
                server.key,
                server.version,
                require_enabled=True,
            )
            identity = (server.key, server.version)
            if identity in seen:
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": "Duplicate MCP server selection"}],
                )
            seen.add(identity)
            resolved.append(server)
        return resolved

    def _resolve_model_connection_for_save(self, connection_id: int) -> ModelConnection:
        connection = self.model_connection_repository.get(connection_id)
        if connection is None:
            raise validation_error(
                "Agent validation failed",
                [
                    {
                        "field": "modelConnectionId",
                        "issue": f"Model connection {connection_id} was not found",
                    }
                ],
            )
        return connection

    def _raise_structured_write_unsupported(self) -> NoReturn:
        raise validation_error(
            "Structured agent writes are not supported",
            [
                {
                    "field": "manifestSource",
                    "issue": (
                        "Agent create/update writes must use signaldeck.agent/v1 manifest source"
                    ),
                }
            ],
        )

    def _resolve_stored_model_connection_row(self, agent: Agent) -> ModelConnection:
        model_connection_id = cast(int | None, agent.model_connection_id)
        if model_connection_id is None:
            raise business_rule_error(
                "agent_model_connection_missing",
                f"Agent {agent.key!r} is missing its saved model connection",
            )
        connection = self.model_connection_repository.get(model_connection_id)
        if connection is None:
            raise business_rule_error(
                "agent_model_connection_missing",
                (f"Agent {agent.key!r} references missing model connection {model_connection_id}"),
            )
        return connection

    def _resolve_model(self, agent_id: int, *, version: int | None) -> Agent:
        anchor = self._get_model(agent_id)
        if version is None:
            return anchor
        agent = self.repository.get_by_key_version(anchor.key, version)
        if agent is None:
            raise not_found_error("Agent")
        return agent

    def _get_model(self, agent_id: int) -> Agent:
        agent = self.repository.get(agent_id)
        if agent is None:
            raise not_found_error("Agent")
        return agent

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _build_input_model(self, input_schema: JsonObject) -> type[BaseModel]:
        candidate = OutputSchema(
            key="agent_input_schema_validation",
            version=1,
            status=AgentStatus.PUBLISHED.value,
            kind="standalone",
            name="Agent Input Schema",
            description="Agent input schema validation candidate",
            json_schema=input_schema,
            registry_refs=[],
        )
        return self.schema_compiler.build_runtime_model(candidate)

    def _to_read_model(self, agent: Agent) -> AgentRead:
        output_schema_row = self.output_schema_repository.get(agent.output_schema_id)
        if output_schema_row is None or output_schema_row.version != agent.output_schema_version:
            raise business_rule_error(
                "agent_output_schema_missing",
                f"Agent {agent.key!r} references a missing output schema version",
            )

        output_schema = self.output_schema_service.get_schema(output_schema_row.id)
        model_connection_row = self._resolve_stored_model_connection_row(agent)
        model_connection = ModelConnectionListItemRead.model_validate(model_connection_row)
        try:
            parsed_model_connection_snapshot = parse_model_connection_runtime_snapshot(
                agent.model_connection_snapshot
            )
            model_connection_snapshot = snapshot_to_json(parsed_model_connection_snapshot)
            model_connection_snapshot["connection_kind"] = model_connection.connection_kind.value
        except ValueError as exc:
            raise business_rule_error(
                "agent_model_connection_snapshot_invalid",
                f"Agent {agent.key!r} has an invalid saved model connection snapshot",
            ) from exc
        stored_capability_rows = self._resolve_stored_capability_rows(agent.capabilities)
        capabilities = [
            self.capability_service.get_capability(capability.id)
            for capability in stored_capability_rows
        ]
        mcp_servers = [
            self._to_mcp_server_read(server)
            for server in self._resolve_stored_mcp_server_rows(agent.mcp_servers)
        ]
        return AgentRead.model_validate(
            {
                "id": agent.id,
                "key": agent.key,
                "version": agent.version,
                "status": agent.status,
                "name": agent.name,
                "description": agent.description,
                "manifestApiVersion": agent.manifest_api_version,
                "manifestSource": agent.manifest_source,
                "manifestHash": agent.manifest_hash,
                "compilerVersion": agent.compiler_version,
                "modelConnectionId": model_connection.id,
                "modelConnection": model_connection,
                "modelConnectionSnapshot": model_connection_snapshot,
                "systemPrompt": agent.system_prompt,
                "inputSchema": agent.input_schema,
                "outputSchema": output_schema,
                "capabilities": capabilities,
                "mcpServers": mcp_servers,
                "budgetUsd": agent.budget_usd,
                "createdAt": agent.created_at,
                "updatedAt": agent.updated_at,
            }
        )

    def _resolve_stored_capability_rows(
        self,
        raw_refs: Sequence[Mapping[str, object]],
    ) -> list[Capability]:
        rows: list[Capability] = []
        for raw_ref in raw_refs:
            version = self._coerce_stored_ref_version(raw_ref.get("capabilityVersion"))
            row = self.capability_repository.get_by_key_version(
                str(raw_ref["capabilityKey"]),
                version,
            )
            if row is None:
                raise business_rule_error(
                    "agent_capability_reference_missing",
                    "Agent references a missing capability version",
                )
            rows.append(row)
        return rows

    def _resolve_stored_mcp_server_rows(
        self,
        raw_refs: Sequence[Mapping[str, object]],
    ) -> list[McpServer]:
        rows: list[McpServer] = []
        for raw_ref in raw_refs:
            version = self._coerce_stored_ref_version(raw_ref.get("mcpServerVersion"))
            row = self.mcp_server_repository.get_by_key_version(
                str(raw_ref["mcpServerKey"]),
                version,
            )
            if row is None:
                raise business_rule_error(
                    "agent_mcp_server_reference_missing",
                    "Agent references a missing MCP server version",
                )
            rows.append(row)
        return rows

    @staticmethod
    def _coerce_stored_ref_version(value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value)
        raise business_rule_error(
            "agent_reference_invalid",
            "Agent references an invalid catalog version",
        )

    def _to_mcp_server_read(self, server: McpServer) -> AgentMcpServerRead:
        boundary = self.mcp_server_service.build_client_boundary_version(server.key, server.version)
        return AgentMcpServerRead.model_validate(
            {
                "id": server.id,
                "key": server.key,
                "version": server.version,
                "status": server.status,
                "name": server.name,
                "description": server.description,
                "transport": server.transport,
                "enabled": server.enabled,
                "boundary": self._boundary_to_read(boundary),
            }
        )

    @staticmethod
    def _boundary_to_read(boundary: McpClientBoundary) -> McpClientBoundaryRead:
        return McpClientBoundaryRead.model_validate(
            {
                "transport": boundary.transport,
                "command": list(boundary.command) if boundary.command is not None else None,
                "url": boundary.url,
                "headerNames": sorted(boundary.headers),
                "envKeys": sorted(boundary.env),
                "enabled": boundary.enabled,
            }
        )

    @staticmethod
    def _rewrite_schema_issue(issue: dict[str, str]) -> dict[str, str]:
        field = issue.get("field", "inputSchema")
        if field == "jsonSchema":
            mapped_field = "inputSchema"
        elif field.startswith("jsonSchema."):
            mapped_field = field.replace("jsonSchema", "inputSchema", 1)
        else:
            mapped_field = field
        return {"field": mapped_field, "issue": issue.get("issue", "Invalid schema")}


__all__ = ["AgentService"]
