import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReportRead } from "@/lib/types/report";

import { ReportListPage } from "./list";

const {
  compileReportMutateMock,
  deleteReportMutateMock,
  deleteReportsMutateMock,
  uploadReportMutateMock,
  useReportsMock,
  useTemplatesMock,
} = vi.hoisted(() => ({
  compileReportMutateMock: vi.fn(),
  deleteReportMutateMock: vi.fn(),
  deleteReportsMutateMock: vi.fn(),
  uploadReportMutateMock: vi.fn(),
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
  useReports: () => useReportsMock(),
  useUploadReport: () => ({ isPending: false, mutate: uploadReportMutateMock }),
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplates: () => useTemplatesMock(),
}));

function buildReport(overrides: Partial<ReportRead> = {}): ReportRead {
  return {
    id: 1,
    name: "Daily Market Brief",
    slug: "daily_market_brief",
    source: "compiled",
    content: "# Daily Market Brief",
    metadata: {
      author: "Research Desk",
      description: "Daily summary",
      tags: ["market"],
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

function renderReportsList() {
  const router = createMemoryRouter(
    [{ path: "/reports", element: <ReportListPage /> }],
    { initialEntries: ["/reports"] },
  );

  render(<RouterProvider router={router} />);
  return router;
}

describe("ReportListPage", () => {
  beforeEach(() => {
    compileReportMutateMock.mockReset();
    deleteReportMutateMock.mockReset();
    deleteReportsMutateMock.mockReset();
    uploadReportMutateMock.mockReset();
    useReportsMock.mockReset();
    useTemplatesMock.mockReset();
    useReportsMock.mockReturnValue(queryResult([]));
    useTemplatesMock.mockReturnValue(queryResult({ items: [] }));
  });

  it("renders shared inventory chrome and empty-state copy", () => {
    renderReportsList();

    expect(screen.getByRole("heading", { name: "Reports" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Generate Report" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Upload Report" })).toBeVisible();
    expect(screen.getByLabelText("Search reports")).toBeVisible();
    expect(screen.getByLabelText("Group reports")).toBeVisible();
    expect(screen.getByText("Total")).toBeVisible();
    expect(screen.getByText("Shown")).toBeVisible();
    expect(screen.getByText("Showing 0 of 0 reports")).toBeVisible();
    expect(screen.getByText("No reports yet.")).toBeVisible();
    expect(
      screen.getByText("Generate one from a template or upload a markdown file."),
    ).toBeVisible();
  });

  it("surfaces report loading errors inside the inventory state panel", () => {
    useReportsMock.mockReturnValue({
      data: undefined,
      error: new Error("Reports API unavailable"),
      isError: true,
      isPending: false,
    });

    renderReportsList();

    expect(screen.getByText("Error")).toBeVisible();
    expect(screen.getByText("Reports could not be loaded")).toBeVisible();
    expect(screen.getByText("Reports API unavailable")).toBeVisible();
  });

  it("keeps upload request ownership in the route", () => {
    const router = renderReportsList();
    const file = new File(["# Uploaded"], "Uploaded Brief.md", {
      type: "text/markdown",
    });

    fireEvent.click(screen.getByRole("button", { name: "Upload Report" }));
    fireEvent.change(screen.getByLabelText("Markdown File"), {
      target: { files: [file] },
    });
    expect(screen.getByLabelText("Slug")).toHaveValue("uploaded_brief");

    fireEvent.change(screen.getByLabelText("Author (optional)"), {
      target: { value: "Research Desk" },
    });
    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "Uploaded report" },
    });
    fireEvent.change(screen.getByLabelText("Tags (optional)"), {
      target: { value: "market, uploaded" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Upload" }).closest("form")!);

    expect(uploadReportMutateMock).toHaveBeenCalledTimes(1);
    const [formData, callbacks] = uploadReportMutateMock.mock.calls[0];
    expect(formData.get("file")).toBe(file);
    expect(formData.get("slug")).toBe("uploaded_brief");
    expect(formData.get("author")).toBe("Research Desk");
    expect(formData.get("description")).toBe("Uploaded report");
    expect(formData.get("tags")).toBe("market, uploaded");

    callbacks.onSuccess(
      buildReport({ name: "Uploaded Brief", slug: "uploaded_brief", source: "uploaded" }),
    );
    expect(router.state.location.pathname).toBe("/reports/uploaded_brief");
  });
});
