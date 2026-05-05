import type {
  RunAgentInvocationRead,
  RunCreatedRead,
  RunRead,
  RunRerunDraftRead,
  RunStepReplayDraftRead,
  RunStepRead,
} from "../src/lib/types/run";

const DEFAULT_TIME = "2026-04-29T10:00:00Z";

export function buildRunInvocation(
  overrides: Partial<RunAgentInvocationRead> = {},
): RunAgentInvocationRead {
  return {
    agentId: 1,
    agentKey: "playwright_agent",
    agentVersion: 1,
    createdAt: DEFAULT_TIME,
    durationMs: 5,
    errorCode: null,
    errorDetails: [],
    errorMessage: null,
    finishedAt: "2026-04-29T10:00:04Z",
    id: 1001,
    inputMode: "wired",
    graphMetadata: null,
    optional: false,
    output: { summary: "Playwright summary" },
    outputOrigin: "executed",
    outputSchemaId: 1,
    outputSchemaVersion: 1,
    persistedAt: "2026-04-29T10:00:04Z",
    position: 1,
    resolvedInput: {},
    resolvedInputOrigin: "derived",
    runId: 1,
    runStepId: 101,
    slot: "analysis",
    sourceInvocationId: null,
    startedAt: "2026-04-29T10:00:01Z",
    status: "succeeded",
    stepIndex: 1,
    tokens: 18,
    traceSpanId: null,
    updatedAt: "2026-04-29T10:00:04Z",
    wiring: {},
    ...overrides,
  };
}

export function buildRunStep(overrides: Partial<RunStepRead> = {}): RunStepRead {
  return {
    createdAt: DEFAULT_TIME,
    error: null,
    finishedAt: "2026-04-29T10:00:04Z",
    id: 101,
    index: 1,
    graphMetadata: null,
    invocations: [],
    origin: "planned",
    persistedAt: "2026-04-29T10:00:04Z",
    runId: 1,
    sourceRunId: null,
    sourceRunStepId: null,
    sourceStepIndex: null,
    startedAt: "2026-04-29T10:00:01Z",
    status: "succeeded",
    updatedAt: "2026-04-29T10:00:04Z",
    ...overrides,
  };
}

export function buildRunDetail(overrides: Partial<RunRead> = {}): RunRead {
  return {
    createdAt: DEFAULT_TIME,
    error: null,
    executedTokens: 18,
    finalOutput: { summary: "Playwright summary" },
    finishedAt: "2026-04-29T10:00:04Z",
    replayStepIndex: null,
    id: 1,
    inheritedTokens: 0,
    input: {},
    lineageRootRunId: null,
    memoryArtifacts: [],
    queuedAt: DEFAULT_TIME,
    resumeStepIndex: 1,
    sourceRunId: null,
    startedAt: "2026-04-29T10:00:01Z",
    status: "succeeded",
    steps: [],
    targetId: 1,
    targetKey: "playwright_target",
    targetKind: "workflow",
    targetVersion: 1,
    totalTokens: 18,
    traceId: null,
    updatedAt: "2026-04-29T10:00:04Z",
    ...overrides,
  };
}

export function buildRunCreated(overrides: Partial<RunCreatedRead> = {}): RunCreatedRead {
  return {
    createdAt: DEFAULT_TIME,
    id: 1,
    status: "running",
    targetId: 1,
    targetKey: "playwright_target",
    targetKind: "workflow",
    targetVersion: 1,
    traceId: null,
    ...overrides,
  };
}

export function buildRerunDraft(overrides: Partial<RunRerunDraftRead> = {}): RunRerunDraftRead {
  return {
    parameters: {},
    sourceRunId: 1,
    targetId: 1,
    targetKey: "playwright_target",
    targetKind: "workflow",
    targetVersion: 1,
    ...overrides,
  };
}

export function buildStepReplayDraft(overrides: Partial<RunStepReplayDraftRead> = {}): RunStepReplayDraftRead {
  return {
    parameters: {},
    replayStepIndex: 1,
    sourceRunId: 1,
    targetId: 1,
    targetKey: "playwright_target",
    targetKind: "workflow",
    targetVersion: 1,
    ...overrides,
  };
}
