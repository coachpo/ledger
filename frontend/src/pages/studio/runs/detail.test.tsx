import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StudioRunDetailPage } from "./detail";

vi.mock("react-router", () => ({
  useParams: () => ({ runId: "42" }),
}));

vi.mock("@/hooks/use-studio", () => ({
  useStudioRun: () => ({
    data: {
      runId: 42,
      status: "SUCCEEDED",
      callerType: "studio",
      callerId: null,
      callerScopeKey: "studio-session-a",
      callerIdentityKey: "studio-user-1",
      executionKind: "workflow",
      workflowSpecKey: "alpha_workflow",
      workflowSpecVersion: 2,
      agentSpecKey: null,
      agentSpecVersion: null,
      attemptNumber: 1,
      expiresAt: null,
      createdAt: "2026-04-14T10:00:00Z",
      updatedAt: "2026-04-14T10:05:00Z",
      pendingApprovalIds: [9, 10],
      finalOutput: { summary: "All clear" },
      traceSummary: { eventCount: 12, toolCallCount: 5, warningCount: 1, lastEventAt: null },
      approvalSummary: { totalCount: 2, pendingCount: 2, approvedCount: 0, deniedCount: 0, expiredCount: 0 },
      terminalError: null,
    },
    isError: false,
    isPending: false,
  }),
  useStudioRunArtifact: () => ({
    data: {
      runId: 42,
      finalOutput: { summary: "All clear" },
      reportMarkdown: "# Report",
      normalizedTradeDecisions: null,
      entryPromptHash: "a",
      fullUserPromptHash: "b",
      authoredEntryPromptBody: "Authored prompt",
      compiledEntryPromptBody: "Compiled prompt",
      executionContextBody: "Execution context body",
      promptReportSlug: "prompt-42",
      rawMentionHandles: [],
      resolvedMentions: [],
      mentionedTargetOutputs: [],
      resolvedPersonaProfileRefs: [{ personaProfileKey: "imported.character.analyst" }],
      resolvedWorkflowAgentRefs: [],
      resolvedCapabilities: [{ capabilityKey: "connector.market_data" }],
      resolvedBuiltinVersions: [],
      resolvedRoleVersions: [],
      resolvedCharacterVersions: [],
      resolvedBundleVersions: [],
      resolvedToolVersions: [],
      resolvedConnectorVersions: [],
      traceSummary: { eventCount: 12, toolCallCount: 5, warningCount: 1, lastEventAt: null },
      approvalSummary: { totalCount: 2, pendingCount: 2, approvedCount: 0, deniedCount: 0, expiredCount: 0 },
      createdAt: "2026-04-14T10:00:00Z",
      terminalError: null,
    },
  }),
  useStudioRunTrace: () => ({
    data: {
      items: [
        {
          runId: 42,
          eventIndex: 7,
          eventType: "RUN_COMPLETED",
          stepKey: null,
          capabilityKey: null,
          callerType: "studio",
          callerId: null,
          createdAt: "2026-04-14T10:05:00Z",
          approvalId: null,
          payload: {},
        },
      ],
      nextCursor: null,
    },
    isPending: false,
  }),
}));

describe("StudioRunDetailPage", () => {
  it("renders the run summary, artifact snapshot, and trace widgets", () => {
    render(<StudioRunDetailPage />);

    expect(screen.getByTestId("studio-run-detail")).toBeInTheDocument();
    expect(screen.getByTestId("studio-run-summary-card")).toBeInTheDocument();
    expect(screen.getByTestId("studio-run-artifact-card")).toBeInTheDocument();
    expect(screen.getByTestId("studio-run-trace-card")).toBeInTheDocument();
    expect(screen.getByTestId("studio-run-final-output")).toHaveTextContent(/all clear/i);
    expect(screen.getByTestId("studio-run-trace-event-7")).toBeInTheDocument();
  });
});
