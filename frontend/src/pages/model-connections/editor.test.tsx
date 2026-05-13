import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";

import { ModelConnectionsEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { modelConnectionId?: string } = {};
const createModelConnectionMock = vi.fn();
const testModelConnectionMock = vi.fn();
const updateModelConnectionMock = vi.fn();
const useModelConnectionMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingConnection = {
  apiStyle: "chat_completions",
  baseUrl: "https://api.openai.com/v1",
  connectionKind: "deterministic_smoke",
  createdAt: "2026-04-21T12:00:00Z",
  description: "Production OpenAI connection.",
  id: 4,
  key: "primary_openai",
  lastTestMessage: "Healthy",
  lastTestOk: true,
  lastTestedAt: "2026-04-22T08:30:00Z",
  modelId: "gpt-4.1",
  name: "Primary OpenAI",
  reasoningEffort: "high",
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
  useCreateModelConnection: () => ({ isPending: false, mutateAsync: createModelConnectionMock }),
  useModelConnection: (modelConnectionId?: string) => useModelConnectionMock(modelConnectionId),
  useTestModelConnection: () => ({ isPending: false, mutateAsync: testModelConnectionMock }),
  useUpdateModelConnection: () => ({ isPending: false, mutateAsync: updateModelConnectionMock }),
}));

function fillRequiredCreateFields() {
  fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI" } });
  fireEvent.change(screen.getByLabelText(/^Key$/i), { target: { value: "primary_openai" } });
  fireEvent.change(screen.getByLabelText(/^Model ID$/i), { target: { value: "gpt-4.1" } });
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
    testModelConnectionMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updateModelConnectionMock.mockReset();
    useModelConnectionMock.mockImplementation((modelConnectionId?: string) =>
      modelConnectionId
        ? { data: existingConnection, error: null, isError: false, isPending: false }
        : { data: undefined, error: null, isError: false, isPending: false },
    );
  });

  it("submits a create body without apiKey until one is entered", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 9 });

    render(<ModelConnectionsEditorPage />);

    expect(screen.queryByText("Connection mode:")).not.toBeInTheDocument();
    expect(screen.queryByText("Provider-backed")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI" } });
    fireEvent.change(screen.getByLabelText(/^Key$/i), { target: { value: "primary_openai" } });
    fireEvent.change(screen.getByLabelText(/^Model ID$/i), { target: { value: "gpt-4.1" } });

    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        key: "primary_openai",
        name: "Primary OpenAI",
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "medium",
        timeoutSeconds: 60,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
    expect(createModelConnectionMock).toHaveBeenCalledWith({
      apiStyle: "responses",
      baseUrl: "https://api.openai.com/v1",
      key: "primary_openai",
      modelId: "gpt-4.1",
      name: "Primary OpenAI",
      reasoningEffort: "medium",
      timeoutSeconds: 60,
    });
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/9/edit");
  });

  it("offers omit, preset, and custom reasoning effort options", async () => {
    render(<ModelConnectionsEditorPage />);

    const reasoningSelect = screen.getByLabelText(/^Reasoning Effort$/i);
    reasoningSelect.focus();
    fireEvent.keyDown(reasoningSelect, { key: "ArrowDown" });

    expect(await screen.findByRole("option", { name: /^Omit reasoning parameter$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^none$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^minimal$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^low$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^medium$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^high$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^xhigh$/ })).toBeVisible();
    expect(screen.getByRole("option", { name: /^Custom\.\.\.$/ })).toBeVisible();
    expect(screen.getByText(/Responses API as reasoning\.effort/i)).toBeVisible();
    expect(screen.getByText(/Chat Completions as reasoning_effort/i)).toBeVisible();
    expect(
      screen.getByText(
        /Existing agent versions keep saved model-connection snapshots; re-save the agent to pick up changed model-connection settings\./i,
      ),
    ).toBeVisible();
  });

  it("submits null reasoning effort when Omit is selected", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 11 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^Omit reasoning parameter$/);

    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        key: "primary_openai",
        name: "Primary OpenAI",
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: null,
        timeoutSeconds: 60,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ reasoningEffort: null }),
    );
  });

  it("submits literal none reasoning effort as a string", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 12 });

    render(<ModelConnectionsEditorPage />);
    fillRequiredCreateFields();
    await chooseReasoningEffort(/^none$/);

    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        key: "primary_openai",
        name: "Primary OpenAI",
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "none",
        timeoutSeconds: 60,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
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

    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        key: "primary_openai",
        name: "Primary OpenAI",
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "xhigh",
        timeoutSeconds: 60,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
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
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

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
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith("Reasoning effort must be 128 characters or fewer."),
    );
    expect(createModelConnectionMock).not.toHaveBeenCalled();
  });

  it("loads existing custom reasoning effort values into the custom input", () => {
    paramsMock.modelConnectionId = "4";
    const customConnection = { ...existingConnection, reasoningEffort: "experimental-reasoning" };
    useModelConnectionMock.mockImplementation(() => ({
      data: customConnection,
      error: null,
      isError: false,
      isPending: false,
    }));

    render(<ModelConnectionsEditorPage />);

    expect(screen.getByLabelText(/^Reasoning Effort$/i)).toHaveTextContent("Custom...");
    expect(screen.getByLabelText(/^Custom Reasoning Effort$/i)).toHaveValue("experimental-reasoning");
    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        name: "Primary OpenAI",
        description: "Production OpenAI connection.",
        apiStyle: "chat_completions",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "experimental-reasoning",
        timeoutSeconds: 90,
      }),
    );
  });

  it("submits Chat Completions API style when selected", async () => {
    createModelConnectionMock.mockResolvedValue({ id: 10 });

    render(<ModelConnectionsEditorPage />);

    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Compatible Chat" } });
    fireEvent.change(screen.getByLabelText(/^Key$/i), { target: { value: "compatible_chat" } });
    fireEvent.change(screen.getByLabelText(/^Model ID$/i), { target: { value: "third-party-chat" } });
    const apiStyleSelect = screen.getByLabelText(/^API Style$/i);
    apiStyleSelect.focus();
    fireEvent.keyDown(apiStyleSelect, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", {
      name: /chat completions api - legacy \/ openai-compatible/i,
    }));
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
    expect(createModelConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({ apiStyle: "chat_completions" }),
    );
  });

  it("masks an entered apiKey in the exact config preview", () => {
    render(<ModelConnectionsEditorPage />);

    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI" } });
    fireEvent.change(screen.getByLabelText(/^Key$/i), { target: { value: "primary_openai" } });
    fireEvent.change(screen.getByLabelText(/^Model ID$/i), { target: { value: "gpt-4.1" } });
    fireEvent.change(screen.getByLabelText(/^API Key$/i), { target: { value: "redacted-live-secret" } });

    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        key: "primary_openai",
        name: "Primary OpenAI",
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "medium",
        timeoutSeconds: 60,
        apiKey: "••••••••",
      }),
    );
    expect(screen.getByLabelText(/exact config json/i)).not.toHaveValue(
      expect.stringContaining("redacted-live-secret"),
    );
  });

  it("keeps the secret blank on edit and preserves the existing key when save omits apiKey", async () => {
    paramsMock.modelConnectionId = "4";
    updateModelConnectionMock.mockResolvedValue({ id: 4 });

    render(<ModelConnectionsEditorPage />);

    expect(screen.getByLabelText(/^API Key$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^Key$/i)).toHaveValue("primary_openai");
    expect(screen.getByLabelText(/^Key$/i)).toBeDisabled();

    expect(screen.getByText(/leave blank to keep the offline path credential-free\./i)).toBeVisible();
    expect(screen.getByText(/last test passed/i)).toBeVisible();
    expect(screen.getByLabelText(/^API Style$/i)).toHaveTextContent(
      "Chat Completions API - legacy / OpenAI-compatible",
    );
    expect(screen.getByLabelText(/exact config json/i)).toHaveValue(
      stringifyJson({
        name: "Primary OpenAI",
        description: "Production OpenAI connection.",
        apiStyle: "chat_completions",
        baseUrl: "https://api.openai.com/v1",
        modelId: "gpt-4.1",
        reasoningEffort: "high",
        timeoutSeconds: 90,
      }),
    );
    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(updateModelConnectionMock).toHaveBeenCalledTimes(1));
    const updateCall = updateModelConnectionMock.mock.calls[0][0];
    expect(updateCall.modelConnectionId).toBe("4");
    expect(updateCall.payload).toMatchObject({
      apiStyle: "chat_completions",
      baseUrl: "https://api.openai.com/v1",
      description: "Production OpenAI connection.",
      modelId: "gpt-4.1",
      name: "Primary OpenAI Updated",
      reasoningEffort: "high",
      timeoutSeconds: 90,
    });
    expect(updateCall.payload).not.toHaveProperty("apiKey");
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

    await waitFor(() => expect(screen.getByTestId("model-connection-feedback")).toBeVisible());
    expect(screen.getByText(/connection succeeded/i)).toBeVisible();
    expect(screen.getByText(/connection ok/i)).toBeVisible();
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

    await waitFor(() => expect(screen.getByTestId("model-connection-feedback")).toBeVisible());
    expect(screen.getByText(/connection failed/i)).toBeVisible();
    expect(screen.getByText(/key rejected/i)).toBeVisible();
    expect(toastErrorMock).toHaveBeenCalledWith("Key rejected");
  });
});
