import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  apiKeyLast4: "4242",
  baseUrl: "https://api.openai.com/v1",
  createdAt: "2026-04-21T12:00:00Z",
  description: "Production OpenAI connection.",
  hasApiKey: true,
  id: 4,
  lastTestMessage: "Healthy",
  lastTestOk: true,
  lastTestedAt: "2026-04-22T08:30:00Z",
  modelId: "gpt-4.1",
  name: "Primary OpenAI",
  organization: "org_live",
  project: "proj_live",
  reasoningEffort: "high",
  status: "active",
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

vi.mock("@/hooks/use-model-connections", () => ({
  useCreateModelConnection: () => ({ isPending: false, mutateAsync: createModelConnectionMock }),
  useModelConnection: (modelConnectionId?: string) => useModelConnectionMock(modelConnectionId),
  useTestModelConnection: () => ({ isPending: false, mutateAsync: testModelConnectionMock }),
  useUpdateModelConnection: () => ({ isPending: false, mutateAsync: updateModelConnectionMock }),
}));

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

    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI" } });
    fireEvent.change(screen.getByLabelText(/^Model ID$/i), { target: { value: "gpt-4.1" } });
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(createModelConnectionMock).toHaveBeenCalledTimes(1));
    expect(createModelConnectionMock).toHaveBeenCalledWith({
      baseUrl: "https://api.openai.com/v1",
      modelId: "gpt-4.1",
      name: "Primary OpenAI",
      reasoningEffort: "medium",
      timeoutSeconds: 60,
    });
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/9/edit");
  });

  it("keeps the secret blank on edit and preserves the existing key when save omits apiKey", async () => {
    paramsMock.modelConnectionId = "4";
    updateModelConnectionMock.mockResolvedValue({ id: 4 });

    render(<ModelConnectionsEditorPage />);

    expect(screen.getByLabelText(/^API Key$/i)).toHaveValue("");
    expect(screen.getByText(/leave blank to keep current key ending in ••••4242\./i)).toBeVisible();
    expect(screen.getByText(/last test passed/i)).toBeVisible();

    fireEvent.change(screen.getByLabelText(/^Name$/i), { target: { value: "Primary OpenAI Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save model connection/i }));

    await waitFor(() => expect(updateModelConnectionMock).toHaveBeenCalledTimes(1));
    const updateCall = updateModelConnectionMock.mock.calls[0][0];
    expect(updateCall.modelConnectionId).toBe("4");
    expect(updateCall.payload).toMatchObject({
      baseUrl: "https://api.openai.com/v1",
      description: "Production OpenAI connection.",
      modelId: "gpt-4.1",
      name: "Primary OpenAI Updated",
      organization: "org_live",
      project: "proj_live",
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
