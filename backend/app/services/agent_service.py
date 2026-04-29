from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

from fastapi import status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents import SkillRegistry
from app.agents.mcp import McpClientBoundary, McpConnectionTester
from app.core.errors import ApiError, business_rule_error, not_found_error, validation_error
from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.skill import Skill
from app.repositories.agent import AgentRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.skill import SkillRepository
from app.schemas.agent import (
    AgentCreate,
    AgentListRead,
    AgentMcpServerRead,
    AgentMcpServerRefWrite,
    AgentRead,
    AgentSkillRefWrite,
    AgentStatus,
    AgentUpdate,
)
from app.schemas.mcp_server import McpClientBoundaryRead
from app.schemas.model_connection import ModelConnectionListItemRead, ModelConnectionStatus
from app.schemas.run import RunCreatedRead
from app.services.mcp_server_service import McpServerService
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
)
from app.services.output_schema_service import OutputSchemaService
from app.services.run_service import RunService
from app.services.skill_service import SkillService

type JsonValue = (str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"])
type JsonObject = dict[str, JsonValue]


class AgentService:
    def __init__(
        self,
        session: Session,
        skill_registry: SkillRegistry,
        connection_tester: McpConnectionTester,
    ) -> None:
        self.session: Session = session
        self.repository: AgentRepository = AgentRepository(session)
        self.output_schema_repository: OutputSchemaRepository = OutputSchemaRepository(session)
        self.skill_repository: SkillRepository = SkillRepository(session)
        self.mcp_server_repository: McpServerRepository = McpServerRepository(session)
        self.model_connection_repository: ModelConnectionRepository = ModelConnectionRepository(
            session
        )
        self.skill_service: SkillService = SkillService(session, skill_registry)
        self.mcp_server_service: McpServerService = McpServerService(session, connection_tester)
        self.output_schema_service: OutputSchemaService = OutputSchemaService(session)
        self.schema_compiler: OutputSchemaCompiler = OutputSchemaCompiler(
            self.output_schema_repository
        )

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

    def create_agent(self, payload: AgentCreate) -> AgentRead:
        if self.repository.list_versions(payload.key):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="agent_duplicate_key",
                message="An agent with this key already exists",
            )

        state = self._build_state(
            name=payload.name,
            description=payload.description,
            model_connection_id=payload.model_connection_id,
            system_prompt=payload.system_prompt,
            input_schema=payload.input_schema,
            output_schema_key=payload.output_schema_key,
            output_schema_version=payload.output_schema_version,
            skills=payload.skills,
            mcp_servers=payload.mcp_servers,
            budget_usd=payload.budget_usd,
        )
        agent = Agent(key=payload.key, version=1, status=AgentStatus.PUBLISHED.value, **state)
        try:
            _ = self.repository.add(agent)
            self.session.commit()
            self.session.refresh(agent)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(agent)

    def update_agent(self, agent_id: int, payload: AgentUpdate) -> AgentRead:
        source = self._get_model(agent_id)
        state = self._build_state(
            name=payload.name,
            description=payload.description,
            model_connection_id=payload.model_connection_id,
            system_prompt=payload.system_prompt,
            input_schema=payload.input_schema,
            output_schema_key=payload.output_schema_key,
            output_schema_version=payload.output_schema_version,
            skills=payload.skills,
            mcp_servers=payload.mcp_servers,
            budget_usd=payload.budget_usd,
        )
        agent = Agent(
            key=source.key,
            version=self._next_version(source.key),
            status=AgentStatus.PUBLISHED.value,
            **state,
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

    def archive_agent(self, agent_id: int) -> AgentRead:
        agent = self._get_model(agent_id)
        if agent.status == AgentStatus.ARCHIVED.value:
            return self._to_read_model(agent)

        try:
            agent.status = AgentStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(agent)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(agent)

    def create_run(
        self,
        agent_id: int,
        payload: JsonObject,
        *,
        version: int | None = None,
    ) -> RunCreatedRead:
        return RunService(self.session).create_target_run(
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
        skills: Sequence[AgentSkillRefWrite],
        mcp_servers: Sequence[AgentMcpServerRefWrite],
        budget_usd: Decimal,
    ) -> dict[str, object]:
        normalized_input_schema = self._normalize_input_schema(input_schema)
        output_schema = self._resolve_output_schema(output_schema_key, output_schema_version)
        skill_rows = self._resolve_skill_rows(skills)
        mcp_server_rows = self._resolve_mcp_server_rows(mcp_servers)
        model_connection = self._resolve_model_connection_for_save(model_connection_id)
        return {
            "name": name,
            "description": description,
            "model_connection_id": model_connection.id,
            "model": model_connection.model_id,
            "system_prompt": system_prompt,
            "input_schema": normalized_input_schema,
            "output_schema_id": output_schema.id,
            "output_schema_version": output_schema.version,
            "skills": [
                {"skillId": item.id, "skillKey": item.key, "skillVersion": item.version}
                for item in skill_rows
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

    def _resolve_skill_rows(self, refs: Sequence[AgentSkillRefWrite]) -> list[Skill]:
        resolved: list[Skill] = []
        seen: set[tuple[str, int]] = set()
        for index, ref in enumerate(refs):
            field = f"skills[{index}].skillKey"
            skill = self.skill_repository.resolve_version(ref.skill_key, ref.skill_version)
            if skill is None:
                issue = (
                    f"Skill {ref.skill_key!r} was not found"
                    if ref.skill_version is None
                    else f"Skill {ref.skill_key!r} version {ref.skill_version} was not found"
                )
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": issue}],
                )
            _ = self.skill_service.resolve_toolset_version(skill.key, skill.version)
            identity = (skill.key, skill.version)
            if identity in seen:
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": "Duplicate skill selection"}],
                )
            seen.add(identity)
            resolved.append(skill)
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
                    f"MCP server {ref.mcp_server_key!r} was not found"
                    if ref.mcp_server_version is None
                    else (
                        f"MCP server {ref.mcp_server_key!r} version {ref.mcp_server_version} "
                        "was not found"
                    )
                )
                raise validation_error(
                    "Agent validation failed",
                    [{"field": field, "issue": issue}],
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
        if connection.status != ModelConnectionStatus.ACTIVE.value:
            raise validation_error(
                "Agent validation failed",
                [
                    {
                        "field": "modelConnectionId",
                        "issue": "Archived model connections cannot be selected",
                    }
                ],
            )
        return connection

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
                (
                    f"Agent {agent.key!r} references missing model connection "
                    f"{model_connection_id}"
                ),
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
        model_connection = ModelConnectionListItemRead.model_validate(
            self._resolve_stored_model_connection_row(agent)
        )
        skills = [
            self.skill_service.get_skill(skill.id)
            for skill in self._resolve_stored_skill_rows(agent.skills)
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
                "modelConnectionId": model_connection.id,
                "modelConnection": model_connection,
                "systemPrompt": agent.system_prompt,
                "inputSchema": agent.input_schema,
                "outputSchema": output_schema,
                "skills": skills,
                "mcpServers": mcp_servers,
                "budgetUsd": agent.budget_usd,
                "createdAt": agent.created_at,
                "updatedAt": agent.updated_at,
            }
        )

    def _resolve_stored_skill_rows(self, raw_refs: Sequence[Mapping[str, object]]) -> list[Skill]:
        rows: list[Skill] = []
        for raw_ref in raw_refs:
            version = self._coerce_stored_ref_version(raw_ref.get("skillVersion"))
            row = self.skill_repository.get_by_key_version(
                str(raw_ref["skillKey"]),
                version,
            )
            if row is None:
                raise business_rule_error(
                    "agent_skill_reference_missing",
                    "Agent references a missing skill version",
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
