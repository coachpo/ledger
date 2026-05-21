import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  createModelConnectionMock: vi.fn(),
  deleteModelConnectionMock: vi.fn(),
  getModelConnectionMock: vi.fn(),
  listModelConnectionsMock: vi.fn(),
  testModelConnectionMock: vi.fn(),
  updateModelConnectionMock: vi.fn(),
}));

const reactQueryState = vi.hoisted(() => ({
  capturedMutationOptions: null as {
    mutationFn?: (variables: unknown) => unknown;
    onSettled?: (
      result: unknown,
      error: unknown,
      variables: unknown,
    ) => unknown;
    onSuccess?: (result: unknown, variables: unknown) => unknown;
  } | null,
  invalidateQueriesMock: vi.fn(),
  useQueryMock: vi.fn((options: unknown) => options),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    mutationFn?: (variables: unknown) => unknown;
    onSettled?: (
      result: unknown,
      error: unknown,
      variables: unknown,
    ) => unknown;
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

vi.mock("@/lib/api/model-connections", () => ({
  createModelConnection: apiState.createModelConnectionMock,
  deleteModelConnection: apiState.deleteModelConnectionMock,
  getModelConnection: apiState.getModelConnectionMock,
  listModelConnections: apiState.listModelConnectionsMock,
  testModelConnection: apiState.testModelConnectionMock,
  updateModelConnection: apiState.updateModelConnectionMock,
}));

import { queryKeys } from "@/lib/query-keys";
import {
  useCreateModelConnection,
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnection,
  useModelConnections,
  useTestModelConnection,
  useUpdateModelConnection,
} from "./use-model-connections";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSettled?: (result: unknown, error: unknown, variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useModelConnections", () => {
  beforeEach(() => {
    apiState.createModelConnectionMock.mockReset();
    apiState.deleteModelConnectionMock.mockReset();
    apiState.getModelConnectionMock.mockReset();
    apiState.listModelConnectionsMock.mockReset();
    apiState.testModelConnectionMock.mockReset();
    apiState.updateModelConnectionMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
  });

  it("uses platform list/detail keys and disables detail queries without an id", () => {
    useModelConnections({});
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        queryKey: queryKeys.platform.modelConnections.list({}),
      }),
    );

    useModelConnection(undefined);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        enabled: false,
        queryKey: queryKeys.platform.modelConnections.detail(""),
      }),
    );
  });

  it("invalidates list/detail scopes after create and update", async () => {
    useCreateModelConnection();
    let mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.({ id: 4 }, { key: "model" });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });

    reactQueryState.invalidateQueriesMock.mockClear();
    useUpdateModelConnection();
    mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.onSuccess?.(
      { id: 4 },
      { modelConnectionId: 4, payload: { name: "Updated" } },
    );
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
  });

  it("invalidates list/detail scopes after delete", async () => {
    useDeleteModelConnection();

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(4);
    expect(apiState.deleteModelConnectionMock).toHaveBeenCalledWith(4);

    await mutationOptions.onSuccess?.(undefined, 4);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
  });

  it("deletes model connections in batches and invalidates affected scopes", async () => {
    apiState.deleteModelConnectionMock.mockResolvedValue(undefined);

    useDeleteModelConnections();

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.([4, 12]);
    expect(apiState.deleteModelConnectionMock).toHaveBeenCalledWith(4);
    expect(apiState.deleteModelConnectionMock).toHaveBeenCalledWith(12);

    await mutationOptions.onSettled?.(undefined, null, [4, 12]);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(12),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
  });

  it("surfaces the first batch delete failure", async () => {
    apiState.deleteModelConnectionMock
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("Connection is still referenced"));

    useDeleteModelConnections();

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.([4, 12])).rejects.toThrow(
      "Connection is still referenced",
    );
  });

  it("requires an id before testing a connection", async () => {
    useTestModelConnection(undefined);

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.(undefined)).rejects.toThrow(
      "Model connection id is required to test the connection.",
    );
  });

  it("invalidates list/detail scopes after a successful connection test", async () => {
    useTestModelConnection(12);

    const mutationOptions =
      reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(undefined);
    expect(apiState.testModelConnectionMock).toHaveBeenCalledWith(12);

    await mutationOptions.onSuccess?.({ modelConnectionId: 12 }, undefined);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(12),
    });
  });
});
