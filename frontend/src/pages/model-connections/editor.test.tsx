import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelConnectionsEditorPage } from "./editor";
import { createDefaultCapabilities } from "./model-connection-ui";

const navigateMock = vi.fn();
const paramsMock: { modelConnectionId?: string } = {};
const createModelConnectionMock = vi.fn();
const probeModelConnectionMock = vi.fn();
const testModelConnectionMock = vi.fn();
const updateModelConnectionMock = vi.fn();
const useModelConnectionMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingCapabilities = {
  ...createDefaultCapabilities("openai_chat_completions"),
  nativeToolCalls: {
    detail: "Tool calls rejected by fixture.",
    lastProbedAt: "2026-04-22T08:20:00Z",
    status: "unsupported" as const,
  },
  strictJsonSchemaOutput: {
    detail: "Strict schema accepted.",
    lastProbedAt: "2026-04-22T08:20:00Z",
    status: "supported" as const,
  },
};

const existingConnection = {
  baseUrl: "https://provider.example.test/v1/",
  capabilities: existingCapabilities,
  createdAt: "2026-04-21T12:00:00Z",
  description: "Production compatible endpoint.",
  id: 4,
  key: "primary_compatible",
  lastProbedAt: "2026-04-22T08:20:00Z",
  lastTestMessage: "Healthy",
  lastTestOk: true,
  lastTestedAt: "2026-04-22T08:30:00Z",
  modelId: "fake-tools-disabled",
  name: "Primary Compatible",
  outputStrategyPolicy: "prefer_strict_schema",
  parallelToolCallsPolicy: "serialize",
  probeCacheTtlSeconds: 900,
  protocolProfile: "openai_chat_completions",
  reasoningEffort: "high",
  reasoningPolicy: "allow",
  streamingPolicy: "allow",
  timeoutSeconds: 90,
  updatedAt: "2026-04-22T08:31:00Z",
};

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

vi.mock("@/hooks/use-model-connections", () => ({
  useCreateModelConnection: () => ({
    isPending: false,
    mutateAsync: createModelConnectionMock,
  }),
  useModelConnection: (modelConnectionId?: string) =>
    useModelConnectionMock(modelConnectionId),
  useProbeModelConnectionCapabilities: () => ({
    isPending: false,
    mutateAsync: probeModelConnectionMock,
  }),
  useTestModelConnection: () => ({
    isPending: false,
    mutateAsync: testModelConnectionMock,
  }),
  useUpdateModelConnection: () => ({
    isPending: false,
    mutateAsync: updateModelConnectionMock,
  }),
}));

function fillRequiredCreateFields() {
  fireEvent.change(screen.getByLabelText(/^Name$/i), {
    target: { value: "Primary Compatible" },
  });
  fireEvent.change(screen.getByLabelText(/^Key$/i), {
    target: { value: "primary_compatible" },
  });
  fireEvent.change(screen.getByLabelText(/^Model ID$/i), {
    target: { value: "fake-tools-disabled" },
  });
}

async function chooseReasoningEffort(name: RegExp) {
  const reasoningSelect = screen.getByLabelText(/^Reasoning Effort$/i);
  reasoningSelect.focus();
  fireEvent.keyDown(reasoningSelect, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("ModelConnectionsEditorPage", () => {
  beforeEach(() => {
    paramsMock.modelConnectionId = undefined;
    createModelConnectionMock.mockReset();
    navigateMock.mockReset();
    probeModelConnectionMock.mockReset();
    testModelConnectionMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updateModelConnectionMock.mockReset();
    useModelConnectionMock.mockImplementation((modelConnectionId?: string) =>
      modelConnectionId
        ? {
            data: existingConnection,
            error: null,
            isError: false,
            isPending: false,
          }
        : { data: undefined, error: null, isError: false, isPending: false },
    );
  });

  it("renders a full-height details-plus-evidence shell with labeled core controls", () => {
    render(<ModelConnectionsEditorPage />);

    const shell = screen.getByTestId("model-connections-editor");
    expect(shell).toHaveClass("h-full", "min-h-0", "min-w-0", "overflow-hidden");
    expect(screen.getByTestId("workspace-page-shell-context")).toContainElement(
      screen.getByText("Create Model Connection"),
    );
    expect(screen.getByTestId("workspace-page-shell-body")).toHaveClass(
      "overflow-auto",
    );
    expect(screen.queryByRole("main")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Create Model Connection" }),
    ).toBeVisible();

    for (const label of [
      "Key",
      "Name",
      "Model ID",
      "Description",
      "Base URL",
      "Protocol Profile",
      "Timeout Seconds",
      "Reasoning Effort",
      "API Key",
    ]) {
      expect(screen.getByLabelText(label)).toBeVisible();
    }

    expect(
      screen.getByRole("button", { name: /test connection/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /probe required capabilities/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /save model connection/i }),
    ).toBeEnabled();
    expect(
      screen.getAllByText(
        /test connection checks reachability on the saved endpoint only/i,
      )[0],
    ).toBeVisible();
    expect(screen.getByText("Editable connection details")).toBeVisible();
    expect(screen.getByText("Credential rotation")).toBeVisible();
    expect(screen.getByText("Compatibility evidence")).toBeVisible();
    const compactEvidence = screen.getByTestId(
      "model-connection-compatibility-evidence",
    );
    expect(
      within(compactEvidence).getAllByTestId(
        "model-connection-compact-evidence-row",
      ).length,
    ).toBeGreaterThan(10);
    expect(within(compactEvidence).queryAllByRole("listitem")).toHaveLength(0);
    expect(screen.getByText("Connection health")).toBeVisible();
    expect(screen.getByText("Capability matrix")).toBeVisible();
    expect(screen.getByText("Runtime policies")).toBeVisible();
    expect(screen.getAllByText("Strict JSON schema output")).toHaveLength(1);
    expect(screen.getAllByText("Streaming responses")).toHaveLength(1);
    expect(screen.getByText("Output strategy policy")).toBeVisible();
  });

  it("preserves exact custom roots in create payloads", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 9 });

    render(<ModelConnectionsEditorPage />);

    fillRequiredCreateFields();
    fireEvent.change(screen.getByLabelText(/^Base URL$/i), {
      target: { value: "https://new.sharedchat.cc/codex/v1" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: "https://new.sharedchat.cc/codex/v1",
        key: "primary_compatible",
        modelId: "fake-tools-disabled",
        name: "Primary Compatible",
        protocolProfile: "openai_responses",
        reasoningEffort: "medium",
        timeoutSeconds: 60,
      }),
    );
    expect(createModelConnectionMock.mock.calls[0][0]).not.toHaveProperty(
      "apiKey",
    );
    for (const backendOwnedField of [
      "apiStyle",
      "capabilities",
      "outputStrategyPolicy",
      "parallelToolCallsPolicy",
      "probeCacheTtlSeconds",
      "reasoningPolicy",
      "streamingPolicy",
    ]) {
      expect(createModelConnectionMock.mock.calls[0][0]).not.toHaveProperty(
        backendOwnedField,
      );
    }
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/9/edit");
  });

  it("submits apiKey only when a create user enters a credential", async () => {
    const enteredCredential = globalThis.crypto.randomUUID();
    createModelConnectionMock.mockResolvedValue({ id: 14 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    fireEvent.change(screen.getByLabelText(/^API Key$/i), {
      target: { value: enteredCredential },
    });

    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ apiKey: enteredCredential }),
    );
  });

  it("offers omit, preset, and custom reasoning effort options", async () => {
    render(<ModelConnectionsEditorPage />);

    const reasoningSelect = screen.getByLabelText(/^Reasoning Effort$/i);
    reasoningSelect.focus();
    fireEvent.keyDown(reasoningSelect, { key: "ArrowDown" });

    expect(
      await screen.findByRole("option", { name: /^Omit reasoning parameter$/ }),
    ).toBeVisible();
    expect(screen.getByRole("option", { name: /^none$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^minimal$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^low$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^medium$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^high$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^xhigh$/ })).toBeVisible();
    expect(
      screen.getByRole("option", { name: /^Custom\.\.\.$/ }),
    ).toBeVisible();
  });

  it("submits null reasoning effort when Omit is selected", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 11 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^Omit reasoning parameter$/);

    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ reasoningEffort: null }),
    );
  });

  it("submits literal none reasoning effort as a string", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 12 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^none$/);

    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ reasoningEffort: "none" }),
    );
  });

  it("trims and submits a custom reasoning effort", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 13 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^Custom\.\.\.$/);
    fireEvent.change(screen.getByLabelText(/^Custom Reasoning Effort$/i), {
      target: { value: "  xhigh  " },
    });

    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ reasoningEffort: "xhigh" }),
    );
  });

  it("requires non-blank custom reasoning effort", async () => {
    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^Custom\.\.\.$/);
    fireEvent.change(screen.getByLabelText(/^Custom Reasoning Effort$/i), {
      target: { value: "   " },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Reasoning effort is required when Custom is selected.",
      ),
    );
    expect(createModelConnectionMock).not.toHaveBeenCalled();
  });

  it("limits custom reasoning effort length", async () => {
    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^Custom\.\.\.$/);
    fireEvent.change(screen.getByLabelText(/^Custom Reasoning Effort$/i), {
      target: { value: "x".repeat(129) },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Reasoning effort must be 128 characters or fewer.",
      ),
    );
    expect(createModelConnectionMock).not.toHaveBeenCalled();
  });

  it("loads existing custom reasoning effort values into the custom input", () => {
    paramsMock.modelConnectionId = "4";
    const customConnection = {
      ...existingConnection,
      reasoningEffort: "experimental-reasoning",
    };
    useModelConnectionMock.mockImplementation(() => ({
      data: customConnection,
      error: null,
      isError: false,
      isPending: false,
    }));

    render(<ModelConnectionsEditorPage />);

    expect(screen.getByLabelText(/^Reasoning Effort$/i)).toHaveTextContent(
      "Custom...",
    );
    expect(screen.getByLabelText(/^Custom Reasoning Effort$/i)).toHaveValue(
      "experimental-reasoning",
    );
  });

  it("submits Chat Completions protocol profile when selected", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 10 });

    render(<ModelConnectionsEditorPage />);

    fillRequiredCreateFields();
    const profileSelect = screen.getByLabelText(/^Protocol Profile$/i);
    profileSelect.focus();
    fireEvent.keyDown(profileSelect, { key: "ArrowDown" });
    fireEvent.click(
      await screen.findByRole("option", {
        name: /^Chat Completions-compatible$/i,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(createModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ protocolProfile: "openai_chat_completions" }),
    );
    expect(createModelConnectionMock.mock.calls[0][0]).not.toHaveProperty(
      "apiStyle",
    );
  });

  it("keeps the secret blank on edit and preserves the existing key when apiKey is left blank", async () => {
    paramsMock.modelConnectionId = "4";
    updateModelConnectionMock.mockResolvedValue({ id: 4 });

    render(<ModelConnectionsEditorPage />);

    expect(screen.getByLabelText(/^API Key$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^Key$/i)).toHaveValue("primary_compatible");
    expect(screen.getByLabelText(/^Key$/i)).toBeDisabled();
    expect(screen.getByLabelText(/^Base URL$/i)).toHaveValue(
      "https://provider.example.test/v1/",
    );
    fireEvent.change(screen.getByLabelText(/^Base URL$/i), {
      target: { value: "https://provider.example.com/custom-root" },
    });

    expect(screen.getByText(/last reachability test passed/i)).toBeVisible();
    expect(screen.getAllByText(/tool calls rejected by fixture/i)[0]).toBeVisible();
    expect(screen.getAllByText(/strict schema accepted/i)[0]).toBeVisible();
    expect(screen.getByText("Serialize tool calls")).toBeVisible();
    expect(screen.getByText("900s")).toBeVisible();
    expect(screen.getByLabelText(/^Protocol Profile$/i)).toHaveTextContent(
      "Chat Completions-compatible",
    );
    fireEvent.change(screen.getByLabelText(/^Name$/i), {
      target: { value: "Primary Compatible Updated" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(updateModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    const updateCall = updateModelConnectionMock.mock.calls[0][0];
    expect(updateCall.modelConnectionId).toBe("4");
    expect(updateCall.payload).toMatchObject({
      baseUrl: "https://provider.example.com/custom-root",
      description: "Production compatible endpoint.",
      modelId: "fake-tools-disabled",
      name: "Primary Compatible Updated",
      protocolProfile: "openai_chat_completions",
      reasoningEffort: "high",
      timeoutSeconds: 90,
    });
    for (const backendOwnedField of [
      "apiStyle",
      "apiKey",
      "capabilities",
      "outputStrategyPolicy",
      "parallelToolCallsPolicy",
      "probeCacheTtlSeconds",
      "reasoningPolicy",
      "streamingPolicy",
    ]) {
      expect(updateCall.payload).not.toHaveProperty(backendOwnedField);
    }
  });

  it("surfaces successful connection feedback inline", async () => {
    paramsMock.modelConnectionId = "4";
    testModelConnectionMock.mockResolvedValue({
      lastTestedAt: "2026-04-22T09:00:00Z",
      message: "Connection OK",
      modelConnectionId: 4,
      ok: true,
    });

    render(<ModelConnectionsEditorPage />);
    fireEvent.click(screen.getByTestId("model-connection-test"));

    await waitFor(() =>
      expect(screen.getByTestId("model-connection-feedback")).toBeVisible(),
    );
    const feedback = within(screen.getByTestId("model-connection-feedback"));
    expect(feedback.getByText(/reachability succeeded/i)).toBeVisible();
    expect(feedback.getByText(/connection ok/i)).toBeVisible();
    expect(screen.getAllByText(/reachability succeeded/i)[0]).toBeVisible();
    expect(toastSuccessMock).toHaveBeenCalledWith("Connection OK");
  });

  it("surfaces failed connection feedback inline", async () => {
    paramsMock.modelConnectionId = "4";
    testModelConnectionMock.mockResolvedValue({
      lastTestedAt: "2026-04-22T09:00:00Z",
      message: "Key rejected",
      modelConnectionId: 4,
      ok: false,
    });

    render(<ModelConnectionsEditorPage />);
    fireEvent.click(screen.getByTestId("model-connection-test"));

    await waitFor(() =>
      expect(screen.getByTestId("model-connection-feedback")).toBeVisible(),
    );
    const feedback = within(screen.getByTestId("model-connection-feedback"));
    expect(feedback.getByText(/reachability failed/i)).toBeVisible();
    expect(feedback.getByText(/key rejected/i)).toBeVisible();
    expect(screen.getAllByText(/reachability failed/i)[0]).toBeVisible();
    expect(toastErrorMock).toHaveBeenCalledWith("Key rejected");
  });

  it("surfaces successful capability probe feedback inline", async () => {
    paramsMock.modelConnectionId = "4";
    probeModelConnectionMock.mockResolvedValue({
      cached: false,
      capabilities: existingCapabilities,
      lastProbedAt: "2026-04-22T09:15:00Z",
      modelConnectionId: 4,
      probeCacheTtlSeconds: 900,
      requestedCapabilityKeys: [
        "textGeneration",
        "chatCompletions",
        "responsesApi",
        "streaming",
        "nativeToolCalls",
        "parallelToolCalls",
        "jsonObjectOutput",
        "strictJsonSchemaOutput",
        "reasoningHints",
        "usageReporting",
        "systemMessages",
      ],
    });

    render(<ModelConnectionsEditorPage />);
    fireEvent.click(screen.getByTestId("model-connection-probe"));

    await waitFor(() =>
      expect(
        screen.getByTestId("model-connection-probe-feedback"),
      ).toBeVisible(),
    );
    const feedback = within(
      screen.getByTestId("model-connection-probe-feedback"),
    );
    expect(feedback.getByText(/capability probe completed/i)).toBeVisible();
    expect(feedback.getByText(/fresh probe recorded/i)).toBeVisible();
    expect(screen.getAllByText(/capability probe completed/i)[0]).toBeVisible();
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "Capability probe completed",
    );
  });

  it("keeps compatibility evidence read-only when saving endpoint edits", async () => {
    paramsMock.modelConnectionId = "4";
    updateModelConnectionMock.mockResolvedValue({ id: 4 });

    render(<ModelConnectionsEditorPage />);
    fireEvent.change(screen.getByLabelText(/^Model ID$/i), {
      target: { value: "fake-strict-schema-disabled" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /save model connection/i }),
    );

    await waitFor(() =>
      expect(updateModelConnectionMock).toHaveBeenCalledTimes(1),
    );
    expect(updateModelConnectionMock.mock.calls[0][0].payload).toMatchObject({
      modelId: "fake-strict-schema-disabled",
      protocolProfile: "openai_chat_completions",
    });
    expect(updateModelConnectionMock.mock.calls[0][0].payload).not.toHaveProperty(
      "capabilities",
    );
  });
});
