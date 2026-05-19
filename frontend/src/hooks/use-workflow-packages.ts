import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  createWorkflowPackage,
  createWorkflowPackageLaunch,
  createWorkflowPackageRuntimeInputPersonalEntry,
  deleteWorkflowPackage,
  deleteWorkflowPackageRuntimeInputPersonalEntry,
  deleteWorkflowPackageSecretBinding,
  getWorkflowPackage,
  getWorkflowPackageLaunch,
  getWorkflowPackageManifest,
  getWorkflowPackageRuntimeInputRegistry,
  importWorkflowPackage,
  listWorkflowPackageSecretBindings,
  listWorkflowPackages,
  preflightWorkflowPackage,
  updateWorkflowPackage,
  updateWorkflowPackageRuntimeInputPersonalEntry,
  upsertWorkflowPackageSecretBinding,
  validateWorkflowPackageManifest,
} from "@/lib/api/workflow-packages";
import { filterToolsForExtensionState } from "@/extensions/runtime";
import { useExtensions } from "@/hooks/use-extensions";
import { listTools } from "@/lib/api/tools";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageLaunchCreateRequest,
  WorkflowPackageLaunchCreateResponse,
  WorkflowPackageLaunchRead,
  WorkflowPackageManifestRead,
  WorkflowPackageManifestRequest,
  WorkflowPackageRead,
  WorkflowPackageRuntimeInputPersonalEntryCreateRequest,
  WorkflowPackageRuntimeInputPersonalEntryUpdateRequest,
  WorkflowPackageRuntimeInputRegistryRead,
  WorkflowPackageSecretBindingListRead,
  WorkflowPackageSecretBindingUpdateRequest,
  WorkflowPackageUpdateRequest,
} from "@/lib/types/workflow-package";

type UpdateWorkflowPackageVariables = {
  packageId: IdParam;
  payload: WorkflowPackageUpdateRequest;
};

type WorkflowPackageLaunchVariables = {
  packageId: IdParam;
  payload: WorkflowPackageLaunchCreateRequest;
};

type WorkflowPackageRuntimeInputRegistryVariables = {
  packageId: IdParam;
  workflowKey: string;
};

type WorkflowPackageRuntimeInputPersonalEntryCreateVariables =
  WorkflowPackageRuntimeInputRegistryVariables & {
    payload: WorkflowPackageRuntimeInputPersonalEntryCreateRequest;
  };

type WorkflowPackageRuntimeInputPersonalEntryUpdateVariables =
  WorkflowPackageRuntimeInputRegistryVariables & {
    entryId: IdParam;
    payload: WorkflowPackageRuntimeInputPersonalEntryUpdateRequest;
  };

type WorkflowPackageRuntimeInputPersonalEntryDeleteVariables =
  WorkflowPackageRuntimeInputRegistryVariables & {
    entryId: IdParam;
  };

type WorkflowPackageSecretBindingVariables = {
  key: IdParam;
  packageId: IdParam;
};

type WorkflowPackageSecretBindingUpdateVariables = WorkflowPackageSecretBindingVariables & {
  payload: WorkflowPackageSecretBindingUpdateRequest;
};

type WorkflowPackageReadLike = Pick<WorkflowPackageRead, "id">;

function hasWorkflowPackageId(packageId: IdParam | undefined): packageId is IdParam {
  return Boolean(packageId) && packageId !== "new";
}

function normalizeWorkflowKeyInput(workflowKey: string | null | undefined): string {
  return workflowKey?.trim() ?? "";
}

function invalidateWorkflowPackageRuntimeInputRegistryScope(
  queryClient: QueryClient,
  packageId: IdParam,
  workflowKey?: string | null,
) {
  const normalizedWorkflowKey = normalizeWorkflowKeyInput(workflowKey);
  if (normalizedWorkflowKey) {
    return queryClient.invalidateQueries({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(
        packageId,
        normalizedWorkflowKey,
      ),
    });
  }

  return queryClient.invalidateQueries({
    queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(packageId),
  });
}

function invalidateWorkflowPackageScope(
  queryClient: QueryClient,
  packageRead: WorkflowPackageReadLike,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.detail(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.manifest(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.launch(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.preflight(packageRead.id) }),
    invalidateWorkflowPackageRuntimeInputRegistryScope(queryClient, packageRead.id),
  ]);
}

export function useTools() {
  const extensionsQuery = useExtensions();
  const toolsQuery = useQuery({
    queryKey: queryKeys.platform.tools.list(),
    queryFn: ({ signal }) => listTools(signal),
  });

  return {
    ...toolsQuery,
    data: toolsQuery.data
      ? {
          ...toolsQuery.data,
          items: filterToolsForExtensionState(toolsQuery.data.items, extensionsQuery.data),
        }
      : toolsQuery.data,
    error: toolsQuery.error ?? extensionsQuery.error,
    isError: toolsQuery.isError || extensionsQuery.isError,
    isPending: toolsQuery.isPending || extensionsQuery.isPending,
  };
}

export function useWorkflowPackages() {
  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.list(),
    queryFn: ({ signal }) => listWorkflowPackages(signal),
  });
}

export function useWorkflowPackage(packageId: IdParam | undefined) {
  const resolvedPackageId = packageId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.detail(resolvedPackageId),
    queryFn: ({ signal }) => getWorkflowPackage(resolvedPackageId, signal),
    enabled: Boolean(packageId),
  });
}

export function useWorkflowPackageManifest(
  packageId: IdParam | undefined,
): UseQueryResult<WorkflowPackageManifestRead, Error> {
  const hasPackageId = hasWorkflowPackageId(packageId);
  const resolvedPackageId = hasPackageId ? packageId : "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.manifest(resolvedPackageId),
    queryFn: ({ signal }) => getWorkflowPackageManifest(resolvedPackageId, signal),
    enabled: hasPackageId,
  });
}

export function useValidateWorkflowPackageManifest() {
  return useMutation({
    mutationFn: (payload: WorkflowPackageManifestRequest) => validateWorkflowPackageManifest(payload),
  });
}

export function useCreateWorkflowPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WorkflowPackageManifestRequest) => createWorkflowPackage(payload),
    onSuccess: async (workflowPackage) => {
      await invalidateWorkflowPackageScope(queryClient, workflowPackage);
    },
  });
}
export function useUpdateWorkflowPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ packageId, payload }: UpdateWorkflowPackageVariables) =>
      updateWorkflowPackage(packageId, payload),
    onSuccess: async (workflowPackage, variables) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.workflowPackages.detail(variables.packageId),
      });
      await invalidateWorkflowPackageScope(queryClient, workflowPackage);
    },
  });
}

export function useDeleteWorkflowPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (packageId: IdParam) => deleteWorkflowPackage(packageId),
    onSuccess: async (_result, packageId) => {
      queryClient.removeQueries?.({
        queryKey: queryKeys.platform.workflowPackages.manifest(packageId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.workflowPackages.detail(packageId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.workflowPackages.all,
      });
      await invalidateWorkflowPackageRuntimeInputRegistryScope(queryClient, packageId);
    },
  });
}

export function useWorkflowPackageSecretBindings(
  packageId: IdParam | undefined,
): UseQueryResult<WorkflowPackageSecretBindingListRead, Error> {
  const resolvedPackageId = packageId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.secretBindings(resolvedPackageId),
    queryFn: ({ signal }) => listWorkflowPackageSecretBindings(resolvedPackageId, signal),
    enabled: Boolean(packageId),
  });
}

export function useWorkflowPackageRuntimeInputRegistry(
  packageId: IdParam | undefined,
  workflowKey: string | null | undefined,
): UseQueryResult<WorkflowPackageRuntimeInputRegistryRead, Error> {
  const hasPackageId = hasWorkflowPackageId(packageId);
  const resolvedPackageId = hasPackageId ? packageId : "";
  const resolvedWorkflowKey = normalizeWorkflowKeyInput(workflowKey);

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(
      resolvedPackageId,
      resolvedWorkflowKey,
    ),
    queryFn: ({ signal }) =>
      getWorkflowPackageRuntimeInputRegistry(resolvedPackageId, {
        signal,
        workflowKey: resolvedWorkflowKey,
      }),
    enabled: hasPackageId && Boolean(resolvedWorkflowKey),
  });
}

function invalidateWorkflowPackageSecretBindingScope(queryClient: QueryClient, packageId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.secretBindings(packageId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.launch(packageId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.preflight(packageId) }),
  ]);
}

export function useUpsertWorkflowPackageSecretBinding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ key, packageId, payload }: WorkflowPackageSecretBindingUpdateVariables) =>
      upsertWorkflowPackageSecretBinding(packageId, key, payload),
    onSuccess: async (_binding, variables) => {
      await invalidateWorkflowPackageSecretBindingScope(queryClient, variables.packageId);
    },
  });
}

export function useDeleteWorkflowPackageSecretBinding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ key, packageId }: WorkflowPackageSecretBindingVariables) =>
      deleteWorkflowPackageSecretBinding(packageId, key),
    onSuccess: async (_result, variables) => {
      await invalidateWorkflowPackageSecretBindingScope(queryClient, variables.packageId);
    },
  });
}

export function useCreateWorkflowPackageRuntimeInputPersonalEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ packageId, payload, workflowKey }: WorkflowPackageRuntimeInputPersonalEntryCreateVariables) =>
      createWorkflowPackageRuntimeInputPersonalEntry(packageId, payload, { workflowKey }),
    onSuccess: async (_entry, variables) => {
      await invalidateWorkflowPackageRuntimeInputRegistryScope(
        queryClient,
        variables.packageId,
        variables.workflowKey,
      );
    },
  });
}

export function useUpdateWorkflowPackageRuntimeInputPersonalEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ entryId, packageId, payload, workflowKey }: WorkflowPackageRuntimeInputPersonalEntryUpdateVariables) =>
      updateWorkflowPackageRuntimeInputPersonalEntry(packageId, entryId, payload, { workflowKey }),
    onSuccess: async (_entry, variables) => {
      await invalidateWorkflowPackageRuntimeInputRegistryScope(
        queryClient,
        variables.packageId,
        variables.workflowKey,
      );
    },
  });
}

export function useDeleteWorkflowPackageRuntimeInputPersonalEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ entryId, packageId, workflowKey }: WorkflowPackageRuntimeInputPersonalEntryDeleteVariables) =>
      deleteWorkflowPackageRuntimeInputPersonalEntry(packageId, entryId, { workflowKey }),
    onSuccess: async (_result, variables) => {
      await invalidateWorkflowPackageRuntimeInputRegistryScope(
        queryClient,
        variables.packageId,
        variables.workflowKey,
      );
    },
  });
}

export function useImportWorkflowPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WorkflowPackageImportRequest) => importWorkflowPackage(payload),
    onSuccess: async (workflowPackage) => {
      await invalidateWorkflowPackageScope(queryClient, workflowPackage);
    },
  });
}

export function useWorkflowPackageLaunch(
  packageId: IdParam | undefined,
  workflowKey?: string,
): UseQueryResult<WorkflowPackageLaunchRead, Error> {
  const resolvedPackageId = packageId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.launch(resolvedPackageId, workflowKey),
    queryFn: ({ signal }) => getWorkflowPackageLaunch(resolvedPackageId, { signal, workflowKey }),
    enabled: Boolean(packageId),
  });
}

export function usePreflightWorkflowPackage() {
  return useMutation({
    mutationFn: ({ packageId, payload }: WorkflowPackageLaunchVariables) =>
      preflightWorkflowPackage(packageId, {
        workflowKey: payload.workflowKey ?? undefined,
      }),
  });
}

export function useCreateWorkflowPackageLaunch() {
  const queryClient = useQueryClient();

  return useMutation<WorkflowPackageLaunchCreateResponse, Error, WorkflowPackageLaunchVariables>({
    mutationFn: ({ packageId, payload }) => createWorkflowPackageLaunch(packageId, payload),
    onSuccess: async (run, variables) => {
      const workflowKey = run.workflowKey || variables.payload.workflowKey;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(run.id) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.workflowPackages.launch(
            variables.packageId,
            workflowKey ?? undefined,
          ),
        }),
        invalidateWorkflowPackageRuntimeInputRegistryScope(
          queryClient,
          variables.packageId,
          workflowKey,
        ),
      ]);
    },
  });
}
