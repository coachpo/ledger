import { describe, expect, it, vi } from "vitest";

const invalidateQueriesMock = vi.fn();

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: { onSuccess?: (result: unknown, variables: unknown) => void }) => ({
    mutate: vi.fn(),
    options,
  }),
  useQueryClient: () => ({
    invalidateQueries: invalidateQueriesMock,
  }),
}));

import { queryKeys } from "@/lib/query-keys";

describe("useOrchestration", () => {
  it("keeps the v1 orchestration query key shape stable", () => {
    expect(queryKeys.orchestration.roles.list()).toEqual([
      "api",
      "orchestration",
      "roles",
      "list",
    ]);
    expect(queryKeys.orchestration.characters.detail(7)).toEqual([
      "api",
      "orchestration",
      "characters",
      "detail",
      "7",
    ]);
  });

  it("invalidates the orchestration role and character lists after writes", async () => {
    const { useCreateOrchestrationRole, useCreateOrchestrationCharacter } = await import(
      "./use-orchestration",
    );

    const roleHook = useCreateOrchestrationRole();
    const characterHook = useCreateOrchestrationCharacter();

    expect(roleHook).toBeTruthy();
    expect(characterHook).toBeTruthy();
    expect(invalidateQueriesMock).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(["orchestration"]) }),
    );
  });
});
