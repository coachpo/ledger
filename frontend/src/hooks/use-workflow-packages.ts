import {
  type QueryClient,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  archiveOrDeleteWorkflowPackage,
  createWorkflowPackage,
  createWorkflowPackageLaunch,
  createWorkflowPackageVersion,
  getWorkflowPackage,
  getWorkflowPackageLaunch,
  importWorkflowPackage,
  listWorkflowPackageVersions,
  listWorkflowPackages,
  preflightWorkflowPackage,
  updateWorkflowPackage,
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
  WorkflowPackageManifestRequest,
  WorkflowPackageRead,
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

type WorkflowPackageReadLike = Pick<WorkflowPackageRead, "id" | "latestVersion">;

export type WorkflowPackageVersionSummary = {
  errorMessage: string | null;
  isError: boolean;
  isPending: boolean;
  latestCreatedAt: string | null;
  latestLaunchedAt: string | null;
  warningCount: number;
};

function invalidateWorkflowPackageScope(
  queryClient: QueryClient,
  packageRead: WorkflowPackageReadLike,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.detail(packageRead.id) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.workflowPackages.versions(packageRead.id) }),
    packageRead.latestVersion === null
      ? Promise.resolve()
      : queryClient.invalidateQueries({
          queryKey: queryKeys.platform.workflowPackages.launch(packageRead.id, packageRead.latestVersion),
        }),
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

export function useArchiveOrDeleteWorkflowPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (packageId: IdParam) => archiveOrDeleteWorkflowPackage(packageId),
    onSuccess: async (workflowPackage, packageId) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.platform.workflowPackages.detail(packageId),
      });
      await invalidateWorkflowPackageScope(queryClient, workflowPackage);
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
