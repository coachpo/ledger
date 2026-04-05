import { describe, expect, it, vi } from "vitest";

const invalidateQueriesMock = vi.fn();
const removeQueriesMock = vi.fn();
let capturedMutationOptions: { onSuccess?: (result: unknown, variables: unknown) => void } | null = null;

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: { onSuccess?: (result: unknown, variables: unknown) => void }) => {
    capturedMutationOptions = options;
    return { mutate: vi.fn() };
  },
  useQuery: vi.fn(),
  useQueryClient: () => ({
    invalidateQueries: invalidateQueriesMock,
    removeQueries: removeQueriesMock,
  }),
}));

vi.mock("@/lib/api/backtests", () => ({
  cancelBacktest: vi.fn(),
  createBacktest: vi.fn(),
  deleteBacktest: vi.fn(),
  getBacktest: vi.fn(),
  listBacktests: vi.fn(),
}));

import { queryKeys } from "@/lib/query-keys";
import { useDeleteBacktest } from "./use-backtests";

describe("useDeleteBacktest", () => {
  it("invalidates list and removes the deleted detail scope", () => {
    invalidateQueriesMock.mockReset();
    removeQueriesMock.mockReset();
    capturedMutationOptions = null;

    useDeleteBacktest();

    expect(capturedMutationOptions).not.toBeNull();
    if (capturedMutationOptions === null) {
      throw new Error("Expected mutation options to be captured");
    }

    const mutationOptions = capturedMutationOptions as {
      onSuccess?: (result: unknown, variables: unknown) => void;
    };
    mutationOptions.onSuccess?.(undefined, 42);

    expect(invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.backtests.list(),
    });
    expect(removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.backtests.detail(42),
    });
  });
});
