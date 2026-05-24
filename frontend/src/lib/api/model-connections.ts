import {
  requestPlatform,
  toPathSegment,
  toQueryRecord,
  type IdParam,
} from "../api-client";
import type {
  ModelConnectionCapabilityProbeRead,
  ModelConnectionCapabilityProbeRequest,
  ModelConnectionConnectionTestRead,
  ModelConnectionCreateInput,
  ModelConnectionListParams,
  ModelConnectionListRead,
  ModelConnectionRead,
  ModelConnectionUpdateInput,
} from "../types/model-connection";

function modelConnectionDetailPath(modelConnectionId: IdParam): string {
  return `/model-connections/${toPathSegment(modelConnectionId)}`;
}

export function listModelConnections(
  params?: ModelConnectionListParams,
  signal?: AbortSignal,
): Promise<ModelConnectionListRead> {
  return requestPlatform<ModelConnectionListRead>("/model-connections", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getModelConnection(
  modelConnectionId: IdParam,
  signal?: AbortSignal,
): Promise<ModelConnectionRead> {
  return requestPlatform<ModelConnectionRead>(modelConnectionDetailPath(modelConnectionId), {
    signal,
  });
}

export function createModelConnection(
  payload: ModelConnectionCreateInput,
  signal?: AbortSignal,
): Promise<ModelConnectionRead> {
  return requestPlatform<ModelConnectionRead>("/model-connections", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateModelConnection(
  modelConnectionId: IdParam,
  payload: ModelConnectionUpdateInput,
  signal?: AbortSignal,
): Promise<ModelConnectionRead> {
  return requestPlatform<ModelConnectionRead>(modelConnectionDetailPath(modelConnectionId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function testModelConnection(
  modelConnectionId: IdParam,
  signal?: AbortSignal,
): Promise<ModelConnectionConnectionTestRead> {
  return requestPlatform<ModelConnectionConnectionTestRead>(
    `${modelConnectionDetailPath(modelConnectionId)}/connection-test`,
    {
      method: "POST",
      signal,
    },
  );
}

export function probeModelConnectionCapabilities(
  modelConnectionId: IdParam,
  payload: ModelConnectionCapabilityProbeRequest = {},
  signal?: AbortSignal,
): Promise<ModelConnectionCapabilityProbeRead> {
  return requestPlatform<ModelConnectionCapabilityProbeRead>(
    `${modelConnectionDetailPath(modelConnectionId)}/capability-probe`,
    {
      body: payload,
      method: "POST",
      signal,
    },
  );
}

export function deleteModelConnection(
  modelConnectionId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return requestPlatform<void>(modelConnectionDetailPath(modelConnectionId), {
    method: "DELETE",
    signal,
  });
}

export const modelConnectionsApi = {
  create: createModelConnection,
  delete: deleteModelConnection,
  get: getModelConnection,
  list: listModelConnections,
  probeCapabilities: probeModelConnectionCapabilities,
  testConnection: testModelConnection,
  update: updateModelConnection,
} as const;
