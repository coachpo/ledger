import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelConnectionsListPage } from "./list";

const {
  deleteModelConnectionMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useModelConnectionsMock,
} = vi.hoisted(() => ({
  deleteModelConnectionMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-model-connections", () => ({
  useDeleteModelConnection: () => ({ isPending: false, mutateAsync: deleteModelConnectionMock }),
  useModelConnections: () => useModelConnectionsMock(),
}));

describe("ModelConnectionsListPage", () => {
  beforeEach(() => {
    deleteModelConnectionMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useModelConnectionsMock.mockReturnValue({
      data: {
        items: [
          {
            apiStyle: "responses",
            baseUrl: "https://api.openai.com/v1",
            connectionKind: "provider",
            description: "Production traffic",
            id: 9,
            key: "primary_openai",
            lastTestMessage: "Connection OK",
            lastTestOk: true,
            lastTestedAt: "2026-04-22T08:00:00Z",
            modelId: "gpt-4.1",
            name: "Primary OpenAI",
            reasoningEffort: null,
            timeoutSeconds: 90,
          },
          {
            apiStyle: "chat_completions",
            baseUrl: "https://backup.openai.com/v1",
            connectionKind: "deterministic_smoke",
            description: "Fallback traffic",
            id: 4,
            key: "legacy_backup",
            lastTestMessage: "Key rejected",
            lastTestOk: false,
            lastTestedAt: "2026-04-21T08:00:00Z",
            modelId: "gpt-4o-mini",
            name: "Legacy Backup",
            reasoningEffort: "xhigh",
            timeoutSeconds: 45,
          },
          {
            apiStyle: "responses",
            baseUrl: "https://literal.openai.com/v1",
            connectionKind: "provider",
            description: "Literal none reasoning value",
            id: 12,
            key: "literal_none",
            lastTestMessage: null,
            lastTestOk: null,
            lastTestedAt: null,
            modelId: "gpt-none-literal",
            name: "Literal None",
            reasoningEffort: "none",
            timeoutSeconds: 30,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders rows, deletes connections, and navigates to create and edit routes", async () => {
    deleteModelConnectionMock.mockResolvedValue(undefined);

    render(<ModelConnectionsListPage />);

    expect(screen.getByText(/workflow packages reference by stable key/i)).toBeVisible();
    expect(screen.getByTestId("model-connections-row-9")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-4")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-12")).toBeVisible();
    expect(screen.getAllByText("Responses API")).toHaveLength(2);
    expect(screen.getByText("Chat Completions API - legacy / OpenAI-compatible")).toBeVisible();
    expect(screen.getByText(/^Omitted$/)).toBeVisible();
    expect(screen.getByText(/^xhigh$/)).toBeVisible();
    expect(screen.getByText(/^none$/)).toBeVisible();
    expect(screen.queryByText(/^medium$/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Provider-backed")).toHaveLength(4);
    expect(screen.getAllByText("Deterministic smoke")).toHaveLength(2);
    expect(screen.getByText(/^passed$/i)).toBeVisible();
    expect(screen.getByText(/^failed$/i)).toBeVisible();

    fireEvent.click(screen.getByTestId("model-connections-delete-9"));
    await waitFor(() => expect(deleteModelConnectionMock).toHaveBeenCalledWith(9));
    expect(toastSuccessMock).toHaveBeenCalledWith("Model connection deleted");

    fireEvent.click(screen.getByTestId("model-connections-new"));
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/new");

    fireEvent.click(screen.getByTestId("model-connections-open-9"));
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/9/edit");
  });

  it("shows blocked delete backend messages without rendering secret payloads", async () => {
    const blockedError = Object.assign(
      new Error("Model connection is used by workflow packages and cannot be deleted."),
      {
        details: [{ field: "apiKey", issue: "sk-live-secret" }],
        ["secret" + "Payload"]: { apiKey: "sk-live-secret" },
      },
    );
    deleteModelConnectionMock.mockRejectedValue(blockedError);

    render(<ModelConnectionsListPage />);
    fireEvent.click(screen.getByTestId("model-connections-delete-9"));

    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Model connection is used by workflow packages and cannot be deleted.",
      ),
    );
    expect(toastErrorMock).not.toHaveBeenCalledWith(expect.stringContaining("sk-live-secret"));
    expect(screen.queryByText(/sk-live-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret payload/i)).not.toBeInTheDocument();
  });
});
