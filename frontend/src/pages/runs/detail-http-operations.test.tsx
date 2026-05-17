import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RunOperationInvocationRead, RunRead, RunStepRead } from "@/lib/types/run";

import { RunsDetailPage } from "./detail";

const useRunMock = vi.fn();
let searchParamsMock = new URLSearchParams();

vi.mock("react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useLocation: () => ({ hash: "", pathname: "/runs/42", search: searchParamsMock.toString() }),
  useNavigate: () => vi.fn(),
  useParams: () => ({ runId: "42" }),
  useSearchParams: () => [searchParamsMock, vi.fn()],
}));

vi.mock("@/hooks/use-runs", () => ({
  useCreateRunRerun: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCreateRunStepReplay: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useRun: () => useRunMock(),
  useRunRerunDraft: () => ({ data: undefined, error: null, isError: false, isPending: false }),
  useRunStepReplayDraft: () => ({ data: undefined, error: null, isError: false, isPending: false }),
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
    outputSchemaId: 31,
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
    extensionDependencies: [],
    packageProvenance: null,
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
    targetVersion: 1,
    totalTokens: 0,
    traceId: "trace-http",
    updatedAt: "2026-05-15T08:31:00Z",
    ...overrides,
  };
}

describe("RunsDetailPage HTTP operation invocations", () => {
  beforeEach(() => {
    searchParamsMock = new URLSearchParams();
    useRunMock.mockReset();
  });

  it("renders operation invocations separately with redacted metadata and failure state", () => {
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

    const outlineRender = render(<RunsDetailPage />);

    expect(screen.getByText(/2 of 2 invocation\(s\) terminal/i)).toBeVisible();
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/0 agent invocation/i);
    expect(screen.getByTestId("runs-step-1")).toHaveTextContent(/2 operation invocation/i);

    const operationCard = screen.getByTestId("runs-step-1-operation-webhook_result");
    expect(operationCard).toHaveTextContent(/webhook_result/i);
    expect(operationCard).toHaveTextContent(/POST/i);
    expect(operationCard).toHaveTextContent(/output executed/i);
    expect(operationCard).not.toHaveTextContent("slack-secret-value");
    expect(operationCard).not.toHaveTextContent("body-secret-value");
    expect(screen.getByTestId("runs-trace-path")).toHaveTextContent(/operation webhook_result\/span-operation/i);

    outlineRender.unmount();
    searchParamsMock = new URLSearchParams("inspect=operation:2001&pane=request");
    const requestRender = render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-operation-2001-request-metadata")).toHaveTextContent(/redacted/i);
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
    expect(screen.getByText("http_status_error")).toBeVisible();
    expect(screen.getByText("Webhook returned 500.")).toBeVisible();
    expect(screen.getByText(/statusCode/)).toBeVisible();
    failedRender.unmount();

    searchParamsMock = new URLSearchParams("pane=trace");
    render(<RunsDetailPage />);
    expect(screen.getByTestId("runs-trace-linkage")).toHaveTextContent(/Operation invocation #2001/i);
  });
});
