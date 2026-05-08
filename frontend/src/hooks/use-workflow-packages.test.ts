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
  archiveOrDeleteWorkflowPackage: vi.fn(),
  createWorkflowPackage: vi.fn(),
  createWorkflowPackageLaunch: vi.fn(),
  createWorkflowPackageVersion: vi.fn(),
  getWorkflowPackage: vi.fn(),
  getWorkflowPackageLaunch: vi.fn(),
  importWorkflowPackage: vi.fn(),
  listWorkflowPackageVersions: vi.fn(),
  listWorkflowPackages: vi.fn(),
  preflightWorkflowPackage: vi.fn(),
  updateWorkflowPackage: vi.fn(),
  validateWorkflowPackageManifest: vi.fn(),
}));
import { validateWorkflowPackageManifest } from "@/lib/api/workflow-packages";
import { queryKeys } from "@/lib/query-keys";
import {
  useCreateWorkflowPackage,
  useCreateWorkflowPackageLaunch,
  useUpdateWorkflowPackage,
  useValidateWorkflowPackageManifest,
  useWorkflowPackage,
  useWorkflowPackageLaunch,
  useWorkflowPackageVersions,
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
  });

  it("uses package detail keys and disables detail queries without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useWorkflowPackage(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.detail(""),
      }),
    );

    useWorkflowPackage(15);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
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
    const payload = { manifestSource: "apiVersion: ledger.workflowPackage/v1" };
    await mutationOptions.mutationFn?.(payload);

    expect(validateWorkflowPackageManifest).toHaveBeenCalledWith(payload);
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalled();
  });

  it("invalidates package list, detail, versions, and launch scopes after create", async () => {
    useCreateWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.({ id: 15, latestVersion: 2 }, { manifestSource: "source" });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.versions(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launch(15, 2),
    });
  });

  it("invalidates submitted and returned package detail scopes after update", async () => {
    useUpdateWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.(
      { id: 22, latestVersion: 3 },
      { packageId: "15", payload: { manifestSource: "source" } },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail("15"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(22),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launch(22, 3),
    });
  });

  it("uses package launch and version query keys", () => {
    reactQueryState.useQueryMock.mockClear();

    useWorkflowPackageLaunch(undefined, 2, "summarize");
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.launch("", 2, "summarize"),
      }),
    );

    useWorkflowPackageLaunch(15, 2, "summarize");
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.launch(15, 2, "summarize"),
      }),
    );

    useWorkflowPackageVersions(15);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.versions(15),
      }),
    );
  });

  it("invalidates platform run and package launch caches after creating a package launch", async () => {
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
});
