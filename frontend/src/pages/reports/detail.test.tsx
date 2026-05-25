import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReportRead } from "@/lib/types/report";

import { ReportDetailPage } from "./detail";

const {
  navigateMock,
  updateReportMutateAsyncMock,
  useReportMock,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  updateReportMutateAsyncMock: vi.fn(),
  useReportMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ slug: "agent_memory_snapshot" }),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-reports", () => ({
  useReport: (...args: unknown[]) => useReportMock(...args),
  useUpdateReport: () => ({
    isPending: false,
    mutateAsync: updateReportMutateAsyncMock,
  }),
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
    },
    createdAt: "2026-05-04T10:00:00Z",
    updatedAt: "2026-05-05T10:00:00Z",
    ...overrides,
  };
}

function queryResult<T>(data: T) {
  return {
    data,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
  };
}

describe("ReportDetailPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    updateReportMutateAsyncMock.mockReset();
    updateReportMutateAsyncMock.mockResolvedValue(buildReport());
    useReportMock.mockReset();
    useReportMock.mockReturnValue(queryResult(buildReport()));
  });

  it("renders immutable identity, provenance, and explicit actions before content", () => {
    render(<ReportDetailPage />);

    expect(useReportMock).toHaveBeenCalledWith("agent_memory_snapshot");
    const header = screen.getByTestId("report-detail-header");
    const identity = screen.getByTestId("report-detail-identity");
    expect(header).toHaveClass("rounded-xl", "border", "bg-card");
    expect(within(identity).getByText("Immutable report snapshot")).toHaveClass(
      "uppercase",
      "tracking-wide",
    );
    const heading = screen.getAllByRole("heading", { name: "Memory Snapshot" })[0];
    expect(heading).toHaveAttribute("id", "report-detail-title");
    expect(heading).toHaveClass("break-words", "text-xl", "font-semibold", "tracking-tight");
    expect(within(header).getAllByText("Agent")[0]).toBeVisible();
    expect(within(header).getByText("Slug")).toBeVisible();
    expect(within(header).getByText("agent_memory_snapshot")).toBeVisible();

    const actions = screen.getByTestId("report-detail-actions");
    expect(actions).toHaveClass("flex-wrap", "sm:w-auto");
    expect(within(actions).getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/reports/agent_memory_snapshot/download"),
    );
    expect(within(actions).getByRole("button", { name: /edit/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Report content" })).toBeVisible();
    expect(screen.getByTestId("report-content-pane")).toHaveTextContent("Agent-created report.");
  });

  it("saves only edited markdown content for the slug route", async () => {
    render(<ReportDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(screen.getByRole("heading", { name: "Edit report content" })).toBeVisible();
    const textarea = screen.getByLabelText("Report markdown content");
    expect(textarea).toHaveValue("# Memory Snapshot\n\nAgent-created report.");

    fireEvent.change(textarea, { target: { value: "# Revised\n\nUpdated body." } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(updateReportMutateAsyncMock).toHaveBeenCalledWith({
        slug: "agent_memory_snapshot",
        data: { content: "# Revised\n\nUpdated body." },
      });
    });
  });

  it("keeps report back navigation explicit", () => {
    render(<ReportDetailPage />);

    fireEvent.click(screen.getByRole("button", { name: /reports/i }));

    expect(navigateMock).toHaveBeenCalledWith("/reports");
  });
});
