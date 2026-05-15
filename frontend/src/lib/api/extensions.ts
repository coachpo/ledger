import { requestPlatform, toPathSegment } from "../api-client";
import type {
  ExtensionListRead,
  ExtensionRead,
  ExtensionToggleRequest,
} from "../types/extension";

export function listExtensions(signal?: AbortSignal): Promise<ExtensionListRead> {
  return requestPlatform<ExtensionListRead>("/extensions", { signal });
}

export function toggleExtension(
  extensionKey: string,
  payload: ExtensionToggleRequest,
): Promise<ExtensionRead> {
  return requestPlatform<ExtensionRead>(`/extensions/${toPathSegment(extensionKey)}`, {
    body: payload,
    method: "PATCH",
  });
}

export const extensionsApi = {
  list: listExtensions,
  toggle: toggleExtension,
} as const;
