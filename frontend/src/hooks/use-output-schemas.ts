import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateOutputSchema,
  createOutputSchema,
  getOutputSchema,
  listOutputSchemas,
  updateOutputSchema,
} from "@/lib/api/output-schemas";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  OutputSchemaCreateInput,
  OutputSchemaListParams,
  OutputSchemaUpdateInput,
} from "@/lib/types/output-schema";

type UpdateOutputSchemaVariables = {
  payload: OutputSchemaUpdateInput;
  schemaId: IdParam;
};

function invalidateOutputSchemaScope(queryClient: QueryClient, schemaId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.outputSchemas.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.outputSchemas.detail(schemaId) }),
  ]);
}

export function useOutputSchemas(params: OutputSchemaListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.outputSchemas.list(params),
    queryFn: ({ signal }) => listOutputSchemas(params, signal),
  });
}

export function useOutputSchema(schemaId: IdParam | undefined) {
  const resolvedSchemaId = schemaId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.outputSchemas.detail(resolvedSchemaId),
    queryFn: ({ signal }) => getOutputSchema(resolvedSchemaId, signal),
    enabled: Boolean(schemaId),
  });
}

export function useCreateOutputSchema() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: OutputSchemaCreateInput) => createOutputSchema(payload),
    onSuccess: async (schema) => {
      await invalidateOutputSchemaScope(queryClient, schema.id);
    },
  });
}

export function useUpdateOutputSchema() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, schemaId }: UpdateOutputSchemaVariables) =>
      updateOutputSchema(schemaId, payload),
    onSuccess: async (schema, { schemaId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.outputSchemas.detail(schemaId) });
      await invalidateOutputSchemaScope(queryClient, schema.id);
    },
  });
}

export function useActivateOutputSchema() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (schemaId: IdParam) => activateOutputSchema(schemaId),
    onSuccess: async (schema) => {
      await invalidateOutputSchemaScope(queryClient, schema.id);
    },
  });
}
