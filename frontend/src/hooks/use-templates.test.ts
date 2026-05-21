import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  compileTemplateInlineMock: vi.fn(),
  compileTemplateMock: vi.fn(),
  createTemplateMock: vi.fn(),
  deleteTemplateMock: vi.fn(),
  getPlaceholdersMock: vi.fn(),
  getTemplateMock: vi.fn(),
  listTemplatesMock: vi.fn(),
  updateTemplateMock: vi.fn(),
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

vi.mock("@/lib/api/templates", () => ({
  compileTemplate: apiState.compileTemplateMock,
  compileTemplateInline: apiState.compileTemplateInlineMock,
  createTemplate: apiState.createTemplateMock,
  deleteTemplate: apiState.deleteTemplateMock,
  getPlaceholders: apiState.getPlaceholdersMock,
  getTemplate: apiState.getTemplateMock,
  listTemplates: apiState.listTemplatesMock,
  updateTemplate: apiState.updateTemplateMock,
}));

import { queryKeys } from "@/lib/query-keys";
import { useDeleteTemplate, useDeleteTemplates } from "./use-templates";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useTemplates hooks", () => {
  beforeEach(() => {
    apiState.compileTemplateInlineMock.mockReset();
    apiState.compileTemplateMock.mockReset();
    apiState.createTemplateMock.mockReset();
    apiState.deleteTemplateMock.mockReset();
    apiState.getPlaceholdersMock.mockReset();
    apiState.getTemplateMock.mockReset();
    apiState.listTemplatesMock.mockReset();
    apiState.updateTemplateMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.removeQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
  });

  it("clears deleted template detail caches and invalidates the list after a single delete", async () => {
    useDeleteTemplate();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(7);
    expect(apiState.deleteTemplateMock).toHaveBeenCalledWith(7);

    await mutationOptions.onSuccess?.(undefined, 7);
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.detail(7),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.compile(7),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.list(),
    });
  });

  it("deletes templates in batches, clears detail caches, and invalidates the list on settle", async () => {
    apiState.deleteTemplateMock.mockResolvedValue(undefined);

    useDeleteTemplates();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.([7, 8]);
    expect(apiState.deleteTemplateMock).toHaveBeenCalledWith(7);
    expect(apiState.deleteTemplateMock).toHaveBeenCalledWith(8);

    await mutationOptions.onSettled?.(undefined, null, [7, 8]);
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.detail(7),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.compile(7),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.detail(8),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.compile(8),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.list(),
    });
  });

  it("surfaces the first batch delete failure, clears detail caches, and still invalidates on settle", async () => {
    apiState.deleteTemplateMock
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("Template is still referenced"));

    useDeleteTemplates();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.([7, 8])).rejects.toThrow(
      "Template is still referenced",
    );

    await mutationOptions.onSettled?.(
      undefined,
      new Error("Template is still referenced"),
      [7, 8],
    );
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.detail(7),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.compile(7),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.detail(8),
    });
    expect(reactQueryState.removeQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.compile(8),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.templates.list(),
    });
  });
});
