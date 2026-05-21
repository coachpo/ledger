import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  createPortfolioMock: vi.fn(),
  deletePortfolioMock: vi.fn(),
  getPortfolioMock: vi.fn(),
  listPortfoliosMock: vi.fn(),
  updatePortfolioMock: vi.fn(),
}));

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

vi.mock("@/lib/api/portfolios", () => ({
  createPortfolio: apiState.createPortfolioMock,
  deletePortfolio: apiState.deletePortfolioMock,
  getPortfolio: apiState.getPortfolioMock,
  listPortfolios: apiState.listPortfoliosMock,
  updatePortfolio: apiState.updatePortfolioMock,
}));

import { queryKeys } from "@/lib/query-keys";
import { useDeletePortfolio, useDeletePortfolios } from "./use-portfolios";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("usePortfolios hooks", () => {
  beforeEach(() => {
    apiState.createPortfolioMock.mockReset();
    apiState.deletePortfolioMock.mockReset();
    apiState.getPortfolioMock.mockReset();
    apiState.listPortfoliosMock.mockReset();
    apiState.updatePortfolioMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.removeQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
  });

  it("removes portfolio detail queries and invalidates lists after a single delete", async () => {
    useDeletePortfolio();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(42);
    expect(apiState.deletePortfolioMock).toHaveBeenCalledWith(42);

    await mutationOptions.onSuccess?.(undefined, 42);
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.detail(42),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.lists(),
    });
  });

  it("deletes portfolios in batches and clears related caches on settle", async () => {
    apiState.deletePortfolioMock.mockResolvedValue(undefined);

    useDeletePortfolios();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.([42, 84]);
    expect(apiState.deletePortfolioMock).toHaveBeenCalledWith(42);
    expect(apiState.deletePortfolioMock).toHaveBeenCalledWith(84);

    await mutationOptions.onSettled?.(undefined, null, [42, 84]);
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.detail(42),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.detail(84),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.lists(),
    });
  });

  it("surfaces the first batch delete failure and still clears caches on settle", async () => {
    apiState.deletePortfolioMock
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("Portfolio is still referenced"));

    useDeletePortfolios();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.([42, 84])).rejects.toThrow(
      "Portfolio is still referenced",
    );

    await mutationOptions.onSettled?.(
      undefined,
      new Error("Portfolio is still referenced"),
      [42, 84],
    );
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.detail(42),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.detail(84),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.portfolios.lists(),
    });
  });
});
