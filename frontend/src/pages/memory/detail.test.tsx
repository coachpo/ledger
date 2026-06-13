import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  MemoryAdminEntryRead,
  MemoryAdminEventListRead,
  MemoryAdminRevisionListRead,
} from "@/lib/types/memory";

import { MemoryDetailPage } from "./detail";

const {
  createAdminMemoryRevisionMock,
  updateAdminMemoryStatusMock,
  useAdminMemoryEntryMock,
  useAdminMemoryEventsMock,
  useAdminMemoryRevisionsMock,
} = vi.hoisted(() => ({
  createAdminMemoryRevisionMock: vi.fn(),
  updateAdminMemoryStatusMock: vi.fn(),
  useAdminMemoryEntryMock: vi.fn(),
  useAdminMemoryEventsMock: vi.fn(),
  useAdminMemoryRevisionsMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-memory", () => ({
  useAdminMemoryEntry: (...args: unknown[]) => useAdminMemoryEntryMock(...args),
  useAdminMemoryEvents: (...args: unknown[]) =>
    useAdminMemoryEventsMock(...args),
  useAdminMemoryRevisions: (...args: unknown[]) =>
    useAdminMemoryRevisionsMock(...args),
  useCreateAdminMemoryRevision: () => ({
    isPending: false,
    mutateAsync: createAdminMemoryRevisionMock,
  }),
  useUpdateAdminMemoryStatus: () => ({
    isPending: false,
    mutateAsync: updateAdminMemoryStatusMock,
  }),
}));

const detailFixture: MemoryAdminEntryRead = {
  attributes: { confidence: "high" },
  auditLinks: null,
  content: "Risk memo content with operator visibility.",
  createdAt: "2026-05-20T10:00:00Z",
  kind: "insight",
  memoryId: "mem-risk-1",
  outcome: {
    attributes: { source: "operator" },
    observedAt: "2026-05-20T10:05:00Z",
    status: "approved",
    summary: "Approved operator memory",
  },
  provenance: {
    agentKey: "local-instance-operator",
    agentVersion: 1,
    createdByType: "operator",
    runId: 41,
    workflowKey: "risk-review",
  },
  reflections: [],
  revision: {
    contentHash: "hash-risk-1",
    createdAt: "2026-05-20T10:00:00Z",
    revisionId: "rev-risk-1",
    version: 1,
  },
  revisionId: "rev-risk-1",
  scope: { scopeKey: "pkg_alpha", scopeType: "package" },
  status: "approved",
  subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
  summary: "Risk review memory",
  updatedAt: "2026-05-20T10:05:00Z",
};

const revisionsFixture: MemoryAdminRevisionListRead = {
  count: 1,
  items: [
    {
      attributes: { confidence: "high" },
      content: "Risk memo content with operator visibility.",
      contentHash: "hash-risk-1",
      createdAt: "2026-05-20T10:00:00Z",
      revisionAction: "created",
      revisionId: "rev-risk-1",
      sourceAgentKey: "local-instance-operator",
      sourceRunId: 41,
      status: "approved",
      subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
      summary: "Risk review memory",
      version: 1,
    },
  ],
  limit: 50,
  offset: 0,
};

const eventsFixture: MemoryAdminEventListRead = {
  count: 1,
  items: [
    {
      budget: { max: 3 },
      createdAt: "2026-05-20T10:06:00Z",
      eventId: 99,
      eventType: "operator_created",
      excerpt: "Risk memo content",
      filters: { kind: "insight" },
      memoryId: "mem-risk-1",
      resultSnapshot: { count: 1 },
      revisionId: "rev-risk-1",
      runId: 41,
      statusSnapshot: { status: "approved" },
    },
  ],
  limit: 50,
  offset: 0,
};

function idleQuery(data?: unknown) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function renderDetail(initialEntry = "/memory/mem-risk-1") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<MemoryDetailPage />} path="/memory/:memoryId" />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MemoryDetailPage", () => {
  beforeEach(() => {
    createAdminMemoryRevisionMock.mockReset();
    updateAdminMemoryStatusMock.mockReset();
    useAdminMemoryEntryMock.mockReset();
    useAdminMemoryEventsMock.mockReset();
    useAdminMemoryRevisionsMock.mockReset();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
    useAdminMemoryEntryMock.mockReturnValue(idleQuery(detailFixture));
    useAdminMemoryRevisionsMock.mockReturnValue(idleQuery(revisionsFixture));
    useAdminMemoryEventsMock.mockReturnValue(idleQuery(eventsFixture));
    createAdminMemoryRevisionMock.mockResolvedValue(detailFixture);
    updateAdminMemoryStatusMock.mockResolvedValue(detailFixture);
  });

  it("queries detail, revisions, and audit events from the route param", () => {
    renderDetail();

    expect(screen.getByTestId("memory-detail-page")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "Risk review memory" }),
    ).toBeVisible();
    expect(useAdminMemoryEntryMock).toHaveBeenLastCalledWith("mem-risk-1", {
      enabled: true,
    });
    expect(useAdminMemoryRevisionsMock).toHaveBeenLastCalledWith(
      "mem-risk-1",
      {},
      { enabled: true },
    );
    expect(useAdminMemoryEventsMock).toHaveBeenLastCalledWith(
      "mem-risk-1",
      {},
      { enabled: true },
    );
    expect(screen.getByTestId("memory-detail-panel")).toHaveTextContent(
      "operator · local-instance-operator@1",
    );
    expect(screen.getByTestId("memory-detail-panel")).toHaveTextContent(
      "Latest revision",
    );
    expect(screen.getByRole("link", { name: "Memory Admin" })).toHaveAttribute(
      "href",
      "/memory",
    );
  });

  it("renders revision history and audit events in routed tabs", () => {
    renderDetail();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Revisions" }), {
      button: 0,
    });
    expect(screen.getByTestId("memory-revisions-panel")).toHaveTextContent(
      "v1",
    );
    expect(screen.getByTestId("memory-revisions-panel")).toHaveTextContent(
      "Risk review memory",
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Audit events" }), {
      button: 0,
    });
    expect(screen.getByTestId("memory-events-panel")).toHaveTextContent(
      "operator_created",
    );
    expect(screen.getByTestId("memory-events-panel")).toHaveTextContent(
      "Risk memo content",
    );
  });

  it("supports revise and lifecycle status update mutations", async () => {
    renderDetail();

    fireEvent.click(screen.getByRole("button", { name: "Revise" }));
    const revisionDialog = screen.getByRole("dialog");
    fireEvent.change(
      within(revisionDialog).getByLabelText("Revision summary"),
      { target: { value: "Updated summary" } },
    );
    fireEvent.change(
      within(revisionDialog).getByLabelText("Revision content"),
      { target: { value: "Updated memory body." } },
    );
    fireEvent.click(
      within(revisionDialog).getByRole("button", { name: "Create revision" }),
    );

    await waitFor(() =>
      expect(createAdminMemoryRevisionMock).toHaveBeenCalledWith({
        memoryId: "mem-risk-1",
        payload: expect.objectContaining({
          content: "Updated memory body.",
          provenance: expect.objectContaining({ createdByType: "operator" }),
          summary: "Updated summary",
        }),
      }),
    );

    fireEvent.change(screen.getByLabelText("Status summary"), {
      target: { value: "Ready for workflow lookup" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));

    await waitFor(() =>
      expect(updateAdminMemoryStatusMock).toHaveBeenCalledWith({
        memoryId: "mem-risk-1",
        payload: expect.objectContaining({
          status: "approved",
          summary: "Ready for workflow lookup",
        }),
      }),
    );
  });

  it("surfaces revise and status mutation failures", async () => {
    createAdminMemoryRevisionMock.mockRejectedValueOnce(new Error("revise failed"));
    updateAdminMemoryStatusMock.mockRejectedValueOnce(new Error("status failed"));
    renderDetail();

    fireEvent.click(screen.getByRole("button", { name: "Revise" }));
    const revisionDialog = screen.getByRole("dialog");
    fireEvent.change(
      within(revisionDialog).getByLabelText("Revision summary"),
      { target: { value: "Updated summary" } },
    );
    fireEvent.change(
      within(revisionDialog).getByLabelText("Revision content"),
      { target: { value: "Updated memory body." } },
    );
    fireEvent.click(
      within(revisionDialog).getByRole("button", { name: "Create revision" }),
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("revise failed"),
    );
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Cancel",
      }),
    );

    fireEvent.change(screen.getByLabelText("Status summary"), {
      target: { value: "Ready for workflow lookup" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("status failed"),
    );
  });

  it("renders a detail error state with back navigation", () => {
    useAdminMemoryEntryMock.mockReturnValue({
      data: undefined,
      error: new Error("not found"),
      isError: true,
      isPending: false,
    });

    renderDetail();

    expect(screen.getByTestId("memory-detail-error")).toHaveTextContent(
      "Unable to load memory detail",
    );
    expect(screen.getByTestId("memory-detail-error")).toHaveTextContent(
      "not found",
    );
    expect(
      screen.getByRole("link", { name: "Back to Memory Admin" }),
    ).toHaveAttribute("href", "/memory");
  });
});
