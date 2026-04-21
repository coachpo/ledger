from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_mcp_server_service
from app.schemas.mcp_server import (
    McpServerConnectionTestRead,
    McpServerCreate,
    McpServerListRead,
    McpServerRead,
    McpServerStatus,
    McpServerTransport,
    McpServerUpdate,
)
from app.services.mcp_server_service import McpServerService

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


@router.get("", response_model=McpServerListRead)
def list_mcp_servers(
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
    status_filter: Annotated[McpServerStatus | None, Query(alias="status")] = None,
    enabled: Annotated[bool | None, Query()] = None,
    transport: Annotated[McpServerTransport | None, Query()] = None,
) -> McpServerListRead:
    return service.list_servers(
        status_filter=status_filter,
        enabled=enabled,
        transport=transport,
    )


@router.post("", response_model=McpServerRead, status_code=status.HTTP_201_CREATED)
def create_mcp_server_draft(
    payload: McpServerCreate,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerRead:
    return service.create_draft(payload)


@router.get("/{server_id}", response_model=McpServerRead)
def get_mcp_server(
    server_id: int,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerRead:
    return service.get_server(server_id)


@router.patch("/{server_id}", response_model=McpServerRead)
def update_mcp_server_draft(
    server_id: int,
    payload: McpServerUpdate,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerRead:
    return service.update_draft(server_id, payload)


@router.post("/{server_id}/activate", response_model=McpServerRead)
def activate_mcp_server(
    server_id: int,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerRead:
    return service.activate(server_id)


@router.post("/{server_id}/connection-test", response_model=McpServerConnectionTestRead)
def test_mcp_server_connection(
    server_id: int,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerConnectionTestRead:
    return service.test_connection(server_id)


@router.delete("/{server_id}", response_model=McpServerRead)
def archive_mcp_server(
    server_id: int,
    service: Annotated[McpServerService, Depends(get_mcp_server_service)],
) -> McpServerRead:
    return service.archive(server_id)
