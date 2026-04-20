import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RunsListPage } from "./list";

const navigateMock = vi.fn();
const refetchMock = vi.fn();
const useRunsMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-runs", () => ({
  useRuns: (...args: unknown[]) => useRunsMock(...args),
}));

describe("RunsListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    refetchMock.mockReset();
    useRunsMock.mockReturnValue({
      data: {
        items: [
          {
            finishedAt: null,
            id: 15,
            startedAt: "2026-04-20T10:00:00Z",
            status: "running",
            totalCostUsd: "0.02000000",
            totalTokens: 21,
            traceId: "trace-15",
            workflowId: 41,
            workflowKey: "market_review",
            workflowVersion: 2,
          },
        ],
      },
      error: null,
      isError: false,
      isPending: false,
      refetch: refetchMock,
    });
  });

  it("renders run rows, refreshes, and routes to detail", () => {
    render(<RunsListPage />);

    expect(screen.getByTestId("runs-row-15")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
    expect(refetchMock).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /open run/i }));
    expect(navigateMock).toHaveBeenCalledWith("/runs/15");
  });
});
