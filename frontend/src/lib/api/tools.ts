import { requestPlatform } from "../api-client";
import type { ToolCatalogListRead } from "../types/tool";

export function listTools(signal?: AbortSignal): Promise<ToolCatalogListRead> {
  return requestPlatform<ToolCatalogListRead>("/tools", { signal });
}
