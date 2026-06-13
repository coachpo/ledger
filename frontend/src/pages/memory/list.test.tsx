import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  MemoryAdminEntryRead,
  MemoryAdminEventListRead,
  MemoryAdminListItemRead,
  MemoryAdminListRead,
  MemoryAdminRevisionListRead,
} from "@/lib/types/memory";

import { MemoryListPage } from "./list";

const {
  createAdminMemoryEntryMock,
  createAdminMemoryRevisionMock,
  updateAdminMemoryStatusMock,
  useAdminMemoryEntryMock,
  useAdminMemoryEntriesMock,
  useAdminMemoryEventsMock,
  useAdminMemoryRevisionsMock,
} = vi.hoisted(() => ({
  createAdminMemoryEntryMock: vi.fn(),
  createAdminMemoryRevisionMock: vi.fn(),
  updateAdminMemoryStatusMock: vi.fn(),
  useAdminMemoryEntryMock: vi.fn(),
  useAdminMemoryEntriesMock: vi.fn(),
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
  useAdminMemoryEntries: (...args: unknown[]) => useAdminMemoryEntriesMock(...args),
  useAdminMemoryEntry: (...args: unknown[]) => useAdminMemoryEntryMock(...args),
  useAdminMemoryEvents: (...args: unknown[]) => useAdminMemoryEventsMock(...args),
  useAdminMemoryRevisions: (...args: unknown[]) => useAdminMemoryRevisionsMock(...args),
  useCreateAdminMemoryEntry: () => ({ isPending: false, mutateAsync: createAdminMemoryEntryMock }),
  useCreateAdminMemoryRevision: () => ({ isPending: false, mutateAsync: createAdminMemoryRevisionMock }),
  useUpdateAdminMemoryStatus: () => ({ isPending: false, mutateAsync: updateAdminMemoryStatusMock }),
}));

function adminListItem(overrides: Partial<MemoryAdminListItemRead> = {}): MemoryAdminListItemRead {
  return {
    createdAt: "2026-05-20T10:00:00Z",
    excerpt: "Risk memo content with operator visibility.",
    kind: "insight",
    lastEventType: "operator_created",
    memoryId: "mem-risk-1",
    provenance: {
      agentKey: "local-instance-operator",
      agentVersion: 1,
      createdByType: "operator",
      runId: 41,
      workflowKey: "risk-review",
    },
    revisionId: "rev-risk-1",
    scope: { scopeKey: "pkg_alpha", scopeType: "package" },
    status: "resolved",
    subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
    summary: "Risk review memory",
    updatedAt: "2026-05-20T10:05:00Z",
    ...overrides,
  };
}

const detailFixture: MemoryAdminEntryRead = {
  ...adminListItem(),
  attributes: { confidence: "high" },
  auditLinks: null,
  content: "Risk memo content with operator visibility.",
  outcome: {
    attributes: { source: "operator" },
    observedAt: "2026-05-20T10:05:00Z",
    status: "resolved",
    summary: "Resolved operator memory",
  },
  reflections: [],
  revision: {
    contentHash: "hash-risk-1",
    createdAt: "2026-05-20T10:00:00Z",
    revisionId: "rev-risk-1",
    version: 1,
  },
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
      status: "resolved",
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
      statusSnapshot: { status: "resolved" },
    },
  ],
  limit: 50,
  offset: 0,
};

function listResponse(items: MemoryAdminListItemRead[]): MemoryAdminListRead {
  return {
    items,
    limit: 50,
    offset: 0,
    sort: "updatedAtDesc",
    total: items.length,
  };
}

function idleQuery(data?: unknown) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function renderPage(initialEntry = "/memory") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <MemoryListPage />
    </MemoryRouter>,
  );
}

describe("MemoryListPage", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1024,
    });
    createAdminMemoryEntryMock.mockReset();
    createAdminMemoryRevisionMock.mockReset();
    updateAdminMemoryStatusMock.mockReset();
    useAdminMemoryEntryMock.mockReset();
    useAdminMemoryEntriesMock.mockReset();
    useAdminMemoryEventsMock.mockReset();
    useAdminMemoryRevisionsMock.mockReset();
    useAdminMemoryEntriesMock.mockReturnValue(idleQuery(listResponse([])));
    useAdminMemoryEntryMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? detailFixture : undefined),
    );
    useAdminMemoryRevisionsMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? revisionsFixture : undefined),
    );
    useAdminMemoryEventsMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? eventsFixture : undefined),
    );
    createAdminMemoryEntryMock.mockResolvedValue(detailFixture);
    createAdminMemoryRevisionMock.mockResolvedValue(detailFixture);
    updateAdminMemoryStatusMock.mockResolvedValue(detailFixture);
  });

  it("requests the admin list immediately with default params and no old gates", () => {
    renderPage();

    expect(screen.getByTestId("memory-list-page")).toBeVisible();
    expect(screen.getByTestId("workspace-page-shell-context")).toContainElement(
      screen.getByTestId("memory-admin-notice"),
    );
    expect(screen.getByRole("heading", { level: 1, name: "Memory" })).toBeVisible();
    expect(screen.getByTestId("memory-admin-notice")).toHaveTextContent("trusted local operator console");
    expect(screen.getByTestId("memory-split-inspector")).toHaveAttribute("data-inspector-state", "closed");
    expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith({}, { enabled: true });
    expect(screen.queryByTestId(["memory", "access", "required"].join("-"))).not.toBeInTheDocument();
    expect(screen.queryByTestId(["memory", "explicit", "scope", "required"].join("-"))).not.toBeInTheDocument();
  });

  it("distinguishes the default empty corpus from filtered-empty results", () => {
    const { unmount } = renderPage();

    expect(screen.getByTestId("memory-empty-state-panel")).toHaveTextContent(
      "No canonical memory exists yet",
    );
    expect(screen.getByTestId("memory-empty-state-panel")).not.toHaveTextContent(
      "filters narrowed",
    );

    unmount();
    renderPage("/memory?packageKey=pkg_alpha");

    expect(screen.getByTestId("memory-empty-state-panel")).toHaveTextContent(
      "No memory entries match these filters",
    );
    expect(screen.getByTestId("memory-empty-state-panel")).toHaveTextContent(
      "filters narrowed the operator corpus to zero",
    );
  });

  it("renders rows from different packages, scopes, and statuses together as intended operator visibility", () => {
    useAdminMemoryEntriesMock.mockReturnValue(
      idleQuery(listResponse([
        adminListItem(),
        adminListItem({
          excerpt: "Beta workflow finding",
          memoryId: "mem-beta-2",
          scope: { scopeKey: "beta-agent", scopeType: "agent" },
          status: "pending",
          summary: "Beta package memory",
        }),
        adminListItem({
          excerpt: "Expired gamma workflow finding",
          memoryId: "mem-gamma-3",
          scope: { scopeKey: "gamma-workflow", scopeType: "workflow" },
          status: "expired",
          summary: "Gamma expired memory",
        }),
      ])),
    );

    renderPage();

    expect(screen.getByText("Rows from different packages and scopes can appear together by design.")).toBeVisible();
    expect(screen.getByTestId("memory-row-mem-risk-1")).toHaveTextContent("Package pkg_alpha");
    expect(screen.getByTestId("memory-row-mem-beta-2")).toHaveTextContent("Agent beta-agent");
    expect(screen.getByTestId("memory-row-mem-beta-2")).toHaveTextContent("pending");
    expect(screen.getByTestId("memory-row-mem-gamma-3")).toHaveTextContent("Workflow gamma-workflow");
    expect(screen.getByTestId("memory-row-mem-gamma-3")).toHaveTextContent("expired");
  });

  it("applies URL filters as optional admin params and reset restores the full corpus", async () => {
    renderPage(
      "/memory?packageKey=pkg_alpha&workflowKey=risk-review&agentKey=analyst&runId=41&scopeType=agent&kind=insight&status=resolved&query=drawdown",
    );

    expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith(
      {
        agentKey: "analyst",
        kind: "insight",
        packageKey: "pkg_alpha",
        query: "drawdown",
        runId: 41,
        scopeType: "agent",
        status: "resolved",
        workflowKey: "risk-review",
      },
      { enabled: true },
    );

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));

    await waitFor(() => expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith({}, { enabled: true }));
  });

  it("narrows the corpus when filter fields change", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Package key"), { target: { value: "pkg_beta" } });
    fireEvent.change(screen.getByLabelText("Workflow key"), { target: { value: "audit" } });
    fireEvent.change(screen.getByLabelText("Agent key"), { target: { value: "reviewer" } });
    fireEvent.change(screen.getByLabelText("Run id"), { target: { value: "77" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "lesson" } });
    fireEvent.change(screen.getByLabelText("Search canonical memory"), { target: { value: "liquidity" } });

    await waitFor(() =>
      expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          agentKey: "reviewer",
          kind: "lesson",
          packageKey: "pkg_beta",
          query: "liquidity",
          runId: 77,
          workflowKey: "audit",
        }),
        { enabled: true },
      ),
    );
  });

  it("opens admin detail, revision history, and audit history inline", async () => {
    useAdminMemoryEntriesMock.mockReturnValue(idleQuery(listResponse([adminListItem()])));

    renderPage();
    const row = screen.getByTestId("memory-row-mem-risk-1");
    fireEvent.click(within(row).getByRole("button", { name: "Open memory" }));

    await waitFor(() =>
      expect(screen.getByTestId("memory-split-inspector")).toHaveAttribute("data-inspector-state", "open"),
    );
    expect(useAdminMemoryEntryMock).toHaveBeenLastCalledWith("mem-risk-1", { enabled: true });
    expect(screen.getByTestId("memory-detail-panel")).toHaveTextContent("operator · local-instance-operator@1");
    expect(screen.getByTestId("memory-detail-panel")).toHaveTextContent("Latest revision");

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Revisions" }), { button: 0 });
    expect(screen.getByTestId("memory-revisions-panel")).toHaveTextContent("v1");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Audit events" }), { button: 0 });
    expect(screen.getByTestId("memory-events-panel")).toHaveTextContent("operator_created");
  });

  it("opens selected memory in the mobile sheet", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 390,
    });
    useAdminMemoryEntriesMock.mockReturnValue(idleQuery(listResponse([adminListItem()])));

    renderPage();
    expect(screen.getByTestId("memory-sheet-inspector")).toHaveAttribute("data-inspector-mode", "sheet");
    expect(screen.queryByTestId("memory-split-inspector")).not.toBeInTheDocument();

    fireEvent.click(within(screen.getByTestId("memory-row-mem-risk-1")).getByRole("button", { name: "Open memory" }));

    await waitFor(() =>
      expect(screen.getByTestId("memory-sheet-inspector")).toHaveAttribute("data-inspector-state", "open"),
    );
    expect(screen.getByTestId("split-inspector-sheet-body")).toHaveTextContent("Risk memo content with operator visibility.");
  });

  it("creates admin memory with explicit scope, status, and runtime-impact copy", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Create memory" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByTestId("memory-runtime-impact-copy")).toHaveTextContent("Resolved memory in a matching scope");
    fireEvent.change(within(dialog).getByLabelText("Summary"), { target: { value: "Operator note" } });
    fireEvent.change(within(dialog).getByLabelText("Content"), { target: { value: "Operator-authored canonical memory." } });
    fireEvent.change(within(dialog).getByLabelText("Package key"), { target: { value: "pkg_alpha" } });
    fireEvent.change(within(dialog).getByLabelText("Run id"), { target: { value: "41" } });
    fireEvent.change(within(dialog).getByLabelText("Scope key"), { target: { value: "pkg_alpha" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create memory" }));

    await waitFor(() =>
      expect(createAdminMemoryEntryMock).toHaveBeenCalledWith(
        expect.objectContaining({
          content: "Operator-authored canonical memory.",
          provenance: expect.objectContaining({
            agentKey: "local-instance-operator",
            createdByType: "operator",
            runId: 41,
          }),
          scope: { scopeKey: "pkg_alpha", scopeType: "package" },
          status: "resolved",
          summary: "Operator note",
        }),
      ),
    );
    expect(createAdminMemoryEntryMock.mock.calls[0]?.[0].provenance).not.toHaveProperty(
      "workflowKey",
    );
  });

  it("supports revise and status update flows for the selected admin memory", async () => {
    useAdminMemoryEntriesMock.mockReturnValue(idleQuery(listResponse([adminListItem()])));

    renderPage("/memory?memoryId=mem-risk-1");

    fireEvent.click(screen.getByRole("button", { name: "Revise" }));
    const revisionDialog = screen.getByRole("dialog");
    fireEvent.change(within(revisionDialog).getByLabelText("Revision summary"), { target: { value: "Updated summary" } });
    fireEvent.change(within(revisionDialog).getByLabelText("Revision content"), { target: { value: "Updated memory body." } });
    fireEvent.click(within(revisionDialog).getByRole("button", { name: "Create revision" }));

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

    fireEvent.change(screen.getByLabelText("Status summary"), { target: { value: "Ready for workflow lookup" } });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));

    await waitFor(() =>
      expect(updateAdminMemoryStatusMock).toHaveBeenCalledWith({
        memoryId: "mem-risk-1",
        payload: expect.objectContaining({
          status: "resolved",
          summary: "Ready for workflow lookup",
        }),
      }),
    );
  });

  it("does not render old gate copy or removal controls", () => {
    renderPage();

    const page = screen.getByTestId("memory-list-page");
    expect(page).not.toHaveTextContent(["package", "context"].join(" "));
    expect(page).not.toHaveTextContent(["private", "scope"].join(" "));
    expect(page).not.toHaveTextContent(["explicit", "scope"].join("-"));
    expect(page).not.toHaveTextContent(["Access", "context", "required"].join(" "));
    expect(page).not.toHaveTextContent(["Private", "scope", "required"].join(" "));
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bulk/i })).not.toBeInTheDocument();
  });
});
