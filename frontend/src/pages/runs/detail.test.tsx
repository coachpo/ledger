import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RunsDetailPage } from "./detail";

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useParams: () => ({ runId: "42" }),
}));

vi.mock("@/hooks/use-runs", () => ({
  useRun: () => ({
    data: {
      createdAt: "2026-04-20T10:00:00Z",
      error: null,
      finalOutput: { summary: "All clear" },
      finishedAt: "2026-04-20T10:00:04Z",
      id: 42,
      input: { ticker: "AAPL" },
      perStepOutputs: {
        "1": [
          {
            agentId: 1,
            agentKey: "research_agent",
            agentVersion: 3,
            costUsd: "0.02000000",
            durationMs: 8,
            error: null,
            output: { summary: "analysis" },
            outputSchemaId: 11,
            outputSchemaVersion: 1,
            resolvedInput: { ticker: "AAPL" },
            slot: "analysis",
            status: "succeeded",
            tokens: 21,
            traceSpanId: "span-1",
          },
        ],
        "2": [
          {
            agentId: 2,
            agentKey: "consumer_agent",
            agentVersion: 2,
            costUsd: "0.03000000",
            durationMs: 12,
            error: null,
            output: { summary: "decision" },
            outputSchemaId: 11,
            outputSchemaVersion: 1,
            resolvedInput: { analysis: { summary: "analysis" } },
            slot: "decision",
            status: "succeeded",
            tokens: 30,
            traceSpanId: "span-2",
          },
        ],
      },
      startedAt: "2026-04-20T10:00:00Z",
      status: "succeeded",
      totalCostUsd: "0.05000000",
      totalTokens: 51,
      traceId: "trace-42",
      updatedAt: "2026-04-20T10:00:04Z",
      workflowId: 7,
      workflowKey: "market_review",
      workflowVersion: 2,
    },
    isError: false,
    isPending: false,
  }),
}));

describe("RunsDetailPage", () => {
  it("renders progress, per-agent detail, and trace linkage", () => {
    render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-page")).toBeInTheDocument();
    expect(screen.getByTestId("runs-detail-status")).toHaveTextContent(/succeeded/i);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(/all clear/i);
    expect(screen.getByTestId("runs-trace-linkage")).toHaveTextContent(/trace-42/i);
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(
      /trace-42 -> step 1\/analysis\/span-1 -> step 2\/decision\/span-2/i,
    );
    expect(screen.getByText(/path trace-42 \/ step 1 \/ analysis/i)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /step 1/i }));
    expect(screen.getByTestId("runs-step-1-slot-analysis")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /step 2/i }));
    expect(screen.getByTestId("runs-step-2-slot-decision")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /trace link · span-2/i })).toBeVisible();
  });
});
