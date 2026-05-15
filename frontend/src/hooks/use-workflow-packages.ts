import {
  type QueryClient,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  createWorkflowPackage,
  deleteWorkflowPackage,
  deleteWorkflowPackageSecretBinding,
  createWorkflowPackageLaunch,
  createWorkflowPackageVersion,
  getWorkflowPackage,
  getWorkflowPackageLaunch,
  getWorkflowPackageManifest,
  importWorkflowPackage,
  listWorkflowPackageSecretBindings,
  listWorkflowPackageVersions,
  listWorkflowPackages,
  preflightWorkflowPackage,
  updateWorkflowPackage,
  upsertWorkflowPackageSecretBinding,
  validateWorkflowPackageManifest,
} from "@/lib/api/workflow-packages";
import { listTools } from "@/lib/api/tools";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type {
  WorkflowPackageImportRequest,
  WorkflowPackageLaunchCreateRequest,
  WorkflowPackageLaunchCreateResponse,
  WorkflowPackageLaunchRead,
  WorkflowPackageListParams,
  WorkflowPackageManifestRead,
  WorkflowPackageManifestRequest,
  WorkflowPackageRead,
  WorkflowPackageSecretBindingListRead,
  WorkflowPackageSecretBindingUpdateRequest,
  WorkflowPackageUpdateRequest,
  WorkflowPackageVersionListRead,
} from "@/lib/types/workflow-package";

type UpdateWorkflowPackageVariables = {
  packageId: IdParam;
  payload: WorkflowPackageUpdateRequest;
};

type CreateWorkflowPackageVersionVariables = {
  packageId: IdParam;
  payload: WorkflowPackageManifestRequest;
};

type WorkflowPackageLaunchVariables = {
  packageId: IdParam;
  payload: WorkflowPackageLaunchCreateRequest;
};

type WorkflowPackageSecretBindingVariables = {
  key: IdParam;
  packageId: IdParam;
};

type WorkflowPackageSecretBindingUpdateVariables = WorkflowPackageSecretBindingVariables & {
  payload: WorkflowPackageSecretBindingUpdateRequest;
};

type WorkflowPackageReadLike = Pick<WorkflowPackageRead, "id" | "latestVersion">;

export type WorkflowPackageVersionSummary = {
  errorMessage: string | null;
  isError: boolean;
  isPending: boolean;
  latestCreatedAt: string | null;
  latestLaunchedAt: string | null;
  warningCount: number;
};

function hasWorkflowPackageId(packageId: IdParam | undefined): packageId is IdParam {
  return Boolean(packageId) && packageId !== "new";
}

function normalizeManifestVersion(version: number | string | null | undefined) {
  return version === undefined || version === null || version === "" ? undefined : version;
}

function invalidateWorkflowPackageScope(
  queryClient: QueryClient,
  packageRead: WorkflowPackageReadLike,
) {
  const invalidateLatestVersion = packageRead.latestVersion === null
    ? [Promise.resolve()]
    : [
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.workflowPackages.manifest(packageRead.id, packageRead.latestVersion),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.workflowPackages.launch(packageRead.id, packageRead.latestVersion),
        }),
      ];

  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.detail(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.versions(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.manifest(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.launch(packageRead.id) }),
    ...invalidateLatestVersion,
  ]);
}

export function useTools() {
  return useQuery({
    queryKey: queryKeys.platform.tools.list(),
    queryFn: ({ signal }) => listTools(signal),
  });
}

export function useWorkflowPackages(params: WorkflowPackageListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.list(params),
    queryFn: ({ signal }) => listWorkflowPackages(params, signal),
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
  version?: number | string | null,
): UseQueryResult<WorkflowPackageManifestRead, Error> {
  const hasPackageId = hasWorkflowPackageId(packageId);
  const resolvedPackageId = hasPackageId ? packageId : "";
  const resolvedVersion = normalizeManifestVersion(version);

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.manifest(resolvedPackageId, resolvedVersion),
    queryFn: ({ signal }) =>
      getWorkflowPackageManifest(resolvedPackageId, { signal, version: resolvedVersion }),
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
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.workflowPackages.versions(packageId),
      });
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

export function useWorkflowPackageVersions(
  packageId: IdParam | undefined,
): UseQueryResult<WorkflowPackageVersionListRead, Error> {
  const resolvedPackageId = packageId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.versions(resolvedPackageId),
    queryFn: ({ signal }) => listWorkflowPackageVersions(resolvedPackageId, signal),
    enabled: Boolean(packageId),
  });
}

function latestVersionFromList(items: WorkflowPackageVersionListRead["items"]) {
  return [...items].sort((left, right) => right.version - left.version)[0] ?? null;
}

export function useWorkflowPackageVersionSummaries(
  packageIds: readonly IdParam[],
  enabled = true,
): Map<string, WorkflowPackageVersionSummary> {
  const resolvedPackageIds = packageIds.map(String);
  const queries = useQueries({
    queries: resolvedPackageIds.map((packageId) => ({
      queryKey: queryKeys.platform.workflowPackages.versions(packageId),
      queryFn: ({ signal }: { signal: AbortSignal }) => listWorkflowPackageVersions(packageId, signal),
      enabled: enabled && packageId.length > 0,
    })),
  });

  return new Map(
    resolvedPackageIds.map((packageId, index) => {
      const query = queries[index];
      const latestVersion = latestVersionFromList(query.data?.items ?? []);
      return [
        packageId,
        {
          errorMessage: query.error instanceof Error ? query.error.message : null,
          isError: query.isError,
          isPending: query.isPending,
          latestCreatedAt: latestVersion?.createdAt ?? null,
          latestLaunchedAt: latestVersion?.launchedAt ?? null,
          warningCount: latestVersion?.warnings.length ?? 0,
        },
      ];
    }),
  );
}

export function useCreateWorkflowPackageVersion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ packageId, payload }: CreateWorkflowPackageVersionVariables) =>
      createWorkflowPackageVersion(packageId, payload),
    onSuccess: async (workflowPackage) => {
      await invalidateWorkflowPackageScope(queryClient, workflowPackage);
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
  version?: number,
  workflowKey?: string,
): UseQueryResult<WorkflowPackageLaunchRead, Error> {
  const resolvedPackageId = packageId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.launch(resolvedPackageId, version, workflowKey),
    queryFn: ({ signal }) =>
      getWorkflowPackageLaunch(resolvedPackageId, { signal, version, workflowKey }),
    enabled: Boolean(packageId),
  });
}

export function usePreflightWorkflowPackage() {
  return useMutation({
    mutationFn: ({ packageId, payload }: WorkflowPackageLaunchVariables) =>
      preflightWorkflowPackage(packageId, {
        version: payload.version ?? undefined,
        workflowKey: payload.workflowKey ?? undefined,
      }),
  });
}

export function useCreateWorkflowPackageLaunch() {
  const queryClient = useQueryClient();

  return useMutation<WorkflowPackageLaunchCreateResponse, Error, WorkflowPackageLaunchVariables>({
    mutationFn: ({ packageId, payload }) => createWorkflowPackageLaunch(packageId, payload),
    onSuccess: async (run, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.platform.runs.detail(run.id) }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.platform.workflowPackages.launch(
            variables.packageId,
            variables.payload.version ?? undefined,
            variables.payload.workflowKey ?? undefined,
          ),
        }),
      ]);
    },
  });
}
