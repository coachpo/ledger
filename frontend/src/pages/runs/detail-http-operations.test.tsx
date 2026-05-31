import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RunOperationInvocationRead, RunRead, RunStepRead } from "@/lib/types/run";

import { RunsDetailPage } from "./detail";

const setSearchParamsMock = vi.fn();
const useRunMock = vi.fn();
let searchParamsMock = new URLSearchParams();

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useLocation: () => ({ hash: "", pathname: "/runs/42", search: searchParamsMock.toString() }),
  useNavigate: () => vi.fn(),
  useParams: () => ({ runId: "42" }),
  useSearchParams: () => [searchParamsMock, setSearchParamsMock],
}));

vi.mock("@/hooks/use-runs", () => ({
  useCreateRunFork: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCreateRunRerun: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useRun: () => useRunMock(),
  useRunForkDraft: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useRunRerunDraft: () => ({ data: undefined, error: null, isError: false, isPending: false }),
}));

const NOW = "2026-05-15T08:30:00Z";

function buildOperation(overrides: Partial<RunOperationInvocationRead> = {}): RunOperationInvocationRead {
  return {
    createdAt: NOW,
    durationMs: 42,
    errorCode: null,
    errorDetails: [],
    errorMessage: null,
    finishedAt: "2026-05-15T08:31:00Z",
    graphMetadata: { nodeId: "notify_slack", nodeKind: "http" },
    id: 2001,
    method: "POST",
    operationKey: "notify_slack",
    operationKind: "http",
    optional: false,
    output: { ok: true, message: "queued" },
    outputOrigin: "executed",
    outputSchemaRef: { scope: "packageLocal", localId: 31, version: 1 },
    outputSchemaVersion: 1,
    persistedAt: "2026-05-15T08:31:00Z",
    position: 0,
    requestMetadata: {
      body: { token: { from: "secret", key: "body_token", redacted: true } },
      headers: { Authorization: { from: "secret", key: "slack_webhook_token", redacted: true } },
      url: { redacted: true },
    },
    responseMetadata: { headers: { "content-type": "application/json" }, statusCode: 200 },
    runId: 42,
    runStepId: 101,
    slot: "webhook_result",
    sourceOperationInvocationId: null,
    sourceRunId: null,
    sourceRunStepId: null,
    sourceStepIndex: null,
    startedAt: NOW,
    status: "succeeded",
    stepIndex: 1,
    timeoutSeconds: 10,
    traceSpanId: "span-operation",
    updatedAt: "2026-05-15T08:31:00Z",
    ...overrides,
  };
}

function buildStep(overrides: Partial<RunStepRead> = {}): RunStepRead {
  return {
    createdAt: NOW,
    error: null,
    finishedAt: "2026-05-15T08:31:00Z",
    graphMetadata: { nodeId: "notify_slack", nodeKind: "http" },
    id: 101,
    index: 1,
    invocations: [],
    operationInvocations: [buildOperation()],
    origin: "planned",
    persistedAt: "2026-05-15T08:31:00Z",
    runId: 42,
    sourceRunId: null,
    sourceRunStepId: null,
    sourceStepIndex: null,
    startedAt: NOW,
    status: "succeeded",
    updatedAt: "2026-05-15T08:31:00Z",
    ...overrides,
  };
}

function applyLatestSearchParamsUpdate(currentSearch: string) {
  const lastCall =
    setSearchParamsMock.mock.calls[setSearchParamsMock.mock.calls.length - 1];
  const updater = lastCall?.[0];

  if (typeof updater !== "function") {
    throw new Error(
      "Expected the latest search params update to use an updater function.",
    );
  }

  searchParamsMock = updater(new URLSearchParams(currentSearch));
}

function buildRun(overrides: Partial<RunRead> = {}): RunRead {
  return {
    createdAt: NOW,
    error: null,
    executedTokens: 0,
    finalOutput: { webhook_result: { ok: true } },
    finishedAt: "2026-05-15T08:31:00Z",
    id: 42,
    inheritedTokens: 0,
    input: { ticker: "NVDA" },
    lineageRootRunId: null,
    memoryArtifacts: [],
    memoryEvents: [],
    extensionDependencies: [],
    packageProvenance: null,
    progress: {
      unit: "invocation",
      terminalCount: 1,
      totalCount: 1,
      percent: 100,
    },
    queue: null,
    queuedAt: NOW,
    replayStepIndex: null,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: NOW,
    status: "succeeded",
    steps: [buildStep()],
    targetId: 7,
    targetKey: "http_callbacks",
    targetKind: "workflowPackage",
    totalTokens: 0,
    traceId: "trace-http",
    updatedAt: "2026-05-15T08:31:00Z",
    ...overrides,
  };
}

describe("RunsDetailPage HTTP operation invocations", () => {
  beforeEach(() => {
    searchParamsMock = new URLSearchParams();
    setSearchParamsMock.mockReset();
    useRunMock.mockReset();
  });

  it("preserves operation outputs in step summary and keeps direct operation panes accessible", () => {
    const failedOperation = buildOperation({
      durationMs: 9,
      errorCode: "http_status_error",
      errorDetails: [{ statusCode: 500 }],
      errorMessage: "Webhook returned 500.",
      id: 2002,
      output: null,
      outputOrigin: null,
      position: 1,
      responseMetadata: { statusCode: 500 },
      slot: "webhook_retry",
      status: "failed",
      traceSpanId: "span-operation-failed",
    });
    useRunMock.mockReturnValue({
      data: buildRun({ steps: [buildStep({ operationInvocations: [buildOperation(), failedOperation], status: "failed" })] }),
      isError: false,
      isPending: false,
    });

    searchParamsMock = new URLSearchParams("mode=execution");
    const outlineRender = render(<RunsDetailPage />);

    expect(screen.getByTestId("runs-detail-page")).toHaveClass("h-full", "overflow-hidden");
    expect(screen.queryByTestId("runs-inspection-split-layout"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("split-inspector-right-pane"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-page-shell-left-rail"))
      .not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-tab-console")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-mode-workspace")).toContainElement(
      screen.getByTestId("runs-execution-outline"),
    );
    expect(screen.getByTestId("runs-detail-section-execution-steps")).toHaveAttribute(
      "data-slot",
      "collapsible",
    );
    outlineRender.unmount();
    searchParamsMock = new URLSearchParams("mode=metadata");
    const auditRender = render(<RunsDetailPage />);
    expect(
      screen.queryByTestId("runs-detail-section-metadata"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Metadata" }),
    ).not.toBeInTheDocument();
    [
      "runs-audit-table",
      "runs-audit-row-trace-root",
      "runs-audit-row-payload-output",
      "runs-audit-row-payload-input",
      "runs-audit-row-trace-operation-2001",
      "runs-audit-row-trace-operation-2002",
      "runs-audit-row-memory-groups",
    ].forEach((testId) => {
      expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(
      /webhook_result/i,
    );
    expect(screen.getByTestId("runs-detail-input")).toHaveTextContent(/NVDA/i);
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(
      /webhook_result\/span-operation/i,
    );
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(
      /webhook_retry\/span-operation-failed/i,
    );

    auditRender.unmount();
    searchParamsMock = new URLSearchParams("mode=summary");
    const overviewRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-summary-execution-row")).toHaveTextContent(
      /2 of 2 invocation\(s\) terminal/i,
    );

    overviewRender.unmount();
    searchParamsMock = new URLSearchParams("mode=execution");
    const stepsRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/0 agent invocation/i);
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/2 operation invocation/i);

    expect(screen.queryByTestId("runs-step-1-operation-webhook_result")).not.toBeInTheDocument();
    expect(screen.queryByTestId("runs-step-1-operation-webhook_retry")).not.toBeInTheDocument();
    expect(screen.getByTestId("runs-step-1-trace-summary")).toHaveTextContent(/operation webhook_result\/span-operation/i);
    const operationRow = screen.getByTestId("runs-operation-2001-outline-entry");
    expect(operationRow).toHaveAttribute("role", "button");
    expect(operationRow.querySelector("button")).toBeNull();
    fireEvent.click(operationRow);
    applyLatestSearchParamsUpdate("mode=execution");
    stepsRender.unmount();

    const selectedOperationRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-operation-2001-inline-evidence"))
      .toHaveTextContent(/queued/i);
    fireEvent.keyDown(screen.getByTestId("runs-operation-2001-outline-entry"), {
      key: " ",
    });
    applyLatestSearchParamsUpdate("mode=execution&inspect=operation%3A2001");
    expect(searchParamsMock.get("mode")).toBe("execution");
    expect(searchParamsMock.has("inspect")).toBe(false);
    expect(searchParamsMock.has("pane")).toBe(false);
    selectedOperationRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=step:1");
    const stepSummaryRender = render(<RunsDetailPage />);
    expect(within(screen.getByTestId("runs-step-1-inline-evidence")).queryByRole("button", { name: /trace/i })).not.toBeInTheDocument();
    const aggregatedOutput = screen.getByTestId("runs-step-1-aggregated-output");
    expect(aggregatedOutput).toHaveTextContent(/webhook_result/i);
    expect(aggregatedOutput).toHaveTextContent(/webhook_retry/i);
    expect(aggregatedOutput).toHaveTextContent(/queued/i);
    expect(aggregatedOutput).toHaveTextContent(/failed/i);
    expect(aggregatedOutput).not.toHaveTextContent("slack-secret-value");
    expect(aggregatedOutput).not.toHaveTextContent("body-secret-value");
    stepSummaryRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=operation:2001&pane=request");
    const requestRender = render(<RunsDetailPage />);
    const requestMetadata = screen.getByTestId("runs-operation-2001-request-metadata");
    expect(requestMetadata).toHaveTextContent(/redacted/i);
    expect(screen.getByTestId("runs-operation-2001-request-metadata-tab-scroll")).toHaveClass("max-w-full", "overflow-x-auto");
    fireEvent.mouseDown(within(requestMetadata).getByRole("tab", { name: "Raw" }), { button: 0 });
    expect(screen.getByTestId("runs-operation-2001-request-metadata-raw")).toHaveAttribute("data-wide-payload", "scroll");
    requestRender.unmount();

    searchParamsMock = new URLSearchParams("inspect=operation:2001&pane=response");
    const responseRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-operation-2001-response-metadata")).toHaveTextContent(/statusCode/i);
    responseRender.unmount();

    searchParamsMock = new URLSearchParams("inspect=operation:2001&pane=output");
    const outputRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-operation-2001-output-preview")).toHaveTextContent(/queued/i);
    outputRender.unmount();

    searchParamsMock = new URLSearchParams("inspect=operation:2002&pane=error");
    const failedRender = render(<RunsDetailPage />);
    const activeEvidence = within(
      screen.getByTestId("runs-operation-2002-inline-evidence"),
    ).getByTestId("runs-active-evidence-viewer");
    expect(within(activeEvidence).getByText("http_status_error")).toBeVisible();
    expect(within(activeEvidence).getByText("Webhook returned 500.")).toBeVisible();
    expect(within(activeEvidence).getByText(/statusCode/)).toBeVisible();
    failedRender.unmount();

    searchParamsMock = new URLSearchParams("pane=request");
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-detail-final-output")).toHaveTextContent(/webhook_result/i);
    expect(screen.queryByTestId("runs-evidence-pane-nav")).not.toBeInTheDocument();
  });
});
