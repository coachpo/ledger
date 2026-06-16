import { beforeEach, describe, expect, it, vi } from "vitest";

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    mutationFn?: (variables: unknown) => unknown;
    onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  removeQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

const toolDiscoveryState = vi.hoisted(() => ({
  listToolsMock: vi.fn(),
  useExtensionsMock: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    mutationFn?: (variables: unknown) => unknown;
    onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  }) => {
    reactQueryState.capturedMutationOptions = options;
    return { mutate: vi.fn(), options };
  },
  useQuery: reactQueryState.useQueryMock,
  useQueryClient: () => ({
    invalidateQueries: reactQueryState.invalidateQueriesMock,
    removeQueries: reactQueryState.removeQueriesMock,
  }),
}));

vi.mock("@/lib/api/workflow-packages", () => ({
  createWorkflowPackage: vi.fn(),
  createWorkflowPackageLaunch: vi.fn(),
  createWorkflowPackageRuntimeInputPresetEntry: vi.fn(),
  deleteWorkflowPackage: vi.fn(),
  deleteWorkflowPackageRuntimeInputPresetEntry: vi.fn(),
  deleteWorkflowPackageSecretBinding: vi.fn(),
  getWorkflowPackage: vi.fn(),
  getWorkflowPackageLaunch: vi.fn(),
  getWorkflowPackageManifest: vi.fn(),
  getWorkflowPackageRuntimeInputRegistry: vi.fn(),
  importWorkflowPackage: vi.fn(),
  listWorkflowPackageSecretBindings: vi.fn(),
  listWorkflowPackages: vi.fn(),
  preflightWorkflowPackage: vi.fn(),
  updateWorkflowPackage: vi.fn(),
  updateWorkflowPackageRuntimeInputPresetEntry: vi.fn(),
  upsertWorkflowPackageSecretBinding: vi.fn(),
  validateWorkflowPackageManifest: vi.fn(),
}));

vi.mock("@/hooks/use-extensions", () => ({
  useExtensions: () => toolDiscoveryState.useExtensionsMock(),
}));

vi.mock("@/lib/api/tools", () => ({
  listTools: (...args: unknown[]) => toolDiscoveryState.listToolsMock(...args),
}));

import {
  DIGITAL_ORACLE_EXTENSION_KEY,
  FINANCE_WORKSPACE_EXTENSION_KEY,
} from "@/extensions";
import {
  createWorkflowPackageRuntimeInputPresetEntry,
  deleteWorkflowPackage,
  deleteWorkflowPackageRuntimeInputPresetEntry,
  preflightWorkflowPackage,
  updateWorkflowPackageRuntimeInputPresetEntry,
  validateWorkflowPackageManifest,
} from "@/lib/api/workflow-packages";
import { queryKeys } from "@/lib/query-keys";
import {
  useCreateWorkflowPackageLaunch,
  useCreateWorkflowPackageRuntimeInputPresetEntry,
  useDeleteWorkflowPackage,
  useDeleteWorkflowPackages,
  useDeleteWorkflowPackageRuntimeInputPresetEntry,
  usePreflightWorkflowPackage,
  useTools,
  useUpdateWorkflowPackage,
  useUpdateWorkflowPackageRuntimeInputPresetEntry,
  useValidateWorkflowPackageManifest,
  useWorkflowPackage,
  useWorkflowPackageLaunch,
  useWorkflowPackageRuntimeInputRegistry,
  useWorkflowPackages,
} from "./use-workflow-packages";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useWorkflowPackages", () => {
  beforeEach(() => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.removeQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    toolDiscoveryState.listToolsMock.mockReset();
    toolDiscoveryState.useExtensionsMock.mockReset();
    toolDiscoveryState.useExtensionsMock.mockReturnValue({
      data: {
        items: [
          {
            enabled: true,
            key: FINANCE_WORKSPACE_EXTENSION_KEY,
            label: "Finance Workspace",
          },
          {
            enabled: true,
            key: DIGITAL_ORACLE_EXTENSION_KEY,
            label: "Digital Oracle Runtime",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
    vi.mocked(createWorkflowPackageRuntimeInputPresetEntry).mockReset();
    vi.mocked(deleteWorkflowPackage).mockReset();
    vi.mocked(deleteWorkflowPackageRuntimeInputPresetEntry).mockReset();
    vi.mocked(preflightWorkflowPackage).mockReset();
    vi.mocked(updateWorkflowPackageRuntimeInputPresetEntry).mockReset();
    vi.mocked(validateWorkflowPackageManifest).mockReset();
  });

  it("filters finance and Digital Oracle tools independently through extension state", () => {
    const toolCatalog = {
      items: [
        {
          key: "signaldeck.finance.reports.lookup",
          displayName: "Report Lookup",
          description: "Read persisted SignalDeck reports.",
        },
        {
          key: "signaldeck.digital_oracle.prediction_markets.lookup",
          displayName: "Prediction Markets",
          description: "Find prediction-market signals.",
        },
        {
          key: "signaldeck.digital_oracle.sec_filings.lookup",
          displayName: "SEC Filings",
          description: "Find SEC filing summaries.",
        },
        {
          key: "signaldeck.digital_oracle.market_sentiment.lookup",
          displayName: "Market Sentiment",
          description: "Read market sentiment snapshots.",
        },
        {
          key: "core.echo",
          displayName: "Echo",
          description: "Core smoke tool.",
        },
      ],
    };
    reactQueryState.useQueryMock.mockReturnValue({
      data: toolCatalog,
      error: null,
      isError: false,
      isPending: false,
    });

    expect(useTools().data?.items.map((tool) => tool.key)).toEqual([
      "signaldeck.finance.reports.lookup",
      "signaldeck.digital_oracle.prediction_markets.lookup",
      "signaldeck.digital_oracle.sec_filings.lookup",
      "signaldeck.digital_oracle.market_sentiment.lookup",
      "core.echo",
    ]);
    expect(reactQueryState.useQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: queryKeys.platform.tools.list(),
      }),
    );

    toolDiscoveryState.useExtensionsMock.mockReturnValue({
      data: {
        items: [
          {
            enabled: true,
            key: FINANCE_WORKSPACE_EXTENSION_KEY,
            label: "Finance Workspace",
          },
          {
            enabled: false,
            key: DIGITAL_ORACLE_EXTENSION_KEY,
            label: "Digital Oracle Runtime",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });

    expect(useTools().data?.items.map((tool) => tool.key)).toEqual([
      "signaldeck.finance.reports.lookup",
      "core.echo",
    ]);

    toolDiscoveryState.useExtensionsMock.mockReturnValue({
      data: {
        items: [
          {
            enabled: false,
            key: FINANCE_WORKSPACE_EXTENSION_KEY,
            label: "Finance Workspace",
          },
          {
            enabled: true,
            key: DIGITAL_ORACLE_EXTENSION_KEY,
            label: "Digital Oracle Runtime",
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });

    expect(useTools().data?.items.map((tool) => tool.key)).toEqual([
      "signaldeck.digital_oracle.prediction_markets.lookup",
      "signaldeck.digital_oracle.sec_filings.lookup",
      "signaldeck.digital_oracle.market_sentiment.lookup",
      "core.echo",
    ]);
  });

  it("uses package list and detail keys without live status filters", () => {
    useWorkflowPackages();
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        queryKey: queryKeys.platform.workflowPackages.list(),
      }),
    );

    useWorkflowPackage(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.detail(""),
      }),
    );

    useWorkflowPackage(15);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.detail(15),
      }),
    );
  });

  it("uses workflow-scoped runtime input registry keys", () => {
    useWorkflowPackageRuntimeInputRegistry(undefined, "runtime_workflow");
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(
          "",
          "runtime_workflow",
        ),
      }),
    );

    useWorkflowPackageRuntimeInputRegistry(15, " summarize ");
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(15, "summarize"),
      }),
    );
  });

  it("gates workflow launch metadata queries until a workflow key is selected", () => {
    useWorkflowPackageLaunch(15, "   ");
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflowPackages.launch(15),
      }),
    );

    useWorkflowPackageLaunch(15, " summarize ");
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflowPackages.launch(15, "summarize"),
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

  it("posts workflow preflight with workflow key and launch parameters", async () => {
    usePreflightWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      packageId: 15,
      payload: { parameters: { ticker: "AVGO" }, workflowKey: "summarize" },
    });

    expect(preflightWorkflowPackage).toHaveBeenCalledWith(15, {
      parameters: { ticker: "AVGO" },
      workflowKey: "summarize",
    });
  });

  it("invalidates package, run, and launch scopes after creating a package launch", async () => {
    useCreateWorkflowPackageLaunch();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.(
      { id: 23, workflowKey: "summarize" },
      { packageId: 15, payload: { workflowKey: "summarize", parameters: { ticker: "AVGO" } } },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(23),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launch(15, "summarize"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(15, "summarize"),
    });
  });

  it("invalidates package update scopes including runtime input registries", async () => {
    useUpdateWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.(
      { id: 15 },
      { packageId: 15, payload: { manifestSource: "updated" } },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(15),
    });
  });

  it("invalidates workflow-scoped registry entries after preset mutations", async () => {
    useCreateWorkflowPackageRuntimeInputPresetEntry();
    let mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      packageId: 15,
      workflowKey: "summarize",
      payload: { name: "Morning preset", payload: { ticker: "AVGO" } },
    });
    expect(createWorkflowPackageRuntimeInputPresetEntry).toHaveBeenCalledWith(
      15,
      { name: "Morning preset", payload: { ticker: "AVGO" } },
      { workflowKey: "summarize" },
    );
    await mutationOptions.onSuccess?.({}, { packageId: 15, workflowKey: "summarize" });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(15, "summarize"),
    });

    reactQueryState.invalidateQueriesMock.mockClear();
    useUpdateWorkflowPackageRuntimeInputPresetEntry();
    mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      entryId: 44,
      packageId: 15,
      workflowKey: "summarize",
      payload: { payload: { ticker: "MSFT" } },
    });
    expect(updateWorkflowPackageRuntimeInputPresetEntry).toHaveBeenCalledWith(
      15,
      44,
      { payload: { ticker: "MSFT" } },
      { workflowKey: "summarize" },
    );
    await mutationOptions.onSuccess?.({}, { packageId: 15, workflowKey: "summarize" });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(15, "summarize"),
    });

    reactQueryState.invalidateQueriesMock.mockClear();
    useDeleteWorkflowPackageRuntimeInputPresetEntry();
    mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({ entryId: 44, packageId: 15, workflowKey: "summarize" });
    expect(deleteWorkflowPackageRuntimeInputPresetEntry).toHaveBeenCalledWith(15, 44, {
      workflowKey: "summarize",
    });
    await mutationOptions.onSuccess?.({}, { packageId: 15, workflowKey: "summarize" });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistry(15, "summarize"),
    });
  });

  it("invalidates package and run list scopes after delete", async () => {
    useDeleteWorkflowPackage();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(15);
    expect(deleteWorkflowPackage).toHaveBeenCalledWith(15);

    await mutationOptions.onSuccess?.(undefined, 15);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(15),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
      type: "inactive",
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.all,
    });
  });

  it("composes single-package deletes for bulk workflow package deletion", async () => {
    useDeleteWorkflowPackages();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.([15, 16]);
    expect(deleteWorkflowPackage).toHaveBeenCalledWith(15);
    expect(deleteWorkflowPackage).toHaveBeenCalledWith(16);

    await mutationOptions.onSettled?.(undefined, null, [15, 16]);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(16),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(16),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.all,
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
      type: "inactive",
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
    });
  });

  it("still invalidates package scopes after partial bulk delete failure", async () => {
    vi.mocked(deleteWorkflowPackage).mockImplementation((packageId) => {
      if (packageId === 16) {
        return Promise.reject(new Error("Package not found"));
      }

      return Promise.resolve(undefined);
    });

    useDeleteWorkflowPackages();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.([15, 16])).rejects.toThrow(
      "Package not found",
    );
    await mutationOptions.onSettled?.(
      undefined,
      new Error("Package not found"),
      [15, 16],
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.detail(16),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.runtimeInputRegistryScope(16),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.all,
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
      type: "inactive",
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.lists(),
    });
  });
});
