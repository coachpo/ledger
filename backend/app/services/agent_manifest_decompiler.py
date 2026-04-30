# pyright: reportMissingImports=false, reportUnknownMemberType=false

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import StringIO
from typing import Protocol, cast

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.schemas.agent import AgentCreate
from app.schemas.agent_manifest import AGENT_MANIFEST_API_VERSION
from app.services.agent_manifest_compiler import compile_agent_manifest

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class AgentManifestDecompilerError(ValueError):
    pass


class AgentManifestSource(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def model_connection_id(self) -> int: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def input_schema(self) -> dict[str, JsonValue]: ...

    @property
    def output_schema_id(self) -> int: ...

    @property
    def output_schema_version(self) -> int: ...

    @property
    def skills(self) -> list[dict[str, JsonValue]]: ...

    @property
    def mcp_servers(self) -> list[dict[str, JsonValue]]: ...

    @property
    def budget_usd(self) -> Decimal: ...


@dataclass(frozen=True)
class AgentManifestDecompileResult:
    source: str
    payload: dict[str, object]


class AgentManifestDecompiler:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.model_connection_repository: ModelConnectionRepository = ModelConnectionRepository(
            session
        )
        self.output_schema_repository: OutputSchemaRepository = OutputSchemaRepository(session)

    def decompile(
        self,
        agent: AgentManifestSource,
        *,
        verify_lossless: bool = True,
    ) -> AgentManifestDecompileResult:
        payload = self._project_agent_payload(agent)
        manifest: dict[str, object] = {
            "apiVersion": AGENT_MANIFEST_API_VERSION,
            "kind": "Agent",
            "metadata": {
                "key": payload["key"],
                "name": payload["name"],
                "description": payload["description"],
            },
            "spec": {
                "modelConnection": self._model_connection_key(agent.model_connection_id),
                "systemPrompt": LiteralScalarString(str(payload["systemPrompt"])),
                "inputSchema": payload["inputSchema"],
                "outputSchema": self._output_schema_pin(
                    agent.output_schema_id,
                    agent.output_schema_version,
                ),
                "capabilities": _sorted_pins(
                    cast(list[dict[str, object]], payload["capabilities"]),
                    "capability",
                ),
                "mcpServers": _sorted_pins(
                    cast(list[dict[str, object]], payload["mcpServers"]),
                    "mcpServer",
                ),
                "budgetUsd": DoubleQuotedScalarString(str(payload["budgetUsd"])),
            },
        }
        source = _dump_manifest_yaml(manifest)
        if verify_lossless:
            compiled_payload = compile_agent_manifest(source, self.session)
            if compiled_payload != payload:
                raise AgentManifestDecompilerError(
                    "Decompiled manifest did not round-trip losslessly"
                )
        return AgentManifestDecompileResult(source=source, payload=payload)

    def _project_agent_payload(self, agent: AgentManifestSource) -> dict[str, object]:
        payload = {
            "key": agent.key,
            "name": agent.name,
            "description": agent.description,
            "modelConnectionId": agent.model_connection_id,
            "systemPrompt": agent.system_prompt,
            "inputSchema": agent.input_schema,
            "outputSchemaKey": self._output_schema_key(
                agent.output_schema_id,
                agent.output_schema_version,
            ),
            "outputSchemaVersion": agent.output_schema_version,
            "capabilities": [
                {
                    "capabilityKey": item.get("skillKey"),
                    "capabilityVersion": item.get("skillVersion"),
                }
                for item in agent.skills
            ],
            "skills": [
                {
                    "skillKey": item.get("skillKey"),
                    "skillVersion": item.get("skillVersion"),
                }
                for item in agent.skills
            ],
            "mcpServers": [
                {
                    "mcpServerKey": item.get("mcpServerKey"),
                    "mcpServerVersion": item.get("mcpServerVersion"),
                }
                for item in agent.mcp_servers
            ],
            "budgetUsd": str(agent.budget_usd),
        }
        try:
            return cast(
                dict[str, object],
                AgentCreate.model_validate(payload).model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
            )
        except ValidationError as exc:
            raise AgentManifestDecompilerError(str(exc)) from exc

    def _model_connection_key(self, model_connection_id: int) -> str:
        row = self.model_connection_repository.get(model_connection_id)
        if row is None:
            raise AgentManifestDecompilerError(
                f"Agent references missing model connection {model_connection_id}"
            )
        return row.key

    def _output_schema_key(self, output_schema_id: int, output_schema_version: int) -> str:
        row = self.output_schema_repository.get(output_schema_id)
        if row is None or row.version != output_schema_version:
            raise AgentManifestDecompilerError("Agent references a missing output schema version")
        return row.key

    def _output_schema_pin(self, output_schema_id: int, output_schema_version: int) -> str:
        key = self._output_schema_key(output_schema_id, output_schema_version)
        return f"{key}@{output_schema_version}"


def decompile_agent_manifest(
    agent: AgentManifestSource,
    session: Session,
    *,
    verify_lossless: bool = True,
) -> AgentManifestDecompileResult:
    return AgentManifestDecompiler(session).decompile(agent, verify_lossless=verify_lossless)


def decompile_agent_model(
    agent: Agent,
    session: Session,
    *,
    verify_lossless: bool = True,
) -> AgentManifestDecompileResult:
    return decompile_agent_manifest(
        cast(AgentManifestSource, cast(object, agent)),
        session,
        verify_lossless=verify_lossless,
    )


def _sorted_pins(refs: list[dict[str, object]], prefix: str) -> list[str]:
    key_name = f"{prefix}Key"
    version_name = f"{prefix}Version"
    pins = [f"{ref[key_name]}@{ref[version_name]}" for ref in refs]
    return sorted(pins)


def _dump_manifest_yaml(manifest: dict[str, object]) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    yaml.dump(manifest, stream)
    return stream.getvalue()


__all__ = [
    "AgentManifestDecompileResult",
    "AgentManifestDecompiler",
    "AgentManifestDecompilerError",
    "decompile_agent_manifest",
    "decompile_agent_model",
]
