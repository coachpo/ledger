from __future__ import annotations

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.mcp import (
    McpClientBoundary,
    McpClientConfigError,
    McpConnectionTester,
    build_mcp_client_boundary,
)
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.platform_reference import AgentMcpServerRef
from app.repositories.mcp_server import McpServerRepository
from app.schemas.mcp_server import (
    McpClientBoundaryRead,
    McpServerBase,
    McpServerConnectionTestRead,
    McpServerCreate,
    McpServerListItemRead,
    McpServerListRead,
    McpServerRead,
    McpServerStatus,
    McpServerTransport,
    McpServerUpdate,
)


class McpServerService:
    def __init__(self, session: Session, connection_tester: McpConnectionTester) -> None:
        self.session = session
        self.repository = McpServerRepository(session)
        self.connection_tester = connection_tester

    def list_servers(
        self,
        *,
        status_filter: McpServerStatus | None = None,
        enabled: bool | None = None,
        transport: McpServerTransport | None = None,
    ) -> McpServerListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None,
            enabled=enabled,
            transport=transport.value if transport is not None else None,
        )
        return McpServerListRead(
            items=[McpServerListItemRead.model_validate(item) for item in items]
        )

    def get_server(self, server_id: int) -> McpServerRead:
        return self._to_read_model(self._get_model(server_id))

    def create_draft(self, payload: McpServerCreate) -> McpServerRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="mcp_server_duplicate_draft",
                message="A draft MCP server already exists for this key",
            )

        server = McpServer(
            key=payload.key,
            version=self._next_version(payload.key),
            status=McpServerStatus.DRAFT.value,
            config=self._validated_config_payload(payload, key=payload.key),
        )
        try:
            _ = self.repository.add(server)
            self.session.commit()
            self.session.refresh(server)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(server)

    def update_draft(self, server_id: int, payload: McpServerUpdate) -> McpServerRead:
        source = self._get_model(server_id)
        self._ensure_status(source, McpServerStatus.DRAFT, action="patch")

        updated = McpServer(
            key=source.key,
            version=self._next_version(source.key),
            status=McpServerStatus.DRAFT.value,
            config=self._validated_config_payload(payload, key=source.key),
        )
        try:
            self.repository.delete(source)
            self.session.flush()
            _ = self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(updated)

    def activate(self, server_id: int) -> McpServerRead:
        server = self._get_model(server_id)
        self._ensure_status(server, McpServerStatus.DRAFT, action="activate")
        _ = self._build_boundary_model(server)

        current_published = self.repository.get_published_by_key(server.key)
        try:
            if current_published is not None and current_published.id != server.id:
                current_published.status = McpServerStatus.DEPRECATED.value
                self.session.flush()
            server.status = McpServerStatus.PUBLISHED.value
            self.session.commit()
            self.session.refresh(server)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(server)

    def delete_server(self, server_id: int) -> None:
        server = self._get_model(server_id)
        agent_refs = self._agent_reference_details(server.id)
        if agent_refs:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="mcp_server_delete_blocked",
                message="MCP server is referenced by agents",
                details=agent_refs,
            )

        try:
            self.repository.delete(server)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _agent_reference_details(self, server_id: int) -> list[dict[str, object]]:
        statement = (
            select(Agent)
            .join(AgentMcpServerRef, Agent.id == AgentMcpServerRef.agent_id)
            .where(AgentMcpServerRef.mcp_server_id == server_id)
            .order_by(Agent.key.asc(), Agent.version.desc(), Agent.id.asc())
        )
        return [
            {
                "field": "agentId",
                "issue": "MCP server is referenced by agent",
                "agentId": agent.id,
                "agentKey": agent.key,
                "agentVersion": agent.version,
            }
            for agent in self.session.scalars(statement)
        ]

    def build_client_boundary(self, server_id: int) -> McpClientBoundary:
        return self._build_boundary_model(self._get_model(server_id))

    def build_client_boundary_version(
        self,
        key: str,
        version: int | None,
        *,
        require_enabled: bool = False,
    ) -> McpClientBoundary:
        server = self.repository.resolve_version(
            key,
            version,
            enabled=True if require_enabled else None,
        )
        if server is None:
            raise not_found_error("MCP server")
        if require_enabled and not server.enabled:
            raise validation_error(
                "MCP server validation failed",
                [{"field": "enabled", "issue": "MCP server must be enabled"}],
            )
        return self._build_boundary_model(server)

    def test_connection(self, server_id: int) -> McpServerConnectionTestRead:
        boundary = self.build_client_boundary(server_id)
        result = self.connection_tester.test(boundary)
        return McpServerConnectionTestRead.model_validate(
            {
                "serverId": server_id,
                "ok": result.ok,
                "message": result.message,
                "boundary": self._boundary_to_read(boundary),
            }
        )

    def _validated_config_payload(self, payload: McpServerBase, *, key: str) -> dict[str, object]:
        config_payload = self._payload_to_config(payload)
        candidate = McpServer(
            key=key,
            version=1,
            status=McpServerStatus.DRAFT.value,
            config=config_payload,
        )
        _ = self._build_boundary_model(candidate)
        return config_payload

    @staticmethod
    def _payload_to_config(payload: McpServerBase) -> dict[str, object]:
        resource: dict[str, object] = {
            "name": payload.name,
            "description": payload.description,
            "enabled": payload.enabled,
            "transport": payload.transport.value,
        }
        if payload.transport == McpServerTransport.STDIO:
            resource.update(
                {
                    "command": getattr(payload, "command", None),
                    "args": list(getattr(payload, "args", [])),
                    "env": dict(getattr(payload, "env", {})),
                }
            )
        else:
            resource.update(
                {
                    "url": getattr(payload, "url", None),
                    "headers": dict(getattr(payload, "headers", {})),
                }
            )
        return resource

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, server_id: int) -> McpServer:
        server = self.repository.get(server_id)
        if server is None:
            raise not_found_error("MCP server")
        return server

    @staticmethod
    def _ensure_status(server: McpServer, expected: McpServerStatus, *, action: str) -> None:
        if server.status != expected.value:
            raise validation_error(
                "MCP server validation failed",
                [
                    {
                        "field": "status",
                        "issue": f"Only {expected.value} MCP servers can be used for {action}",
                    }
                ],
            )

    @staticmethod
    def _build_boundary_model(server: McpServer) -> McpClientBoundary:
        try:
            return build_mcp_client_boundary(server)
        except McpClientConfigError as exc:
            raise validation_error("MCP server validation failed", exc.details) from exc

    def _to_read_model(self, server: McpServer) -> McpServerRead:
        boundary = self._build_boundary_model(server)
        snapshots = server.flat_config.get("toolSnapshots", [])
        if not isinstance(snapshots, list):
            snapshots = []
        return McpServerRead.model_validate(
            {
                "id": server.id,
                "key": server.key,
                "version": server.version,
                "status": server.status,
                "name": server.name,
                "description": server.description,
                "enabled": server.enabled,
                "transport": server.transport,
                "createdAt": server.created_at,
                "updatedAt": server.updated_at,
                "command": list(boundary.command) if boundary.command is not None else None,
                "url": boundary.url,
                "headerNames": sorted(boundary.headers),
                "envKeys": sorted(boundary.env),
                "toolSnapshots": snapshots,
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


__all__ = ["McpServerService"]
