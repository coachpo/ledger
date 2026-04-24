import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelConnectionsListPage } from "./list";

const {
  archiveModelConnectionMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  useModelConnectionsMock,
} = vi.hoisted(() => ({
  archiveModelConnectionMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  useModelConnectionsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-model-connections", () => ({
  useArchiveModelConnection: () => ({ isPending: false, mutateAsync: archiveModelConnectionMock }),
  useModelConnections: () => useModelConnectionsMock(),
}));

describe("ModelConnectionsListPage", () => {
  beforeEach(() => {
    archiveModelConnectionMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    useModelConnectionsMock.mockReturnValue({
      data: {
        items: [
          {
            apiKeyLast4: "4242",
            baseUrl: "https://api.openai.com/v1",
            description: "Production traffic",
            hasApiKey: true,
            id: 9,
            lastTestMessage: "Connection OK",
            lastTestOk: true,
            lastTestedAt: "2026-04-22T08:00:00Z",
            modelId: "gpt-4.1",
            name: "Primary OpenAI",
            organization: "org_live",
            project: "proj_live",
            reasoningEffort: "high",
            status: "active",
            timeoutSeconds: 90,
          },
          {
            apiKeyLast4: null,
            baseUrl: "https://archive.openai.com/v1",
            description: "Historical fallback",
            hasApiKey: false,
            id: 4,
            lastTestMessage: "Key rejected",
            lastTestOk: false,
            lastTestedAt: "2026-04-21T08:00:00Z",
            modelId: "gpt-4o-mini",
            name: "Legacy Archive",
            organization: null,
            project: null,
            reasoningEffort: "low",
            status: "archived",
            timeoutSeconds: 45,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders rows, archives active connections, and navigates to create and edit routes", async () => {
    archiveModelConnectionMock.mockResolvedValue({ id: 9 });

    render(<ModelConnectionsListPage />);

    expect(screen.getByTestId("model-connections-row-9")).toBeVisible();
    expect(screen.getByTestId("model-connections-row-4")).toBeVisible();
    expect(screen.getByText(/ending in ••••4242/i)).toBeVisible();
    expect(screen.getByText(/no api key saved\./i)).toBeVisible();
    expect(screen.getByText(/^passed$/i)).toBeVisible();
    expect(screen.getByText(/^failed$/i)).toBeVisible();
    expect(screen.queryByTestId("model-connections-archive-4")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("model-connections-archive-9"));
    await waitFor(() => expect(archiveModelConnectionMock).toHaveBeenCalledWith(9));
    expect(toastSuccessMock).toHaveBeenCalledWith("Model connection archived");

    fireEvent.click(screen.getByTestId("model-connections-new"));
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/new");

    fireEvent.click(screen.getByTestId("model-connections-open-9"));
    expect(navigateMock).toHaveBeenCalledWith("/model-connections/9/edit");
  });
});
