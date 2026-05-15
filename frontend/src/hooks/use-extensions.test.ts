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

import { FINANCE_WORKSPACE_EXTENSION_KEY } from "@/extensions";
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
  defaultEnabled: true,
  phase: "phase_1_bundled_first_party",
  versioningRule: "follows_backend_application_version",
  contributionCategories: [],
  dependencies: [],
  contributions: [],
  stateVersion: 2,
  enabledAt: null,
  disabledAt: "2026-05-15T11:00:00Z",
  disabledReason: "Disabled in test",
  createdAt: "2026-05-15T09:00:00Z",
  updatedAt: "2026-05-15T11:00:00Z",
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

  it("invalidates extension, finance, and tool caches after finance state changes", async () => {
    vi.mocked(toggleExtension).mockResolvedValue(financeExtension);
    useToggleExtension();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.({
      extensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      payload: { enabled: false, disabledReason: "Disabled in test" },
    });
    expect(toggleExtension).toHaveBeenCalledWith(FINANCE_WORKSPACE_EXTENSION_KEY, {
      enabled: false,
      disabledReason: "Disabled in test",
    });

    await mutationOptions.onSuccess?.(financeExtension, {});

    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.extensions.all,
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
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.tools.all,
    });
  });
});
