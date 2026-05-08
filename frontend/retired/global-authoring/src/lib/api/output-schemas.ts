import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type {
  OutputSchemaCreateInput,
  OutputSchemaListParams,
  OutputSchemaListRead,
  OutputSchemaRead,
  OutputSchemaUpdateInput,
} from "../types/output-schema";

function outputSchemaPath(schemaId: IdParam): string {
  return `/output-schemas/${toPathSegment(schemaId)}`;
}

export function listOutputSchemas(
  params?: OutputSchemaListParams,
  signal?: AbortSignal,
): Promise<OutputSchemaListRead> {
  return requestPlatform<OutputSchemaListRead>("/output-schemas", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getOutputSchema(
  schemaId: IdParam,
  signal?: AbortSignal,
): Promise<OutputSchemaRead> {
  return requestPlatform<OutputSchemaRead>(outputSchemaPath(schemaId), { signal });
}

export function createOutputSchema(
  payload: OutputSchemaCreateInput,
  signal?: AbortSignal,
): Promise<OutputSchemaRead> {
  return requestPlatform<OutputSchemaRead>("/output-schemas", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateOutputSchema(
  schemaId: IdParam,
  payload: OutputSchemaUpdateInput,
  signal?: AbortSignal,
): Promise<OutputSchemaRead> {
  return requestPlatform<OutputSchemaRead>(outputSchemaPath(schemaId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateOutputSchema(
  schemaId: IdParam,
  signal?: AbortSignal,
): Promise<OutputSchemaRead> {
  return requestPlatform<OutputSchemaRead>(`${outputSchemaPath(schemaId)}/activate`, {
    method: "POST",
    signal,
  });
}

export const outputSchemasApi = {
  activate: activateOutputSchema,
  create: createOutputSchema,
  get: getOutputSchema,
  list: listOutputSchemas,
  update: updateOutputSchema,
} as const;
