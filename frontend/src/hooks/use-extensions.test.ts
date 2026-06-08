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

vi.mock("@/lib/api/extensions", () => ({
  listExtensions: vi.fn(),
  toggleExtension: vi.fn(),
}));

import {
  DIGITAL_ORACLE_EXTENSION_KEY,
  FINANCE_WORKSPACE_EXTENSION_KEY,
} from "@/extensions";
import { listExtensions, toggleExtension } from "@/lib/api/extensions";
import { queryKeys } from "@/lib/query-keys";
import type { ExtensionRead } from "@/lib/types/extension";
import { useExtensions, useToggleExtension } from "./use-extensions";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

const financeExtension: ExtensionRead = {
  key: FINANCE_WORKSPACE_EXTENSION_KEY,
  label: "Finance Workspace",
  enabled: false,
};

const digitalOracleExtension: ExtensionRead = {
  key: DIGITAL_ORACLE_EXTENSION_KEY,
  label: "Digital Oracle Runtime",
  enabled: false,
};

describe("useExtensions", () => {
  beforeEach(() => {
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
    reactQueryState.capturedMutationOptions = null;
    vi.mocked(listExtensions).mockReset();
    vi.mocked(toggleExtension).mockReset();
  });

  it("uses the backend extension list query key", () => {
    useExtensions();

    expect(reactQueryState.useQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: queryKeys.platform.extensions.list(),
      }),
    );
  });

  it("invalidates extension, tool, and finance caches after finance state changes", async () => {
    vi.mocked(toggleExtension).mockResolvedValue(financeExtension);
    useToggleExtension();

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      extensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      payload: { enabled: false },
    });
    expect(toggleExtension).toHaveBeenCalledWith(
      FINANCE_WORKSPACE_EXTENSION_KEY,
      {
        enabled: false,
      },
    );

    await mutationOptions.onSuccess?.(financeExtension, {});

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledTimes(9);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.extensions.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.tools.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launches(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.preflights(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.rerunDrafts(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.forkDrafts(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.reports.all,
    });
  });

  it("invalidates extension, tool, and readiness caches after Digital Oracle state changes", async () => {
    vi.mocked(toggleExtension).mockResolvedValue(digitalOracleExtension);
    useToggleExtension();

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      extensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
      payload: { enabled: false },
    });
    expect(toggleExtension).toHaveBeenCalledWith(DIGITAL_ORACLE_EXTENSION_KEY, {
      enabled: false,
    });

    await mutationOptions.onSuccess?.(digitalOracleExtension, {});

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledTimes(6);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.extensions.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.tools.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.launches(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.workflowPackages.preflights(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.rerunDrafts(),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.runs.forkDrafts(),
    });
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.all,
    });
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalledWith({
      queryKey: queryKeys.templates.all,
    });
    expect(reactQueryState.invalidateQueriesMock).not.toHaveBeenCalledWith({
      queryKey: queryKeys.reports.all,
    });
  });
});
