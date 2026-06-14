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
  deleteAdminMemoryEntryMock,
  updateAdminMemoryWorkflowVisibilityMock,
  useAdminMemoryEntryMock,
  useAdminMemoryEventsMock,
  useAdminMemoryRevisionsMock,
} = vi.hoisted(() => ({
  createAdminMemoryRevisionMock: vi.fn(),
  deleteAdminMemoryEntryMock: vi.fn(),
  updateAdminMemoryWorkflowVisibilityMock: vi.fn(),
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
  useDeleteAdminMemoryEntry: () => ({
    isPending: false,
    mutateAsync: deleteAdminMemoryEntryMock,
  }),
  useUpdateAdminMemoryWorkflowVisibility: () => ({
    isPending: false,
    mutateAsync: updateAdminMemoryWorkflowVisibilityMock,
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
    summary: "Workflow-visible operator memory",
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
  subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
  summary: "Risk review memory",
  updatedAt: "2026-05-20T10:05:00Z",
  visibleToWorkflow: true,
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
      subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
      summary: "Risk review memory",
      version: 1,
      visibleToWorkflow: true,
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
      statusSnapshot: { visibleToWorkflow: true },
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

async function chooseSelectOption(label: string, optionName: string | RegExp) {
  const selector = screen.getByRole("combobox", { name: label });
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

function renderDetail(initialEntry = "/memory/mem-risk-1") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          element={<div data-testid="memory-list-route">Memory route</div>}
          path="/memory"
        />
        <Route element={<MemoryDetailPage />} path="/memory/:memoryId" />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MemoryDetailPage", () => {
  beforeEach(() => {
    createAdminMemoryRevisionMock.mockReset();
    deleteAdminMemoryEntryMock.mockReset();
    updateAdminMemoryWorkflowVisibilityMock.mockReset();
    useAdminMemoryEntryMock.mockReset();
    useAdminMemoryEventsMock.mockReset();
    useAdminMemoryRevisionsMock.mockReset();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
    useAdminMemoryEntryMock.mockReturnValue(idleQuery(detailFixture));
    useAdminMemoryRevisionsMock.mockReturnValue(idleQuery(revisionsFixture));
    useAdminMemoryEventsMock.mockReturnValue(idleQuery(eventsFixture));
    createAdminMemoryRevisionMock.mockResolvedValue(detailFixture);
    deleteAdminMemoryEntryMock.mockResolvedValue(undefined);
    updateAdminMemoryWorkflowVisibilityMock.mockResolvedValue(detailFixture);
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
    const eventsPanel = screen.getByTestId("memory-events-panel");
    expect(eventsPanel).toHaveTextContent("operator_created");
    expect(eventsPanel).toHaveTextContent("Risk memo content");
    expect(eventsPanel).toHaveTextContent("Event state snapshot");
    expect(eventsPanel).toHaveTextContent("visibleToWorkflow");
    expect(eventsPanel).not.toHaveTextContent("approved");
    expect(eventsPanel).not.toHaveTextContent("pending");
    expect(eventsPanel).not.toHaveTextContent("archived");
  });

  it("supports revise and workflow visibility update mutations", async () => {
    const hiddenDetail = { ...detailFixture, visibleToWorkflow: false };
    updateAdminMemoryWorkflowVisibilityMock.mockResolvedValue(hiddenDetail);

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

    expect(
      screen.getByTestId("memory-workflow-visibility-form"),
    ).toHaveTextContent("Workflow visible");
    expect(screen.queryByText("New status")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Update status" }),
    ).not.toBeInTheDocument();
    await chooseSelectOption("New workflow visibility", "Workflow hidden");
    expect(
      screen.getByTestId("memory-workflow-visibility-form"),
    ).toHaveTextContent("Workflow hidden");
    fireEvent.change(screen.getByLabelText("Visibility summary"), {
      target: { value: "Hide from workflow lookup" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Update workflow visibility" }),
    );

    await waitFor(() =>
      expect(updateAdminMemoryWorkflowVisibilityMock).toHaveBeenCalledWith({
        memoryId: "mem-risk-1",
        payload: expect.objectContaining({
          summary: "Hide from workflow lookup",
          visibleToWorkflow: false,
        }),
      }),
    );
  });

  it("confirms single-entry detail deletion and redirects to Memory Admin", async () => {
    renderDetail();

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete selected/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete memory" }));
    const cancelDialog = screen.getByRole("alertdialog");
    expect(cancelDialog).toHaveTextContent("Delete memory");
    expect(cancelDialog).toHaveTextContent(
      "This permanently removes this memory entry and its revisions. Existing run evidence keeps snapshot memory ids, but the memory entry will no longer appear in admin search or runtime lookup.",
    );
    fireEvent.click(within(cancelDialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
    expect(deleteAdminMemoryEntryMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("memory-detail-page")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Delete memory" }));
    const confirmDialog = screen.getByRole("alertdialog");
    fireEvent.click(
      within(confirmDialog).getByRole("button", { name: "Delete memory" }),
    );

    await waitFor(() =>
      expect(deleteAdminMemoryEntryMock).toHaveBeenCalledWith("mem-risk-1"),
    );
    expect(deleteAdminMemoryEntryMock).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith("Memory deleted");
    await waitFor(() =>
      expect(screen.getByTestId("memory-list-route")).toBeVisible(),
    );
  });

  it("surfaces delete mutation failures without leaving detail", async () => {
    deleteAdminMemoryEntryMock.mockRejectedValueOnce(new Error("delete failed"));
    renderDetail();

    fireEvent.click(screen.getByRole("button", { name: "Delete memory" }));
    fireEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Delete memory",
      }),
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("delete failed"),
    );
    expect(deleteAdminMemoryEntryMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("memory-detail-page")).toBeVisible();
  });

  it("surfaces revise and workflow visibility mutation failures", async () => {
    createAdminMemoryRevisionMock.mockRejectedValueOnce(
      new Error("revise failed"),
    );
    updateAdminMemoryWorkflowVisibilityMock.mockRejectedValueOnce(
      new Error("visibility failed"),
    );
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

    fireEvent.change(screen.getByLabelText("Visibility summary"), {
      target: { value: "Ready for workflow lookup" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Update workflow visibility" }),
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("visibility failed"),
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
