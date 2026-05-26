import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";

import type { ReportRead } from "@/lib/types/report";

import { ReportDetailPage } from "./detail";
import { ReportListPage } from "./list";

const {
  compileReportMutateMock,
  deleteReportMutateMock,
  deleteReportsMutateMock,
  updateReportMutateAsyncMock,
  uploadReportMutateMock,
  useReportMock,
  useReportsMock,
  useTemplatesMock,
} = vi.hoisted(() => ({
  compileReportMutateMock: vi.fn(),
  deleteReportMutateMock: vi.fn(),
  deleteReportsMutateMock: vi.fn(),
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
  useCompileReport: () => ({
    isPending: false,
    mutate: compileReportMutateMock,
  }),
  useDeleteReport: () => ({ isPending: false, mutate: deleteReportMutateMock }),
  useDeleteReports: () => ({
    isPending: false,
    mutate: deleteReportsMutateMock,
  }),
  useReport: (...args: unknown[]) => useReportMock(...args),
  useReports: () => useReportsMock(),
  useUpdateReport: () => ({
    isPending: false,
    mutateAsync: updateReportMutateAsyncMock,
  }),
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
      author: "SignalDeck Agent",
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
    deleteReportsMutateMock.mockReset();
    updateReportMutateAsyncMock.mockReset();
    uploadReportMutateMock.mockReset();
    useReportMock.mockReset();
    useReportsMock.mockReset();
    useTemplatesMock.mockReset();
    useReportMock.mockReturnValue(queryResult(buildReport()));
    useReportsMock.mockReturnValue(queryResult([buildReport()]));
    useTemplatesMock.mockReturnValue(queryResult({ items: [] }));
  });

  it("renders Agent source badge on report list", () => {
    renderReportRoute("/reports");

    expect(screen.getByLabelText("Search reports")).toBeVisible();
    expect(screen.getByLabelText("Group reports")).toBeVisible();
    const generateAction = screen.getByRole("button", {
      name: /generate report/i,
    });
    const uploadAction = screen.getByRole("button", {
      name: /upload report/i,
    });
    expect(
      generateAction.compareDocumentPosition(uploadAction) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.getByText("Memory Snapshot")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open report Memory Snapshot" }),
    ).toHaveAttribute("href", "/reports/agent_memory_snapshot");
    expect(
      screen.getByRole("link", { name: "View report Memory Snapshot" }),
    ).toHaveAttribute("href", "/reports/agent_memory_snapshot");
    expect(screen.getByText("Agent")).toBeVisible();
    expect(screen.queryByText("External")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: /select all shown reports/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", {
        name: /select report memory snapshot/i,
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    expect(
      screen.queryByRole("checkbox", { name: /select all shown reports/i }),
    ).not.toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(table.parentElement?.parentElement).toHaveClass(
      "min-w-0",
      "max-w-full",
      "rounded-md",
      "border",
    );
    expect(
      within(table).getByRole("button", { name: /sort reports by name/i }),
    ).toBeVisible();
    expect(
      within(table).getByRole("link", { name: "View report Memory Snapshot" }),
    ).toHaveAttribute("href", "/reports/agent_memory_snapshot");
    expect(
      within(table).getAllByRole("checkbox", {
        name: /select reports in memory/i,
      }),
    ).toHaveLength(1);
    expect(
      within(table).getByRole("checkbox", {
        name: /select report memory snapshot/i,
      }),
    ).toBeVisible();
    expect(within(table).getByText("Memory Snapshot")).toBeVisible();
    expect(within(table).getByText("Agent")).toBeVisible();
    expect(within(table).queryByText("External")).not.toBeInTheDocument();
  });

  it("renders Uploaded source badge consistently across list views", () => {
    useReportsMock.mockReturnValue(
      queryResult([
        buildReport({
          id: 43,
          name: "Uploaded Snapshot",
          slug: "uploaded_snapshot",
          source: "uploaded",
        }),
      ]),
    );

    renderReportRoute("/reports");

    expect(screen.getByText("Uploaded Snapshot")).toBeVisible();
    expect(screen.getByText("Uploaded")).toBeVisible();
    expect(screen.queryByText("Agent")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));

    const table = screen.getByRole("table");
    expect(within(table).getByText("Uploaded")).toBeVisible();
    expect(within(table).queryByText("Agent")).not.toBeInTheDocument();
  });

  it("keeps single report delete in an overflow confirmation path", () => {
    renderReportRoute("/reports");

    fireEvent.keyDown(
      screen.getByRole("button", { name: "Open actions for Memory Snapshot" }),
      { key: "Enter" },
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      'Delete "Memory Snapshot"?',
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteReportMutateMock).toHaveBeenCalledWith(
      "agent_memory_snapshot",
      expect.any(Object),
    );
  });

  it("supports selecting multiple reports and batch deleting them", () => {
    useReportsMock.mockReturnValue(
      queryResult([
        buildReport(),
        buildReport({
          id: 43,
          name: "Uploaded Snapshot",
          slug: "uploaded_snapshot",
          source: "uploaded",
        }),
      ]),
    );

    renderReportRoute("/reports");

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    expect(
      screen.queryByRole("checkbox", { name: /select all shown reports/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("checkbox", { name: /select reports in memory/i }),
    ).toHaveLength(1);
    const table = screen.getByRole("table");
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select reports in memory/i }),
    );
    const bulkActions = screen.getByTestId("reports-bulk-actions");
    expect(
      within(bulkActions).getByText("2 of 2 reports selected"),
    ).toBeVisible();
    expect(
      table.compareDocumentPosition(bulkActions) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(
      within(table).queryByText("2 of 2 reports selected"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /download selected/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      within(bulkActions).getByRole("button", { name: /delete selected/i }),
    );

    expect(deleteReportsMutateMock).toHaveBeenCalledWith(
      ["agent_memory_snapshot", "uploaded_snapshot"],
      expect.any(Object),
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("hides bulk actions when the current search filters away selected reports", () => {
    renderReportRoute("/reports");

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select report memory snapshot/i }),
    );
    expect(
      within(screen.getByTestId("reports-bulk-actions")).getByText(
        "1 of 1 reports selected",
      ),
    ).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search reports"), {
      target: { value: "missing" },
    });

    expect(screen.getByText("No reports match your search.")).toBeVisible();
    expect(screen.queryByText(/No reports yet/i)).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("reports-bulk-actions"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete selected/i }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search reports"), {
      target: { value: "" },
    });

    expect(
      within(screen.getByTestId("reports-bulk-actions")).getByText(
        "1 of 1 reports selected",
      ),
    ).toBeVisible();
  });

  it("clears active report selection when switching from table to cards", () => {
    renderReportRoute("/reports");

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select report memory snapshot/i }),
    );
    const bulkActions = screen.getByTestId("reports-bulk-actions");
    expect(
      within(bulkActions).getByText("1 of 1 reports selected"),
    ).toBeVisible();
    expect(
      within(bulkActions).getByRole("button", { name: "Clear" }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("radio", { name: /cards view/i }));
    expect(
      screen.queryByTestId("reports-bulk-actions"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: /select all shown reports/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", {
        name: /select report memory snapshot/i,
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /table view/i }));
    expect(
      screen.getByRole("checkbox", { name: /select report memory snapshot/i }),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.queryByRole("button", { name: /delete selected/i }),
    ).not.toBeInTheDocument();
  });

  it("renders Agent source badge on report detail", () => {
    renderReportRoute("/reports/agent_memory_snapshot");

    expect(useReportMock).toHaveBeenCalledWith("agent_memory_snapshot");
    const detailHeading = screen.getAllByRole("heading", {
      name: /Memory Snapshot/,
    })[0];
    const detailTitle = screen.getByText("Memory Snapshot", {
      selector: "#report-detail-title",
    });
    expect(detailHeading).toBeVisible();
    expect(detailTitle).toHaveClass(
      "break-words",
      "text-xl",
      "font-semibold",
      "tracking-tight",
    );
    expect(detailHeading).not.toHaveClass("truncate", "text-lg");
    expect(screen.getByText("Agent")).toBeVisible();
    expect(screen.queryByText("External")).not.toBeInTheDocument();

    const actions = screen.getByTestId("report-detail-actions");
    expect(actions).toHaveClass("flex-wrap", "sm:w-auto");
    expect(
      within(actions).getByRole("link", { name: /download/i }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("/reports/agent_memory_snapshot/download"),
    );
    expect(
      within(actions).getByRole("button", { name: /edit/i }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /reports/i })).toBeVisible();
  });
});
