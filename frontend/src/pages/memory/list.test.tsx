import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "@/lib/api-client";
import type {
  MemoryApiEntryRead,
  MemoryApiEventListRead,
  MemoryApiListItemRead,
  MemoryApiListRead,
  MemoryApiRevisionListRead,
} from "@/lib/types/memory";

import { MemoryListPage } from "./list";

const {
  useMemoryDetailMock,
  useMemoryEventsMock,
  useMemoryListMock,
  useMemoryRevisionsMock,
} = vi.hoisted(() => ({
  useMemoryDetailMock: vi.fn(),
  useMemoryEventsMock: vi.fn(),
  useMemoryListMock: vi.fn(),
  useMemoryRevisionsMock: vi.fn(),
}));

vi.mock("@/hooks/use-memory", () => ({
  useMemoryDetail: (...args: unknown[]) => useMemoryDetailMock(...args),
  useMemoryEvents: (...args: unknown[]) => useMemoryEventsMock(...args),
  useMemoryList: (...args: unknown[]) => useMemoryListMock(...args),
  useMemoryRevisions: (...args: unknown[]) => useMemoryRevisionsMock(...args),
}));

function listItem(overrides: Partial<MemoryApiListItemRead> = {}): MemoryApiListItemRead {
  return {
    content: "Risk memo content with a deterministic scope.",
    createdAt: "2026-05-20T10:00:00Z",
    kind: "insight",
    memoryId: "mem-risk-1",
    provenance: {
      agentKey: "analyst",
      agentVersion: 1,
      runId: 41,
      workflowKey: "risk-review",
    },
    revisionId: "rev-risk-1",
    scope: { scopeKey: "41", scopeType: "run" },
    subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
    summary: "Risk review memory",
    ...overrides,
  };
}

const detailFixture: MemoryApiEntryRead = {
  ...listItem(),
  attributes: { confidence: "high" },
  revision: {
    attributes: { confidence: "high" },
    content: "Risk memo content with a deterministic scope.",
    contentHash: "hash-risk-1",
    createdAt: "2026-05-20T10:00:00Z",
    revisionAction: "created",
    revisionId: "rev-risk-1",
    sourceAgentKey: "analyst",
    sourceRunId: 41,
    status: "resolved",
    subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
    summary: "Risk review memory",
    version: 1,
  },
  status: "resolved",
  updatedAt: "2026-05-20T10:05:00Z",
};

const revisionsFixture: MemoryApiRevisionListRead = {
  count: 1,
  items: [detailFixture.revision],
  limit: 20,
  offset: 0,
};

const eventsFixture: MemoryApiEventListRead = {
  count: 1,
  items: [
    {
      budget: { max: 3 },
      createdAt: "2026-05-20T10:06:00Z",
      eventId: 99,
      eventType: "memory.write",
      excerpt: "Risk memo content",
      filters: { kind: "insight" },
      memoryId: "mem-risk-1",
      resultSnapshot: { count: 1 },
      revisionId: "rev-risk-1",
      runId: 41,
      statusSnapshot: { status: "resolved" },
    },
  ],
  limit: 20,
  offset: 0,
};

function listResponse(items: MemoryApiListItemRead[]): MemoryApiListRead {
  return {
    count: items.length,
    items,
    limit: 20,
    offset: 0,
    scope: { scopeKey: "41", scopeType: "run" },
    visibility: "explicit-scope",
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
    useMemoryDetailMock.mockReset();
    useMemoryEventsMock.mockReset();
    useMemoryListMock.mockReset();
    useMemoryRevisionsMock.mockReset();
    useMemoryListMock.mockReturnValue(idleQuery(listResponse([])));
    useMemoryDetailMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? detailFixture : undefined),
    );
    useMemoryRevisionsMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? revisionsFixture : undefined),
    );
    useMemoryEventsMock.mockImplementation((memoryId: string | undefined) =>
      idleQuery(memoryId ? eventsFixture : undefined),
    );
  });

  it("keeps package access context and private scope gates explicit before queries", () => {
    renderPage();

    expect(screen.getByTestId("memory-list-page")).toBeVisible();
    expect(screen.getByTestId("workspace-page-shell-context")).toContainElement(
      screen.getByTestId("memory-contract-notice"),
    );
    expect(screen.getByRole("heading", { level: 1, name: "Memory" })).toBeVisible();
    const contractNotice = screen.getByTestId("memory-contract-notice");
    expect(contractNotice).not.toHaveTextContent("Explicit private scopes");
    expect(contractNotice).not.toHaveTextContent("Package key required");
    expect(contractNotice).not.toHaveTextContent("Private scope required");
    expect(contractNotice).not.toHaveTextContent("Namespace grants server-owned only");
    expect(contractNotice).toHaveTextContent("/api/memory");
    expect(contractNotice).toHaveTextContent("package access context");
    expect(contractNotice).toHaveTextContent("concrete private scope");
    expect(contractNotice).toHaveTextContent("visibility is fixed to explicit-scope");
    expect(contractNotice).toHaveTextContent("browser-authored JSON is not accepted");
    expect(contractNotice).toHaveTextContent("finance report history remains in Reports");
    const shellBody = screen.getByTestId("workspace-page-shell-body");
    expect(shellBody.children[0]).toBe(screen.getByTestId("memory-access-filter-controls"));
    expect(shellBody.children[1]).toBe(screen.getByTestId("memory-split-inspector"));
    expect(screen.getByTestId("memory-access-required")).toHaveTextContent(
      "Access context required",
    );
    expect(screen.getByTestId("memory-split-inspector")).toHaveAttribute(
      "data-inspector-state",
      "closed",
    );
    expect(useMemoryListMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ visibility: "explicit-scope" }),
      { enabled: false },
    );
  });

  it("requires the selected private scope field before enabling a scoped read", () => {
    renderPage("/memory?packageKey=pkg_alpha");

    expect(screen.getByTestId("memory-explicit-scope-required")).toHaveTextContent(
      "Private scope required",
    );
    expect(useMemoryListMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        accessContext: expect.objectContaining({ packageKey: "pkg_alpha" }),
        scope: { scopeKey: "missing", scopeType: "package" },
        visibility: "explicit-scope",
      }),
      { enabled: false },
    );
  });

  it("renders scoped rows and inspects detail, revisions, and events inline", async () => {
    useMemoryListMock.mockReturnValue(idleQuery(listResponse([listItem()])));

    renderPage("/memory?packageKey=pkg_alpha&runId=41");

    expect(useMemoryListMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        accessContext: expect.objectContaining({ packageKey: "pkg_alpha", runId: 41 }),
        scope: { scopeKey: "41", scopeType: "run" },
        visibility: "explicit-scope",
      }),
      { enabled: true },
    );
    expect(screen.getByTestId("memory-access-filter-controls")).toHaveTextContent(
      "Access context and filters",
    );
    expect(screen.getByTestId("memory-split-inspector")).toBeVisible();
    const row = screen.getByTestId("memory-row-mem-risk-1");
    expect(row).toHaveTextContent("Risk review memory");
    expect(row).toHaveTextContent("run scope 41");

    fireEvent.click(within(row).getByRole("button", { name: "Open memory" }));

    await waitFor(() =>
      expect(screen.getByTestId("memory-split-inspector")).toHaveAttribute(
        "data-inspector-state",
        "open",
      ),
    );
    expect(screen.getByTestId("memory-detail-panel")).toHaveTextContent(
      "Risk memo content with a deterministic scope.",
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Revisions" }), { button: 0 });
    expect(screen.getByTestId("memory-revisions-panel")).toHaveTextContent("v1");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Events" }), { button: 0 });
    expect(screen.getByTestId("memory-events-panel")).toHaveTextContent("event #99");
    expect(screen.queryByRole("link", { name: /memory/i })).not.toBeInTheDocument();
  });

  it("opens selected memory in a sheet instead of an inline split inspector on mobile", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 390,
    });
    useMemoryListMock.mockReturnValue(idleQuery(listResponse([listItem()])));

    renderPage("/memory?packageKey=pkg_alpha&runId=41");

    await waitFor(() =>
      expect(screen.getByTestId("memory-sheet-inspector")).toHaveAttribute(
        "data-inspector-mode",
        "sheet",
      ),
    );
    expect(screen.queryByTestId("memory-split-inspector")).not.toBeInTheDocument();
    expect(screen.queryByTestId("split-inspector-sheet")).not.toBeInTheDocument();

    const row = screen.getByTestId("memory-row-mem-risk-1");
    fireEvent.click(within(row).getByRole("button", { name: "Open memory" }));

    await waitFor(() =>
      expect(screen.getByTestId("memory-sheet-inspector")).toHaveAttribute(
        "data-inspector-state",
        "open",
      ),
    );
    expect(screen.getByTestId("split-inspector-sheet-body")).toHaveTextContent(
      "Risk memo content with a deterministic scope.",
    );
    expect(screen.queryByTestId("split-inspector-right-pane")).not.toBeInTheDocument();
  });

  it("keeps access-denied failures distinct from generic empty states", () => {
    useMemoryListMock.mockReturnValue({
      data: undefined,
      error: new ApiRequestError({
        code: "memory_namespace_access_denied",
        message: "Scope denied",
        status: 403,
      }),
      isError: true,
      isPending: false,
    });

    renderPage("/memory?packageKey=pkg_alpha&runId=41");

    expect(screen.getByTestId("memory-access-denied")).toHaveTextContent(
      "Memory access denied",
    );
    expect(screen.queryByTestId("memory-empty-state")).not.toBeInTheDocument();
  });
});
