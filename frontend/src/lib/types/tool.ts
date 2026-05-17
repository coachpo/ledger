export interface ToolCatalogItemRead {
  key: string;
  displayName: string;
  description: string;
}

export interface ToolCatalogListRead {
  items: ToolCatalogItemRead[];
}
