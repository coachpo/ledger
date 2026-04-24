import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveModelConnection,
  createModelConnection,
  getModelConnection,
  listModelConnections,
  testModelConnection,
  updateModelConnection,
} from "@/lib/api/model-connections";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  ModelConnectionCreateInput,
  ModelConnectionListParams,
  ModelConnectionUpdateInput,
} from "@/lib/types/model-connection";

type UpdateModelConnectionVariables = {
  payload: ModelConnectionUpdateInput;
  modelConnectionId: IdParam;
};

function invalidateModelConnectionScope(queryClient: QueryClient, modelConnectionId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.modelConnections.all }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.modelConnections.detail(modelConnectionId),
    }),
  ]);
}

export function useModelConnections(params: ModelConnectionListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.modelConnections.list(params),
    queryFn: ({ signal }) => listModelConnections(params, signal),
  });
}

export function useModelConnection(modelConnectionId: IdParam | undefined) {
  const resolvedModelConnectionId = modelConnectionId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.modelConnections.detail(resolvedModelConnectionId),
    queryFn: ({ signal }) => getModelConnection(resolvedModelConnectionId, signal),
    enabled: Boolean(modelConnectionId),
  });
}

export function useCreateModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ModelConnectionCreateInput) => createModelConnection(payload),
    onSuccess: async (modelConnection) => {
      await invalidateModelConnectionScope(queryClient, modelConnection.id);
    },
  });
}

export function useUpdateModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, modelConnectionId }: UpdateModelConnectionVariables) =>
      updateModelConnection(modelConnectionId, payload),
    onSuccess: async (modelConnection, { modelConnectionId }) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.modelConnections.detail(modelConnectionId),
      });
      await invalidateModelConnectionScope(queryClient, modelConnection.id);
    },
  });
}

export function useArchiveModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (modelConnectionId: IdParam) => archiveModelConnection(modelConnectionId),
    onSuccess: async (modelConnection, modelConnectionId) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.modelConnections.detail(modelConnectionId),
      });
      await invalidateModelConnectionScope(queryClient, modelConnection.id);
    },
  });
}

export function useTestModelConnection(modelConnectionId: IdParam | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      if (!modelConnectionId) {
        throw new Error("Model connection id is required to test the connection.");
      }

      return testModelConnection(modelConnectionId);
    },
    onSuccess: async (result) => {
      await invalidateModelConnectionScope(queryClient, result.modelConnectionId);
    },
  });
}
