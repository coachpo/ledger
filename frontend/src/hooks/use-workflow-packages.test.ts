import { beforeEach, describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    mutationFn?: (variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  }) => {
    reactQueryState.capturedMutationOptions = options;
    return { mutate: vi.fn(), options };
  },
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
  }),
}));

vi.mock("@/lib/api/workflow-packages", () => ({
  createWorkflowPackage: vi.fn(),
  createWorkflowPackageLaunch: vi.fn(),
  createWorkflowPackageVersion: vi.fn(),
  deleteWorkflowPackage: vi.fn(),
  getWorkflowPackage: vi.fn(),
  getWorkflowPackageLaunch: vi.fn(),
  importWorkflowPackage: vi.fn(),
  listWorkflowPackageVersions: vi.fn(),
  listWorkflowPackages: vi.fn(),
  preflightWorkflowPackage: vi.fn(),
  updateWorkflowPackage: vi.fn(),
  validateWorkflowPackageManifest: vi.fn(),
}));

import { deleteWorkflowPackage, validateWorkflowPackageManifest } from "@/lib/api/workflow-packages";
import { queryKeys } from "@/lib/query-keys";
import {
  useCreateWorkflowPackageLaunch,
  useDeleteWorkflowPackage,
  useValidateWorkflowPackageManifest,
  useWorkflowPackage,
} from "./use-workflow-packages";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useWorkflowPackages", () => {
  beforeEach(() => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    vi.mocked(validateWorkflowPackageManifest).mockReset();
    vi.mocked(deleteWorkflowPackage).mockReset();
  });

  it("uses package detail keys and disables detail queries without an id", () => {
    useWorkflowPackage(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.detail(""),
      }),
    );

    useWorkflowPackage(15);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.detail(15),
      }),
    );
  });

  it("passes manifest validation payloads through without invalidating caches", async () => {
    vi.mocked(validateWorkflowPackageManifest).mockResolvedValue({
      diagnostics: [],
      warnings: [],
      metadata: null,
      packageDefinition: null,
      compiledPlan: null,
      manifestHash: null,
      compiledHash: null,
    });

    useValidateWorkflowPackageManifest();
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.({ manifestSource: "source" })).resolves.toEqual({
      diagnostics: [],
      warnings: [],
      metadata: null,
      packageDefinition: null,
      compiledPlan: null,
      manifestHash: null,
      compiledHash: null,
    });
    expect(validateWorkflowPackageManifest).toHaveBeenCalledWith({ manifestSource: "source" });
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalled();
  });

  it("invalidates package, run, and launch scopes after creating a package launch", async () => {
    useCreateWorkflowPackageLaunch();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.(
      { id: 23 },
      { packageId: 15, payload: { version: 2, workflowKey: "summarize", parameters: { ticker: "AVGO" } } },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(23),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launch(15, 2, "summarize"),
    });
  });

  it("invalidates package list and detail scopes after delete", async () => {
    useDeleteWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(15);
    expect(deleteWorkflowPackage).toHaveBeenCalledWith(15);

    await mutationOptions.onSuccess?.(undefined, 15);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.all,
    });
  });
});
