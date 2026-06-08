from __future__ import annotations

from app.schemas.common import CamelModel


class ToolCatalogItemRead(CamelModel):
    key: str
    display_name: str
    description: str


class ToolCatalogListRead(CamelModel):
    items: list[ToolCatalogItemRead]
