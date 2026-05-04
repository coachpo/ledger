import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";

import type { ReportRead } from "@/lib/types/report";

import { ReportDetailPage } from "./detail";
import { ReportListPage } from "./list";

const {
  compileReportMutateMock,
  deleteReportMutateMock,
  updateReportMutateAsyncMock,
  uploadReportMutateMock,
  useReportMock,
  useReportsMock,
  useTemplatesMock,
} = vi.hoisted(() => ({
  compileReportMutateMock: vi.fn(),
  deleteReportMutateMock: vi.fn(),
  updateReportMutateAsyncMock: vi.fn(),
  uploadReportMutateMock: vi.fn(),
  useReportMock: vi.fn(),
  useReportsMock: vi.fn(),
  useTemplatesMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-reports", () => ({
  useCompileReport: () => ({ isPending: false, mutate: compileReportMutateMock }),
  useDeleteReport: () => ({ isPending: false, mutate: deleteReportMutateMock }),
  useReport: (...args: unknown[]) => useReportMock(...args),
  useReports: () => useReportsMock(),
  useUpdateReport: () => ({ isPending: false, mutateAsync: updateReportMutateAsyncMock }),
  useUploadReport: () => ({ isPending: false, mutate: uploadReportMutateMock }),
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplates: () => useTemplatesMock(),
}));

function buildReport(overrides: Partial<ReportRead> = {}): ReportRead {
  return {
    id: 42,
    name: "Memory Snapshot",
    slug: "agent_memory_snapshot",
    source: "agent",
    content: "# Memory Snapshot\n\nAgent-created report.",
    metadata: {
      author: "Ledger Agent",
      description: "Created by an agent run.",
      tags: ["memory"],
      createdBy: {
        type: "agent",
        runId: 904,
        agentKey: "research_agent",
        agentVersion: 3,
      },
    },
    createdAt: "2026-05-04T10:00:00Z",
    updatedAt: "2026-05-04T10:00:00Z",
    ...overrides,
  };
}

function queryResult<T>(data: T) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function renderReportRoute(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/reports", element: <ReportListPage /> },
      { path: "/reports/:slug", element: <ReportDetailPage /> },
    ],
    { initialEntries: [path] },
  );

  render(<RouterProvider router={router} />);
}
describe("report source labels", () => {
  beforeEach(() => {
    compileReportMutateMock.mockReset();
    deleteReportMutateMock.mockReset();
    updateReportMutateAsyncMock.mockReset();
    uploadReportMutateMock.mockReset();
    useReportMock.mockReset();
    useReportsMock.mockReset();
    useTemplatesMock.mockReset();
    useReportMock.mockReturnValue(queryResult(buildReport()));
    useReportsMock.mockReturnValue(queryResult([buildReport()]));
    useTemplatesMock.mockReturnValue(queryResult([]));
  });

  it("renders Agent source badge on report list", () => {
    renderReportRoute("/reports");

    expect(screen.getByText("Memory Snapshot")).toBeVisible();
    expect(screen.getByText("Agent")).toBeVisible();
    expect(screen.queryByText("External")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));

    const table = screen.getByRole("table");
    expect(within(table).getByText("Memory Snapshot")).toBeVisible();
    expect(within(table).getByText("Agent")).toBeVisible();
    expect(within(table).queryByText("External")).not.toBeInTheDocument();
  });

  it("renders Agent source badge on report detail", () => {
    renderReportRoute("/reports/agent_memory_snapshot");

    expect(useReportMock).toHaveBeenCalledWith("agent_memory_snapshot");
    expect(screen.getAllByRole("heading", { name: "Memory Snapshot" })[0]).toBeVisible();
    expect(screen.getByText("Agent")).toBeVisible();
    expect(screen.queryByText("External")).not.toBeInTheDocument();
  });
});
