import { describe, expect, it } from "vitest";

import { groupReports } from "./report-grouping";
import type { ReportCreatedByMetadata, ReportRead } from "./types/report";

const backendCreatedByReadContract = {
  type: "agent",
  runId: 42,
  agentKey: "research_agent",
  agentVersion: 3,
  workflowKey: "daily_review",
  workflowVersion: 2,
  traceId: "trace-report-created-by",
} satisfies ReportCreatedByMetadata;

function buildReport(overrides: Partial<ReportRead> = {}): ReportRead {
  return {
    id: 1,
    name: "Agent Memory Snapshot",
    slug: "agent_memory_snapshot",
    source: "agent",
    content: "# Snapshot",
    metadata: {
      author: "SignalDeck Agent",
      description: null,
      tags: [],
      createdBy: backendCreatedByReadContract,
    },
    createdAt: "2026-05-04T10:00:00Z",
    updatedAt: "2026-05-04T10:00:00Z",
    ...overrides,
  };
}

describe("report grouping", () => {
  it("groups reports with agent source under Agent", () => {
    const groups = groupReports(
      [
        buildReport(),
        buildReport({
          id: 2,
          name: "Uploaded Summary",
          slug: "uploaded_summary",
          source: "uploaded",
        }),
      ],
      "source",
    );

    expect(groups.get("Agent")?.map((report) => report.slug)).toEqual([
      "agent_memory_snapshot",
    ]);
    expect(groups.get("Uploaded")?.map((report) => report.slug)).toEqual([
      "uploaded_summary",
    ]);
  });
});
