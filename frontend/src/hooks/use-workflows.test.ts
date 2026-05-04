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

vi.mock("@/lib/api/workflows", () => ({
  archiveWorkflow: vi.fn(),
  createWorkflow: vi.fn(),
  createWorkflowLaunch: vi.fn(),
  getWorkflow: vi.fn(),
  getWorkflowLaunch: vi.fn(),
  listWorkflowVersions: vi.fn(),
  listWorkflows: vi.fn(),
  updateWorkflow: vi.fn(),
  validateWorkflowManifest: vi.fn(),
}));

import { validateWorkflowManifest } from "@/lib/api/workflows";
import { queryKeys } from "@/lib/query-keys";
import {
  useCreateWorkflow,
  useCreateWorkflowLaunch,
  useUpdateWorkflow,
  useValidateWorkflowManifest,
  useWorkflow,
  useWorkflowLaunch,
  useWorkflowVersions,
} from "./use-workflows";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useWorkflows", () => {
  beforeEach(() => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    vi.mocked(validateWorkflowManifest).mockReset();
  });

  it("uses platform workflow detail keys and disables detail queries without an id", () => {
    reactQueryState.useQueryMock.mockClear();

    useWorkflow(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflows.detail(""),
      }),
    );

    useWorkflow(15, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflows.detail(15, 2),
      }),
    );
  });

  it("passes manifest validation payloads through without invalidating caches", async () => {
    vi.mocked(validateWorkflowManifest).mockResolvedValue({
      diagnostics: [],
      metadata: null,
      compiledPayload: null,
      runInputSchema: null,
    });

    useValidateWorkflowManifest();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    if (!mutationOptions.mutationFn) {
      throw new Error("Expected mutation function to be captured");
    }

    const payload = { manifestSource: "apiVersion: ledger.workflow/v1" };
    await mutationOptions.mutationFn(payload);

    expect(validateWorkflowManifest).toHaveBeenCalledWith(payload);
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalled();
  });

  it("invalidates platform workflow list and detail scopes after create", async () => {
    useCreateWorkflow();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.({ id: 15, version: 1 }, { key: "report_lookup_reference" });

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(15),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(15, 1),
    });
  });

  it("invalidates submitted and created workflow detail scopes after update", async () => {
    useUpdateWorkflow();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.(
      { id: 22, version: 3 },
      { payload: { manifestSource: "apiVersion: ledger.workflow/v1" }, workflowId: "15" },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail("15"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(22),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.detail(22, 3),
    });
  });

  it("uses workflow launch and version query keys", () => {
    reactQueryState.useQueryMock.mockClear();

    useWorkflowLaunch(undefined, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.workflows.launch("", 2),
      }),
    );

    useWorkflowLaunch(15, 2);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflows.launch(15, 2),
      }),
    );

    useWorkflowVersions(15);
    expect(reactQueryState.useQueryMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.workflows.versions(15),
      }),
    );
  });

  it("invalidates platform run and workflow launch caches after creating a workflow launch", async () => {
    useCreateWorkflowLaunch();

    expect(reactQueryState.capturedMutationOptions).not.toBeNull();
    if (reactQueryState.capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }
    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;

    await mutationOptions.onSuccess?.(
      { id: 23 },
      { workflowId: 15, payload: { version: 2, parameters: { ticker: "AVGO" } } },
    );

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.detail(23),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflows.launch(15, 2),
    });
  });
});
