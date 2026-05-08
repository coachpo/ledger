export interface ToolCatalogItemRead {
  key: string;
  displayName: string;
  description: string;
  module: string;
}

export interface ToolCatalogListRead {
  items: ToolCatalogItemRead[];
}
