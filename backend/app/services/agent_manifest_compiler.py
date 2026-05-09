# pyright: reportMissingImports=false

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.repositories.capability import CapabilityRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.schemas.agent import AgentCreate
from app.schemas.agent_manifest import (
    AgentManifest,
    AgentManifestDiagnostic,
    AgentManifestDiagnosticSeverity,
    AgentManifestPinnedRef,
    JsonValue,
)
from app.services.agent_manifest_parser import locate_agent_manifest_path, parse_agent_manifest
from app.services.output_schema_compiler import OutputSchemaCompiler, OutputSchemaValidationFailure


class AgentManifestCompilerError(ValueError):
    def __init__(self, diagnostics: list[AgentManifestDiagnostic]) -> None:
        super().__init__("Agent manifest could not be compiled")
        self.diagnostics: list[AgentManifestDiagnostic] = diagnostics


class AgentManifestCompiler:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.model_connection_repository: ModelConnectionRepository = ModelConnectionRepository(
            session
        )
        self.output_schema_repository: OutputSchemaRepository = OutputSchemaRepository(session)
        self.capability_repository: CapabilityRepository = CapabilityRepository(session)
        self.mcp_server_repository: McpServerRepository = McpServerRepository(session)
        self.schema_compiler: OutputSchemaCompiler = OutputSchemaCompiler(
            self.output_schema_repository
        )

    def compile(self, source: str | AgentManifest) -> dict[str, object]:
        manifest, source_text = self._resolve_manifest(source)
        diagnostics: list[AgentManifestDiagnostic] = []

        model_connection: ModelConnection | None = self.model_connection_repository.get_by_key(
            manifest.spec.model_connection
        )
        if model_connection is None:
            diagnostics.append(
                self._diagnostic(
                    f"Model connection {manifest.spec.model_connection!r} was not found",
                    path="spec.modelConnection",
                    source=source_text,
                )
            )

        input_schema = manifest.spec.input_schema
        try:
            prepared_schema = self.schema_compiler.normalize_payload(
                builder=None,
                json_schema=input_schema,
            )
            input_schema = cast(dict[str, JsonValue], prepared_schema.json_schema)
        except OutputSchemaValidationFailure as exc:
            diagnostics.extend(
                self._diagnostic(
                    issue.get("issue", "Invalid input schema"),
                    path=self._input_schema_issue_path(issue.get("field", "jsonSchema")),
                    source=source_text,
                )
                for issue in exc.issues
            )

        output_schema = self._resolve_output_schema(
            manifest.spec.output_schema,
            source=source_text,
            diagnostics=diagnostics,
        )
        capabilities = self._resolve_capabilities(
            manifest,
            source=source_text,
            diagnostics=diagnostics,
        )
        mcp_servers = self._resolve_mcp_servers(
            manifest,
            source=source_text,
            diagnostics=diagnostics,
        )

        if diagnostics:
            raise AgentManifestCompilerError(diagnostics)
        if model_connection is None or output_schema is None:
            raise AgentManifestCompilerError(diagnostics)

        payload = {
            "key": manifest.metadata.key,
            "name": manifest.metadata.name,
            "description": manifest.metadata.description,
            "modelConnectionId": model_connection.id,
            "systemPrompt": manifest.spec.system_prompt,
            "inputSchema": input_schema,
            "outputSchemaKey": output_schema.key,
            "outputSchemaVersion": output_schema.version,
            "capabilities": [
                {"capabilityKey": capability.key, "capabilityVersion": capability.version}
                for capability in capabilities
            ],
            "mcpServers": [
                {"mcpServerKey": server.key, "mcpServerVersion": server.version}
                for server in mcp_servers
            ],
            "budgetUsd": manifest.spec.budget_usd,
        }
        return cast(
            dict[str, object],
            AgentCreate.model_validate(payload).model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        )

    def _resolve_manifest(self, source: str | AgentManifest) -> tuple[AgentManifest, str | None]:
        if isinstance(source, AgentManifest):
            return source, None
        result = parse_agent_manifest(source)
        if result.manifest is None or result.diagnostics:
            raise AgentManifestCompilerError(result.diagnostics)
        return result.manifest, source

    def _resolve_output_schema(
        self,
        ref: AgentManifestPinnedRef,
        *,
        source: str | None,
        diagnostics: list[AgentManifestDiagnostic],
    ) -> OutputSchema | None:
        schema = self.output_schema_repository.get_by_key_version(ref.key, ref.version)
        if schema is None:
            diagnostics.append(
                self._diagnostic(
                    f"Output schema {ref.key!r} version {ref.version} was not found",
                    path="spec.outputSchema",
                    source=source,
                )
            )
            return None
        return schema

    def _resolve_capabilities(
        self,
        manifest: AgentManifest,
        *,
        source: str | None,
        diagnostics: list[AgentManifestDiagnostic],
    ) -> list[Capability]:
        rows: list[Capability] = []
        for index, ref in enumerate(manifest.spec.capabilities):
            row = self.capability_repository.get_by_key_version(ref.key, ref.version)
            if row is None:
                diagnostics.append(
                    self._diagnostic(
                        f"Capability {ref.key!r} version {ref.version} was not found",
                        path=f"spec.capabilities[{index}]",
                        source=source,
                    )
                )
                continue
            rows.append(row)
        return rows

    def _resolve_mcp_servers(
        self,
        manifest: AgentManifest,
        *,
        source: str | None,
        diagnostics: list[AgentManifestDiagnostic],
    ) -> list[McpServer]:
        rows: list[McpServer] = []
        for index, ref in enumerate(manifest.spec.mcp_servers):
            row = self.mcp_server_repository.resolve_version(ref.key, ref.version, enabled=True)
            if row is None:
                diagnostics.append(
                    self._diagnostic(
                        f"Enabled MCP server {ref.key!r} version {ref.version} was not found",
                        path=f"spec.mcpServers[{index}]",
                        source=source,
                    )
                )
                continue
            rows.append(row)
        return rows

    @staticmethod
    def _input_schema_issue_path(field: str) -> str:
        if field == "jsonSchema":
            return "spec.inputSchema"
        if field.startswith("jsonSchema."):
            return field.replace("jsonSchema", "spec.inputSchema", 1)
        return f"spec.inputSchema.{field}"

    @staticmethod
    def _diagnostic(message: str, *, path: str, source: str | None) -> AgentManifestDiagnostic:
        line, column = (
            locate_agent_manifest_path(source, path) if source is not None else (None, None)
        )
        return AgentManifestDiagnostic(
            severity=AgentManifestDiagnosticSeverity.ERROR,
            message=message,
            path=path,
            line=line,
            column=column,
        )


def compile_agent_manifest(source: str | AgentManifest, session: Session) -> dict[str, object]:
    return AgentManifestCompiler(session).compile(source)


__all__ = ["AgentManifestCompiler", "AgentManifestCompilerError", "compile_agent_manifest"]
