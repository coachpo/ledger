from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agents import ToolCatalog
from app.api.dependencies import get_tool_catalog
from app.schemas.common import CamelModel


class ToolCatalogItemRead(CamelModel):
    key: str
    display_name: str
    description: str


class ToolCatalogListRead(CamelModel):
    items: list[ToolCatalogItemRead]


router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=ToolCatalogListRead)
def list_tools(
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
) -> ToolCatalogListRead:
    return ToolCatalogListRead(
        items=[
            ToolCatalogItemRead(
                key=tool.key,
                display_name=tool.display_name,
                description=tool.description,
            )
            for tool in tool_catalog.list_registered_tools()
        ]
    )
