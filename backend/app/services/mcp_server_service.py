from __future__ import annotations

from fastapi import status
from sqlalchemy.orm import Session

from app.agents.mcp import (
    McpClientBoundary,
    McpClientConfigError,
    McpConnectionTester,
    build_mcp_client_boundary,
)
from app.core.errors import ApiError, not_found_error, validation_error
from app.models.mcp_server import McpServer
from app.repositories.mcp_server import McpServerRepository
from app.schemas.mcp_server import (
    McpClientBoundaryRead,
    McpServerConfigEnvelope,
    McpServerConnectionTestRead,
    McpServerDraftCreate,
    McpServerDraftUpdate,
    McpServerListItemRead,
    McpServerListRead,
    McpServerRead,
    McpServerStatus,
    McpServerTransport,
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
        return McpServerRead.model_validate(self._get_model(server_id))

    def create_draft(self, payload: McpServerDraftCreate) -> McpServerRead:
        if self.repository.get_draft_by_key(payload.server_key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="mcp_server_duplicate_draft",
                message="A draft MCP server already exists for this key",
            )

        server = McpServer(
            key=payload.server_key,
            version=self._next_version(payload.server_key),
            status=McpServerStatus.DRAFT.value,
            config=self._validated_config_payload(payload),
        )
        try:
            self.repository.add(server)
            self.session.commit()
            self.session.refresh(server)
        except Exception:
            self.session.rollback()
            raise
        return McpServerRead.model_validate(server)

    def update_draft(self, server_id: int, payload: McpServerDraftUpdate) -> McpServerRead:
        source = self._get_model(server_id)
        self._ensure_status(source, McpServerStatus.DRAFT, action="patch")
        self._ensure_immutable_key(source, payload)

        updated = McpServer(
            key=source.key,
            version=self._next_version(source.key),
            status=McpServerStatus.DRAFT.value,
            config=self._validated_config_payload(payload),
        )
        try:
            source.status = McpServerStatus.ARCHIVED.value
            self.session.flush()
            self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return McpServerRead.model_validate(updated)

    def activate(self, server_id: int) -> McpServerRead:
        server = self._get_model(server_id)
        self._ensure_status(server, McpServerStatus.DRAFT, action="activate")
        self._build_boundary_model(server)

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
        return McpServerRead.model_validate(server)

    def archive(self, server_id: int) -> McpServerRead:
        server = self._get_model(server_id)
        if server.status == McpServerStatus.ARCHIVED.value:
            return McpServerRead.model_validate(server)

        try:
            server.status = McpServerStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(server)
        except Exception:
            self.session.rollback()
            raise
        return McpServerRead.model_validate(server)

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

    def _validated_config_payload(self, payload: McpServerConfigEnvelope) -> dict[str, object]:
        config_payload = payload.model_dump(mode="json", by_alias=True)
        candidate = McpServer(
            key=payload.server_key,
            version=1,
            status=McpServerStatus.DRAFT.value,
            config=config_payload,
        )
        self._build_boundary_model(candidate)
        return config_payload

    @staticmethod
    def _ensure_immutable_key(server: McpServer, payload: McpServerConfigEnvelope) -> None:
        if payload.server_key != server.key:
            raise validation_error(
                "MCP server validation failed",
                [
                    {
                        "field": "mcpServers",
                        "issue": "PATCH payload key must match the persisted MCP server key",
                    }
                ],
            )

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
