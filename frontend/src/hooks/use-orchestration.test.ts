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

describe("useOrchestration", () => {
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
