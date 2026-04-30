import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  CapabilityCreateInput,
  CapabilityListParams,
  CapabilityListRead,
  CapabilityRead,
  CapabilityUpdateInput,
} from "../types/capability";

function capabilityPath(capabilityId: IdParam): string {
  return `/capabilities/${toPathSegment(capabilityId)}`;
}

export function listCapabilities(
  params?: CapabilityListParams,
  signal?: AbortSignal,
): Promise<CapabilityListRead> {
  return requestPlatform<CapabilityListRead>("/capabilities", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getCapability(capabilityId: IdParam, signal?: AbortSignal): Promise<CapabilityRead> {
  return requestPlatform<CapabilityRead>(capabilityPath(capabilityId), { signal });
}

export function createCapability(
  payload: CapabilityCreateInput,
  signal?: AbortSignal,
): Promise<CapabilityRead> {
  return requestPlatform<CapabilityRead>("/capabilities", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateCapability(
  capabilityId: IdParam,
  payload: CapabilityUpdateInput,
  signal?: AbortSignal,
): Promise<CapabilityRead> {
  return requestPlatform<CapabilityRead>(capabilityPath(capabilityId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateCapability(capabilityId: IdParam, signal?: AbortSignal): Promise<CapabilityRead> {
  return requestPlatform<CapabilityRead>(`${capabilityPath(capabilityId)}/activate`, {
    method: "POST",
    signal,
  });
}

export function archiveCapability(capabilityId: IdParam, signal?: AbortSignal): Promise<CapabilityRead> {
  return requestPlatform<CapabilityRead>(capabilityPath(capabilityId), {
    method: "DELETE",
    signal,
  });
}

export const capabilitiesApi = {
  activate: activateCapability,
  archive: archiveCapability,
  create: createCapability,
  get: getCapability,
  list: listCapabilities,
  update: updateCapability,
} as const;
