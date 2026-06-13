import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  MemoryAdminEntryRead,
  MemoryAdminListItemRead,
  MemoryAdminListRead,
} from "@/lib/types/memory";

import { MemoryListPage } from "./list";

const { createAdminMemoryEntryMock, useAdminMemoryEntriesMock } = vi.hoisted(
  () => ({
    createAdminMemoryEntryMock: vi.fn(),
    useAdminMemoryEntriesMock: vi.fn(),
  }),
);

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-memory", () => ({
  useAdminMemoryEntries: (...args: unknown[]) =>
    useAdminMemoryEntriesMock(...args),
  useCreateAdminMemoryEntry: () => ({
    isPending: false,
    mutateAsync: createAdminMemoryEntryMock,
  }),
}));

function adminListItem(
  overrides: Partial<MemoryAdminListItemRead> = {},
): MemoryAdminListItemRead {
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
    status: "approved",
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
    status: "approved",
    summary: "Approved operator memory",
  },
  reflections: [],
  revision: {
    contentHash: "hash-risk-1",
    createdAt: "2026-05-20T10:00:00Z",
    revisionId: "rev-risk-1",
    version: 1,
  },
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

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location-probe">
      {location.pathname + location.search}
    </div>
  );
}

function renderPage(initialEntry = "/memory") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <MemoryListPage />
    </MemoryRouter>,
  );
}

describe("MemoryListPage", () => {
  beforeEach(() => {
    createAdminMemoryEntryMock.mockReset();
    useAdminMemoryEntriesMock.mockReset();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
    useAdminMemoryEntriesMock.mockReturnValue(idleQuery(listResponse([])));
    createAdminMemoryEntryMock.mockResolvedValue(detailFixture);
  });

  it("requests the admin list immediately with default params and no old gates", () => {
    renderPage();

    expect(screen.getByTestId("memory-list-page")).toBeVisible();
    expect(screen.getByTestId("workspace-page-shell-context")).toContainElement(
      screen.getByTestId("memory-admin-notice"),
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "Memory" }),
    ).toBeVisible();
    expect(screen.getByTestId("memory-admin-notice")).toHaveTextContent(
      "trusted local operator console",
    );
    expect(
      within(screen.getByTestId("workspace-page-shell-context")).getByRole(
        "button",
        { name: "Create memory" },
      ),
    ).toBeVisible();
    expect(
      within(screen.getByTestId("memory-admin-filter-controls")).queryByText(
        "Loaded",
      ),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId("memory-admin-filter-controls")).queryByText(
        /memory entries/,
      ),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId("memory-admin-filter-controls")).queryByText(
        "Mode",
      ),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId("memory-admin-filter-controls")).queryByText(
        "trusted operator",
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-write-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-runtime-impact-copy")).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId("memory-admin-filter-controls")).getByText(
        "Search canonical memory",
      ),
    ).toBeVisible();
    expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith(
      {},
      { enabled: true },
    );
    expect(
      screen.queryByTestId("memory-split-inspector"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("memory-sheet-inspector"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(["memory", "access", "required"].join("-")),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(
        ["memory", "explicit", "scope", "required"].join("-"),
      ),
    ).not.toBeInTheDocument();
  });

  it("distinguishes the default empty corpus from filtered-empty results", () => {
    const { unmount } = renderPage();

    const emptyStatePanel = screen.getByTestId("memory-empty-state-panel");

    expect(emptyStatePanel).toHaveTextContent("No canonical memory exists yet");
    expect(emptyStatePanel).not.toHaveTextContent("filters narrowed");
    expect(emptyStatePanel).not.toHaveTextContent("Create operator memory");
    expect(emptyStatePanel).not.toHaveTextContent("durable fact");
    expect(emptyStatePanel).not.toHaveTextContent("workflow lookup");

    unmount();
    renderPage("/memory?packageKey=pkg_alpha");

    expect(screen.getByTestId("memory-empty-state-panel")).toHaveTextContent(
      "No memory entries match these filters",
    );
    expect(screen.getByTestId("memory-empty-state-panel")).toHaveTextContent(
      "filters narrowed the operator corpus to zero",
    );
  });

  it("renders rows from different packages, scopes, and statuses with detail links", () => {
    useAdminMemoryEntriesMock.mockReturnValue(
      idleQuery(
        listResponse([
          adminListItem(),
          adminListItem({
            excerpt: "Beta workflow finding",
            memoryId: "mem-beta-2",
            scope: { scopeKey: "beta-agent", scopeType: "agent" },
            status: "pending",
            summary: "Beta package memory",
          }),
          adminListItem({
            excerpt: "Archived gamma workflow finding",
            memoryId: "mem-gamma-3",
            scope: { scopeKey: "gamma-workflow", scopeType: "workflow" },
            status: "archived",
            summary: "Gamma archived memory",
          }),
        ]),
      ),
    );

    renderPage();

    expect(
      screen.queryByText(
        "Rows from different packages and scopes can appear together by design.",
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("memory-row-mem-risk-1")).toHaveTextContent(
      "Package pkg_alpha",
    );
    expect(screen.getByTestId("memory-row-mem-beta-2")).toHaveTextContent(
      "Agent beta-agent",
    );
    expect(screen.getByTestId("memory-row-mem-beta-2")).toHaveTextContent(
      "pending",
    );
    expect(screen.getByTestId("memory-row-mem-gamma-3")).toHaveTextContent(
      "Workflow gamma-workflow",
    );
    expect(screen.getByTestId("memory-row-mem-gamma-3")).toHaveTextContent(
      "archived",
    );
    expect(
      within(screen.getByTestId("memory-row-mem-risk-1")).getByRole("link", {
        name: "Open detail",
      }),
    ).toHaveAttribute("href", "/memory/mem-risk-1");
    expect(
      within(screen.getByTestId("memory-row-mem-risk-1")).getByRole("link", {
        name: "Open memory mem-risk-1",
      }),
    ).toHaveAttribute("href", "/memory/mem-risk-1");
  });

  it("applies URL filters as optional admin params and reset restores the full corpus", async () => {
    renderPage(
      "/memory?packageKey=pkg_alpha&workflowKey=risk-review&agentKey=analyst&runId=41&scopeType=agent&kind=insight&status=approved&query=drawdown",
    );

    expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith(
      {
        agentKey: "analyst",
        kind: "insight",
        packageKey: "pkg_alpha",
        query: "drawdown",
        runId: 41,
        scopeType: "agent",
        status: "approved",
        workflowKey: "risk-review",
      },
      { enabled: true },
    );

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));

    await waitFor(() =>
      expect(useAdminMemoryEntriesMock).toHaveBeenLastCalledWith(
        {},
        { enabled: true },
      ),
    );
    expect(screen.getByTestId("location-probe")).toHaveTextContent("/memory");
  });

  it("narrows the corpus when filter fields change", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Package key"), {
      target: { value: "pkg_beta" },
    });
    fireEvent.change(screen.getByLabelText("Workflow key"), {
      target: { value: "audit" },
    });
    fireEvent.change(screen.getByLabelText("Agent key"), {
      target: { value: "reviewer" },
    });
    fireEvent.change(screen.getByLabelText("Run id"), {
      target: { value: "77" },
    });
    fireEvent.change(screen.getByLabelText("Kind"), {
      target: { value: "lesson" },
    });
    fireEvent.change(screen.getByLabelText("Search canonical memory"), {
      target: { value: "liquidity" },
    });

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

  it("creates admin memory and navigates to the routed detail page", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Create memory" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText("Create operator memory")).not.toBeInTheDocument();
    expect(within(dialog).queryByTestId("memory-runtime-impact-copy")).not.toBeInTheDocument();
    expect(
      within(dialog).queryByText("Approved memory in a matching scope", {
        exact: false,
      }),
    ).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Summary"), {
      target: { value: "Operator note" },
    });
    fireEvent.change(within(dialog).getByLabelText("Content"), {
      target: { value: "Operator-authored canonical memory." },
    });
    fireEvent.change(within(dialog).getByLabelText("Package key"), {
      target: { value: "pkg_alpha" },
    });
    fireEvent.change(within(dialog).getByLabelText("Run id"), {
      target: { value: "41" },
    });
    fireEvent.change(within(dialog).getByLabelText("Scope key"), {
      target: { value: "pkg_alpha" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create memory" }),
    );

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
          status: "approved",
          summary: "Operator note",
        }),
      ),
    );
    expect(
      createAdminMemoryEntryMock.mock.calls[0]?.[0].provenance,
    ).not.toHaveProperty("workflowKey");
    await waitFor(() =>
      expect(screen.getByTestId("location-probe")).toHaveTextContent(
        "/memory/mem-risk-1",
      ),
    );
  });

  it("surfaces create mutation failures without navigating", async () => {
    createAdminMemoryEntryMock.mockRejectedValueOnce(new Error("create failed"));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Create memory" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Summary"), {
      target: { value: "Operator note" },
    });
    fireEvent.change(within(dialog).getByLabelText("Content"), {
      target: { value: "Operator-authored canonical memory." },
    });
    fireEvent.change(within(dialog).getByLabelText("Package key"), {
      target: { value: "pkg_alpha" },
    });
    fireEvent.change(within(dialog).getByLabelText("Run id"), {
      target: { value: "41" },
    });
    fireEvent.change(within(dialog).getByLabelText("Scope key"), {
      target: { value: "pkg_alpha" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create memory" }),
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("create failed"));
    expect(screen.getByTestId("location-probe")).toHaveTextContent("/memory");
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("does not render removed inline inspector behavior or removal controls", () => {
    renderPage();

    const page = screen.getByTestId("memory-list-page");
    expect(page).not.toHaveTextContent(["package", "context"].join(" "));
    expect(page).not.toHaveTextContent(["private", "scope"].join(" "));
    expect(page).not.toHaveTextContent(["explicit", "scope"].join("-"));
    expect(page).not.toHaveTextContent(
      ["Access", "context", "required"].join(" "),
    );
    expect(page).not.toHaveTextContent(
      ["Private", "scope", "required"].join(" "),
    );
    expect(
      screen.queryByTestId("memory-split-inspector"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("memory-sheet-inspector"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /bulk/i }),
    ).not.toBeInTheDocument();
  });
});
