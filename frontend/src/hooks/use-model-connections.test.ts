import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  archiveModelConnectionMock: vi.fn(),
  createModelConnectionMock: vi.fn(),
  getModelConnectionMock: vi.fn(),
  listModelConnectionsMock: vi.fn(),
  testModelConnectionMock: vi.fn(),
  updateModelConnectionMock: vi.fn(),
}));

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

vi.mock("@/lib/api/model-connections", () => ({
  archiveModelConnection: apiState.archiveModelConnectionMock,
  createModelConnection: apiState.createModelConnectionMock,
  getModelConnection: apiState.getModelConnectionMock,
  listModelConnections: apiState.listModelConnectionsMock,
  testModelConnection: apiState.testModelConnectionMock,
  updateModelConnection: apiState.updateModelConnectionMock,
}));

import { queryKeys } from "@/lib/query-keys";
import {
  useArchiveModelConnection,
  useCreateModelConnection,
  useModelConnection,
  useModelConnections,
  useTestModelConnection,
  useUpdateModelConnection,
} from "./use-model-connections";

type CapturedMutationOptions = {
  mutationFn?: (variables: unknown) => unknown;
  onSuccess?: (result: unknown, variables: unknown) => unknown;
};

describe("useModelConnections", () => {
  beforeEach(() => {
    apiState.archiveModelConnectionMock.mockReset();
    apiState.createModelConnectionMock.mockReset();
    apiState.getModelConnectionMock.mockReset();
    apiState.listModelConnectionsMock.mockReset();
    apiState.testModelConnectionMock.mockReset();
    apiState.updateModelConnectionMock.mockReset();
    reactQueryState.capturedMutationOptions = null;
    reactQueryState.invalidateQueriesMock.mockReset();
    reactQueryState.useQueryMock.mockClear();
  });

  it("uses platform list/detail keys and disables detail queries without an id", () => {
    useModelConnections({ status: "active" });
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        queryKey: queryKeys.platform.modelConnections.list({ status: "active" }),
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

    useModelConnection(4);
    expect(reactQueryState.useQueryMock).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({
        enabled: true,
        queryKey: queryKeys.platform.modelConnections.detail(4),
      }),
    );
  });

  it("delegates create payloads and invalidates list/detail scopes after create", async () => {
    useCreateModelConnection();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    const omittedReasoningPayload = {
      baseUrl: "https://api.openai.com/v1",
      key: "primary_openai",
      modelId: "gpt-4.1",
      name: "Primary OpenAI",
      reasoningEffort: null,
      timeoutSeconds: 60,
    };
    const customReasoningPayload = {
      ...omittedReasoningPayload,
      key: "experimental_openai",
      reasoningEffort: "xhigh",
    };

    await mutationOptions.mutationFn?.(omittedReasoningPayload);
    await mutationOptions.mutationFn?.(customReasoningPayload);
    expect(apiState.createModelConnectionMock).toHaveBeenNthCalledWith(1, omittedReasoningPayload);
    expect(apiState.createModelConnectionMock).toHaveBeenNthCalledWith(2, customReasoningPayload);

    await mutationOptions.onSuccess?.({ id: 9 }, omittedReasoningPayload);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(9),
    });
  });

  it("invalidates the previous and canonical detail scopes after update", async () => {
    useUpdateModelConnection();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    const omittedReasoningVariables = {
      modelConnectionId: "4",
      payload: { name: "Updated OpenAI", reasoningEffort: null },
    };
    const customReasoningVariables = {
      modelConnectionId: "4",
      payload: { name: "Updated OpenAI", reasoningEffort: "xhigh" },
    };

    await mutationOptions.mutationFn?.(omittedReasoningVariables);
    await mutationOptions.mutationFn?.(customReasoningVariables);
    expect(apiState.updateModelConnectionMock).toHaveBeenNthCalledWith(1, "4", {
      name: "Updated OpenAI",
      reasoningEffort: null,
    });
    expect(apiState.updateModelConnectionMock).toHaveBeenNthCalledWith(2, "4", {
      name: "Updated OpenAI",
      reasoningEffort: "xhigh",
    });

    await mutationOptions.onSuccess?.({ id: 4 }, customReasoningVariables);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail("4"),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
  });

  it("invalidates list/detail scopes after archive", async () => {
    useArchiveModelConnection();

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await mutationOptions.mutationFn?.(4);
    expect(apiState.archiveModelConnectionMock).toHaveBeenCalledWith(4);

    await mutationOptions.onSuccess?.({ id: 4 }, 4);
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.all,
    });
    expect(reactQueryState.invalidateQueriesMock).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.modelConnections.detail(4),
    });
  });

  it("requires an id before testing a connection", async () => {
    useTestModelConnection(undefined);

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
    await expect(mutationOptions.mutationFn?.(undefined)).rejects.toThrow(
      "Model connection id is required to test the connection.",
    );
  });

  it("invalidates list/detail scopes after a successful connection test", async () => {
    useTestModelConnection(12);

    const mutationOptions = reactQueryState.capturedMutationOptions as CapturedMutationOptions;
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
