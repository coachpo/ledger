import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowsListPage } from "./list";

const navigateMock = vi.fn();
const useWorkflowsMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-workflows", () => ({
  useWorkflows: () => useWorkflowsMock(),
}));

describe("WorkflowsListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    useWorkflowsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 41,
            aggregateBudgetUsd: "1.25000000",
            description: "Runs research then produces a decision.",
            inputSchema: {},
            key: "market_review",
            name: "Market Review",
            outputSpec: { kind: "slot", slot: "decision", stepIndex: 2 },
            status: "published",
            steps: [{ agents: [{ slot: "analysis" }] }, { agents: [{ slot: "decision" }] }],
            version: 2,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders workflow rows and routes to create, edit, and review-run paths", () => {
    render(<WorkflowsListPage />);

    expect(screen.getByTestId("workflows-row-market_review")).toBeVisible();

    fireEvent.click(screen.getByTestId("workflows-new"));
    expect(navigateMock).toHaveBeenCalledWith("/workflows/new");

    fireEvent.click(screen.getByTestId("workflows-open-market_review"));
    expect(navigateMock).toHaveBeenCalledWith("/workflows/41/edit");

    fireEvent.click(screen.getByTestId("workflows-run-market_review"));
    expect(navigateMock).toHaveBeenCalledWith("/workflows/41/edit#review");
  });
});
