import { type IdParam, type RequestQueryValue, requestV2, toPathSegment } from "../api-client";
import type {
  CapabilityListParams,
  CapabilityRegistryEntryDraftCreateInput,
  CapabilityRegistryEntryDraftUpdateInput,
  CapabilityRegistryEntryListRead,
  CapabilityRegistryEntryRead,
} from "../types/studio";

function capabilityPath(specId: IdParam): string {
  return `/capabilities/${toPathSegment(specId)}`;
}

function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

export function listCapabilities(
  params?: CapabilityListParams,
  signal?: AbortSignal,
): Promise<CapabilityRegistryEntryListRead> {
  return requestV2<CapabilityRegistryEntryListRead>("/capabilities", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getCapability(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<CapabilityRegistryEntryRead> {
  return requestV2<CapabilityRegistryEntryRead>(capabilityPath(specId), { signal });
}

export function createCapability(
  payload: CapabilityRegistryEntryDraftCreateInput,
  signal?: AbortSignal,
): Promise<CapabilityRegistryEntryRead> {
  return requestV2<CapabilityRegistryEntryRead>("/capabilities", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateCapability(
  specId: IdParam,
  payload: CapabilityRegistryEntryDraftUpdateInput,
  signal?: AbortSignal,
): Promise<CapabilityRegistryEntryRead> {
  return requestV2<CapabilityRegistryEntryRead>(capabilityPath(specId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateCapability(
  specId: IdParam,
  signal?: AbortSignal,
): Promise<CapabilityRegistryEntryRead> {
  return requestV2<CapabilityRegistryEntryRead>(`${capabilityPath(specId)}/activate`, {
    method: "POST",
    signal,
  });
}

export const capabilitiesApi = {
  list: listCapabilities,
  get: getCapability,
  create: createCapability,
  update: updateCapability,
  activate: activateCapability,
} as const;
