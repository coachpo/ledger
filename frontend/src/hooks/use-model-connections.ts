import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createModelConnection,
  deleteModelConnection,
  getModelConnection,
  listModelConnections,
  probeModelConnectionCapabilities,
  testModelConnection,
  updateModelConnection,
} from "@/lib/api/model-connections";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  ModelConnectionCapabilityProbeRequest,
  ModelConnectionCreateInput,
  ModelConnectionListParams,
  ModelConnectionUpdateInput,
} from "@/lib/types/model-connection";

type UpdateModelConnectionVariables = {
  payload: ModelConnectionUpdateInput;
  modelConnectionId: IdParam;
};

function invalidateModelConnectionScope(
  queryClient: QueryClient,
  modelConnectionId: IdParam,
) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.platform.modelConnections.all,
    }),
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
    queryKey: queryKeys.platform.modelConnections.detail(
      resolvedModelConnectionId,
    ),
    queryFn: ({ signal }) =>
      getModelConnection(resolvedModelConnectionId, signal),
    enabled: Boolean(modelConnectionId),
  });
}

export function useCreateModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ModelConnectionCreateInput) =>
      createModelConnection(payload),
    onSuccess: async (modelConnection) => {
      await invalidateModelConnectionScope(queryClient, modelConnection.id);
    },
  });
}

export function useUpdateModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      payload,
      modelConnectionId,
    }: UpdateModelConnectionVariables) =>
      updateModelConnection(modelConnectionId, payload),
    onSuccess: async (modelConnection, { modelConnectionId }) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.modelConnections.detail(modelConnectionId),
      });
      await invalidateModelConnectionScope(queryClient, modelConnection.id);
    },
  });
}

async function invalidateDeletedModelConnectionScope(
  queryClient: QueryClient,
  modelConnectionId: IdParam,
) {
  await queryClient.invalidateQueries({
    queryKey: queryKeys.platform.modelConnections.detail(modelConnectionId),
  });
}

export function useDeleteModelConnection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (modelConnectionId: IdParam) =>
      deleteModelConnection(modelConnectionId),
    onSuccess: async (_result, modelConnectionId) => {
      await invalidateDeletedModelConnectionScope(
        queryClient,
        modelConnectionId,
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.modelConnections.all,
      });
    },
  });
}

export function useDeleteModelConnections() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (modelConnectionIds: IdParam[]) => {
      const results = await Promise.allSettled(
        modelConnectionIds.map((modelConnectionId) =>
          deleteModelConnection(modelConnectionId),
        ),
      );
      const firstRejected = results.find(
        (result) => result.status === "rejected",
      );

      if (firstRejected?.status === "rejected") {
        throw firstRejected.reason;
      }
    },
    onSettled: async (_result, _error, modelConnectionIds) => {
      await Promise.all(
        modelConnectionIds.map((modelConnectionId) =>
          invalidateDeletedModelConnectionScope(queryClient, modelConnectionId),
        ),
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.modelConnections.all,
      });
    },
  });
}

export function useTestModelConnection(modelConnectionId: IdParam | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      if (!modelConnectionId) {
        throw new Error(
          "Model connection id is required to test the connection.",
        );
      }

      return testModelConnection(modelConnectionId);
    },
    onSuccess: async (result) => {
      await invalidateModelConnectionScope(
        queryClient,
        result.modelConnectionId,
      );
    },
  });
}

export function useProbeModelConnectionCapabilities(
  modelConnectionId: IdParam | undefined,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: ModelConnectionCapabilityProbeRequest = {}) => {
      if (!modelConnectionId) {
        throw new Error(
          "Model connection id is required to probe capabilities.",
        );
      }

      return probeModelConnectionCapabilities(modelConnectionId, payload);
    },
    onSuccess: async (result) => {
      await invalidateModelConnectionScope(
        queryClient,
        result.modelConnectionId,
      );
    },
  });
}
