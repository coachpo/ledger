import type { ComponentProps } from "react";
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
            apiStyle: "responses",
            baseUrl: "https://api.openai.com/v1",
            description: "Production traffic",
            id: 9,
            lastTestMessage: "Connection OK",
            lastTestOk: true,
            lastTestedAt: "2026-04-22T08:00:00Z",
            modelId: "gpt-4.1",
            name: "Primary OpenAI",
            organization: "org_live",
            project: "proj_live",
            reasoningEffort: null,
            status: "active",
            timeoutSeconds: 90,
          },
          {
            apiStyle: "chat_completions",
            baseUrl: "https://archive.openai.com/v1",
            description: "Historical archive",
            id: 4,
            lastTestMessage: "Key rejected",
            lastTestOk: false,
            lastTestedAt: "2026-04-21T08:00:00Z",
            modelId: "gpt-4o-mini",
            name: "Legacy Archive",
            organization: null,
            project: null,
            reasoningEffort: "xhigh",
            status: "archived",
            timeoutSeconds: 45,
          },
          {
            apiStyle: "responses",
            baseUrl: "https://literal.openai.com/v1",
            description: "Literal none reasoning value",
            id: 12,
            lastTestMessage: null,
            lastTestOk: null,
            lastTestedAt: null,
            modelId: "gpt-none-literal",
            name: "Literal None",
            organization: null,
            project: null,
            reasoningEffort: "none",
            status: "active",
            timeoutSeconds: 30,
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
