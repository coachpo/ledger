import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  WorkflowMemoryAuditEventListRead,
  WorkflowMemoryProposalListRead,
  WorkflowMemoryProposalRead,
  WorkflowMemoryQuarantineListRead,
} from "@/lib/types/memory";

import { MemoryListPage } from "./list";

const {
  approveProposalMock,
  rejectProposalMock,
  useWorkflowMemoryAuditEventsMock,
  useWorkflowMemoryProposalsMock,
  useWorkflowMemoryQuarantineMock,
} = vi.hoisted(() => ({
  approveProposalMock: vi.fn(),
  rejectProposalMock: vi.fn(),
  useWorkflowMemoryAuditEventsMock: vi.fn(),
  useWorkflowMemoryProposalsMock: vi.fn(),
  useWorkflowMemoryQuarantineMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-memory", () => ({
  useApproveWorkflowMemoryProposal: () => ({
    isPending: false,
    mutateAsync: approveProposalMock,
  }),
  useRejectWorkflowMemoryProposal: () => ({
    isPending: false,
    mutateAsync: rejectProposalMock,
  }),
  useWorkflowMemoryAuditEvents: (...args: unknown[]) =>
    useWorkflowMemoryAuditEventsMock(...args),
  useWorkflowMemoryProposals: (...args: unknown[]) =>
    useWorkflowMemoryProposalsMock(...args),
  useWorkflowMemoryQuarantine: (...args: unknown[]) =>
    useWorkflowMemoryQuarantineMock(...args),
}));

function idleQuery(data?: unknown) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function proposal(
  overrides: Partial<WorkflowMemoryProposalRead> = {},
): WorkflowMemoryProposalRead {
  return {
    agentKey: "analyst",
    content: { summary: "Memory candidate", ticker: "AAPL" },
    createdAt: "2026-06-16T12:00:00Z",
    detectors: { pii: false },
    invocationId: "invocation_1",
    kind: "insight",
    namespace: "research",
    packageKey: "research_package",
    proposalId: "proposal_1",
    reason: "Policy requires review",
    runId: 42,
    sourceOutputPath: "nodes.summarize.outputs.memory",
    status: "review_pending",
    stepId: "summarize",
    updatedAt: "2026-06-16T12:05:00Z",
    workflowKey: "daily_research",
    ...overrides,
  };
}

function proposalList(
  items: WorkflowMemoryProposalRead[] = [],
): WorkflowMemoryProposalListRead {
  return {
    items,
    limit: 50,
    offset: 0,
    status: "review_pending",
    total: items.length,
  };
}

function auditList(): WorkflowMemoryAuditEventListRead {
  return {
    items: [
      {
        agentKey: "analyst",
        createdAt: "2026-06-16T12:06:00Z",
        event: { decision: "commit" },
        eventId: 7,
        eventType: "proposal_approved",
        invocationId: "invocation_1",
        packageKey: "research_package",
        runId: 42,
        stepId: "summarize",
        targetId: "proposal_1",
        targetType: "proposal",
        workflowKey: "daily_research",
      },
    ],
    limit: 50,
    offset: 0,
    total: 1,
  };
}

function quarantineList(): WorkflowMemoryQuarantineListRead {
  return {
    items: [
      {
        agentKey: "analyst",
        createdAt: "2026-06-16T12:07:00Z",
        detectors: { promptInjection: true },
        evidence: { text: "suspicious instruction" },
        invocationId: "invocation_1",
        kind: "insight",
        memoryId: null,
        namespace: "research",
        packageKey: "research_package",
        proposalId: "proposal_2",
        quarantineId: 11,
        reason: "Unsafe content",
        reasonCode: "policy_quarantine",
        resolvedAt: null,
        runId: 42,
        stepId: "summarize",
        workflowKey: "daily_research",
      },
    ],
    limit: 50,
    offset: 0,
    total: 1,
    unresolvedOnly: true,
  };
}

async function chooseSelectOption(label: string, optionName: string) {
  const selector = screen.getByRole("combobox", { name: label });
  selector.focus();
  fireEvent.keyDown(selector, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/memory"]}>
      <MemoryListPage />
    </MemoryRouter>,
  );
}

describe("MemoryListPage", () => {
  beforeEach(() => {
    approveProposalMock.mockReset();
    rejectProposalMock.mockReset();
    useWorkflowMemoryAuditEventsMock.mockReset();
    useWorkflowMemoryProposalsMock.mockReset();
    useWorkflowMemoryQuarantineMock.mockReset();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
    approveProposalMock.mockResolvedValue({});
    rejectProposalMock.mockResolvedValue({});
    useWorkflowMemoryProposalsMock.mockReturnValue(idleQuery(proposalList()));
    useWorkflowMemoryAuditEventsMock.mockReturnValue(idleQuery(auditList()));
    useWorkflowMemoryQuarantineMock.mockReturnValue(idleQuery(quarantineList()));
  });

  it("renders the review-only workflow memory surface", () => {
    const { container } = renderPage();
    const page = screen.getByTestId("memory-list-page");
    const inventoryRegions = Array.from(
      container.querySelectorAll("[data-inventory-shell-region]"),
    ).map((region) => region.getAttribute("data-inventory-shell-region"));

    expect(page).toBeVisible();
    expect(inventoryRegions).toEqual(["context", "toolbar", "content"]);
    expect(
      page.querySelector('[data-inventory-shell-region="context"]'),
    ).toBeVisible();
    expect(
      page.querySelector('[data-inventory-shell-region="toolbar"]'),
    ).toBeVisible();
    expect(
      page.querySelector('[data-inventory-shell-region="content"]'),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: "Workflow Memory Review" }),
    ).toBeVisible();
    expect(
      screen.getByRole("combobox", { name: "Proposal status" }),
    ).toBeVisible();
    expect(screen.getByRole("tab", { name: "Proposals" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Audit events" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Quarantine" })).toBeVisible();
    expect(screen.getByText("No proposals to review")).toBeVisible();
    expect(screen.queryByText("Proposal queue")).not.toBeInTheDocument();
    expect(useWorkflowMemoryProposalsMock).toHaveBeenLastCalledWith(
      { status: "review_pending" },
    );
    expect(
      screen.queryByRole("textbox", { name: /search/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: /select/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete selected/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Create memory")).not.toBeInTheDocument();
    expect(screen.queryByText("New memory")).not.toBeInTheDocument();
    expect(screen.queryByText("Memory Admin")).not.toBeInTheDocument();
    expect(screen.queryByText("Workflow visibility")).not.toBeInTheDocument();
  });

  it("filters proposals by review status", async () => {
    renderPage();

    await chooseSelectOption("Proposal status", "All");

    await waitFor(() =>
      expect(useWorkflowMemoryProposalsMock).toHaveBeenLastCalledWith({
        status: "all",
      }),
    );
    expect(screen.getByTestId("memory-review-active-filters")).toHaveTextContent(
      /Status\s*All/,
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() =>
      expect(useWorkflowMemoryProposalsMock).toHaveBeenLastCalledWith({
        status: "review_pending",
      }),
    );
  });

  it("renders proposal cards and records approve or reject reasons", async () => {
    useWorkflowMemoryProposalsMock.mockReturnValue(
      idleQuery(proposalList([proposal()])),
    );

    renderPage();

    const card = screen.getByTestId("memory-proposal-proposal_1");
    expect(card).toHaveTextContent("insight in research");
    expect(card).toHaveTextContent("Review Pending");
    expect(card).toHaveTextContent("Policy requires review");
    expect(card).toHaveTextContent("Memory candidate");
    fireEvent.change(within(card).getByLabelText("Review reason"), {
      target: { value: "Looks durable" },
    });
    fireEvent.click(within(card).getByRole("button", { name: "Approve proposal" }));

    await waitFor(() =>
      expect(approveProposalMock).toHaveBeenCalledWith({
        payload: { reason: "Looks durable" },
        proposalId: "proposal_1",
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Memory proposal approved");

    fireEvent.change(within(card).getByLabelText("Review reason"), {
      target: { value: "Too broad" },
    });
    fireEvent.click(within(card).getByRole("button", { name: "Reject proposal" }));

    await waitFor(() =>
      expect(rejectProposalMock).toHaveBeenCalledWith({
        payload: { reason: "Too broad" },
        proposalId: "proposal_1",
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Memory proposal rejected");
  });

  it("hides review actions for already-decided proposals", () => {
    useWorkflowMemoryProposalsMock.mockReturnValue(
      idleQuery(proposalList([proposal({ status: "committed" })])),
    );

    renderPage();

    const card = screen.getByTestId("memory-proposal-proposal_1");
    expect(card).toHaveTextContent("Committed");
    expect(
      within(card).queryByRole("button", { name: "Approve proposal" }),
    ).not.toBeInTheDocument();
    expect(
      within(card).queryByRole("button", { name: "Reject proposal" }),
    ).not.toBeInTheDocument();
  });

  it("renders audit and quarantine review tabs", async () => {
    renderPage();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Audit events" }), {
      button: 0,
    });
    expect(await screen.findByTestId("memory-audit-event-7")).toHaveTextContent(
      "Proposal Approved",
    );
    expect(screen.getByTestId("memory-audit-event-7")).toHaveTextContent(
      "proposal proposal_1",
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Quarantine" }), {
      button: 0,
    });
    expect(await screen.findByTestId("memory-quarantine-11")).toHaveTextContent(
      "policy_quarantine",
    );
    expect(screen.getByTestId("memory-quarantine-11")).toHaveTextContent(
      "Unresolved",
    );
    expect(screen.getByTestId("memory-quarantine-11")).toHaveTextContent(
      "Unsafe content",
    );
  });

  it("surfaces review mutation failures", async () => {
    approveProposalMock.mockRejectedValueOnce(new Error("review failed"));
    useWorkflowMemoryProposalsMock.mockReturnValue(
      idleQuery(proposalList([proposal()])),
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Approve proposal" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("review failed"),
    );
  });
});
