import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Layout } from "@/components/layout";
import { ThemeProvider } from "@/components/theme-provider";

import { TryoutPage } from "./index";

type ActiveScenario = {
  artifact?: {
    executionContextBody?: string | null;
    finalOutput?: unknown;
    promptReportSlug?: string | null;
    reportMarkdown?: string | null;
    resolvedCapabilities?: Array<{ capabilityKey: string }>;
    resolvedPersonaProfileRefs?: Array<{ personaProfileKey: string }>;
  };
  run?: {
    agentSpecKey?: string | null;
    agentSpecVersion?: number | null;
    executionKind?: "workflow" | "single_agent";
    pendingApprovalIds?: number[];
    status?: string;
    updatedAt?: string;
    workflowSpecKey?: string | null;
    workflowSpecVersion?: number | null;
  };
  trace?: Array<{ eventIndex: number; eventType: string; payload?: Record<string, unknown> }>;
  tryout?: {
    finalOutput?: unknown;
    status?: string;
  };
};

const state = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  createTryoutMock: vi.fn(),
  persistTryoutMock: vi.fn(),
  approveMutationMock: vi.fn(),
  denyMutationMock: vi.fn(),
  tryoutRefetchMock: vi.fn(async () => undefined),
  runtimeRunRefetchMock: vi.fn(async () => undefined),
  runtimeArtifactRefetchMock: vi.fn(async () => undefined),
  runtimeTraceRefetchMock: vi.fn(async () => undefined),
  activeRunId: undefined as number | undefined,
  activeScenario: {} as ActiveScenario,
  workflowSpecs: [
    {
      id: 201,
      key: "growth_tryout_v1",
      version: 3,
      origin: "managed",
      status: "ACTIVE",
      name: "Growth workflow",
      graphDefinition: {},
      finalOutputContract: {},
      mentionPolicy: { version: 1, allowCharacterPersonas: true, allowedBuiltinHandles: [] },
      executionMode: null,
      defaultToolIds: [],
      allowedCapabilityBundleKeys: [],
      connectorIds: [],
      reviewMode: null,
      approvalPolicyOverrides: [],
      createdAt: "2026-04-14T09:00:00Z",
      updatedAt: "2026-04-14T09:00:00Z",
      entryAgentKey: "growth_analyst",
    },
  ],
  agentSpecs: [
    {
      id: 301,
      key: "solo_agent_v1",
      version: 5,
      origin: "managed",
      status: "ACTIVE",
      name: "Solo Agent",
      instructions: "Inspect the request.",
      modelPolicy: {},
      finalOutputContract: null,
      defaultCapabilityBundleKeys: [],
      defaultPersonaProfileKeys: [],
      createdAt: "2026-04-14T09:00:00Z",
      updatedAt: "2026-04-14T09:00:00Z",
    },
  ],
  personaProfiles: [
    {
      id: 401,
      key: "persona.alpha",
      version: 2,
      origin: "managed",
      status: "ACTIVE",
      kind: "managed_persona",
      displayName: "Alpha Persona",
      enabled: true,
      handle: "@alpha",
      canonicalTargetId: "persona:alpha",
      parentProfileKey: null,
      parentProfileVersion: null,
      legacySourceVersion: null,
      systemPromptFragment: "Lead with clarity.",
      promptAppendFragment: "",
      defaultCapabilityBundleKeys: [],
      createdAt: "2026-04-14T09:00:00Z",
      updatedAt: "2026-04-14T09:00:00Z",
    },
  ],
  approvalDetailState: new Map<
    number,
    { status: string; allowedActions: Array<"approve" | "deny"> }
  >(),
}));

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

function setActiveScenario(runId: number, scenario: ActiveScenario) {
  state.activeRunId = runId;
  state.activeScenario = scenario;
}

function buildTryoutQuery(runId: number | string | undefined) {
  if (!runId || Number(runId) !== state.activeRunId) {
    return {
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
      refetch: state.tryoutRefetchMock,
    };
  }

  return {
    data: {
      runId: Number(runId),
      status: state.activeScenario.tryout?.status ?? "QUEUED",
      finalOutput: state.activeScenario.tryout?.finalOutput ?? null,
      reportMarkdown: state.activeScenario.artifact?.reportMarkdown ?? null,
      traceSummary: { eventCount: state.activeScenario.trace?.length ?? 0, toolCallCount: 1, warningCount: 0, lastEventAt: null },
      approvalSummary: {
        totalCount: state.activeScenario.run?.pendingApprovalIds?.length ?? 0,
        pendingCount: state.activeScenario.run?.pendingApprovalIds?.length ?? 0,
        approvedCount: 0,
        deniedCount: 0,
        expiredCount: 0,
      },
      expiresAt: null,
      terminalError: null,
    },
    error: null,
    isError: false,
    isPending: false,
    refetch: state.tryoutRefetchMock,
  };
}

function buildRuntimeRunQuery(runId: number | string | undefined) {
  if (!runId || Number(runId) !== state.activeRunId) {
    return {
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
      refetch: state.runtimeRunRefetchMock,
    };
  }

  return {
    data: {
      runId: Number(runId),
      status: state.activeScenario.run?.status ?? state.activeScenario.tryout?.status ?? "QUEUED",
      callerType: "tryout",
      callerId: null,
      callerScopeKey: null,
      callerIdentityKey: null,
      executionKind: state.activeScenario.run?.executionKind ?? "workflow",
      workflowSpecKey: state.activeScenario.run?.workflowSpecKey ?? "growth_tryout_v1",
      workflowSpecVersion: state.activeScenario.run?.workflowSpecVersion ?? 3,
      agentSpecKey: state.activeScenario.run?.agentSpecKey ?? null,
      agentSpecVersion: state.activeScenario.run?.agentSpecVersion ?? null,
      attemptNumber: 1,
      expiresAt: null,
      createdAt: "2026-04-14T10:00:00Z",
      updatedAt: state.activeScenario.run?.updatedAt ?? "2026-04-14T10:02:00Z",
      pendingApprovalIds: state.activeScenario.run?.pendingApprovalIds ?? [],
      finalOutput: state.activeScenario.tryout?.finalOutput ?? null,
      traceSummary: { eventCount: state.activeScenario.trace?.length ?? 0, toolCallCount: 1, warningCount: 0, lastEventAt: null },
      approvalSummary: {
        totalCount: state.activeScenario.run?.pendingApprovalIds?.length ?? 0,
        pendingCount: state.activeScenario.run?.pendingApprovalIds?.length ?? 0,
        approvedCount: 0,
        deniedCount: 0,
        expiredCount: 0,
      },
      terminalError: null,
    },
    error: null,
    isError: false,
    isPending: false,
    refetch: state.runtimeRunRefetchMock,
  };
}

function buildArtifactQuery(runId: number | string | undefined) {
  if (!runId || Number(runId) !== state.activeRunId) {
    return { data: undefined, isPending: false, refetch: state.runtimeArtifactRefetchMock };
  }

  return {
    data: {
      runId: Number(runId),
      finalOutput:
        state.activeScenario.artifact?.finalOutput ?? state.activeScenario.tryout?.finalOutput ?? null,
      reportMarkdown: state.activeScenario.artifact?.reportMarkdown ?? null,
      normalizedTradeDecisions: null,
      entryPromptHash: "entry-hash",
      fullUserPromptHash: "prompt-hash",
      authoredEntryPromptBody: null,
      compiledEntryPromptBody: null,
      executionContextBody: state.activeScenario.artifact?.executionContextBody ?? "Execution context",
      promptReportSlug: state.activeScenario.artifact?.promptReportSlug ?? null,
      rawMentionHandles: [],
      resolvedMentions: [],
      mentionedTargetOutputs: [],
      resolvedPersonaProfileRefs: state.activeScenario.artifact?.resolvedPersonaProfileRefs ?? [],
      resolvedWorkflowAgentRefs: [],
      resolvedCapabilities: state.activeScenario.artifact?.resolvedCapabilities ?? [],
      resolvedBuiltinVersions: [],
      resolvedRoleVersions: [],
      resolvedCharacterVersions: [],
      resolvedBundleVersions: [],
      resolvedToolVersions: [],
      resolvedConnectorVersions: [],
      traceSummary: { eventCount: state.activeScenario.trace?.length ?? 0, toolCallCount: 1, warningCount: 0, lastEventAt: null },
      approvalSummary: { totalCount: 0, pendingCount: 0, approvedCount: 0, deniedCount: 0, expiredCount: 0 },
      createdAt: "2026-04-14T10:00:00Z",
      terminalError: null,
    },
    isPending: false,
    refetch: state.runtimeArtifactRefetchMock,
  };
}

function buildTraceQuery(runId: number | string | undefined) {
  if (!runId || Number(runId) !== state.activeRunId) {
    return {
      data: { items: [], nextCursor: null },
      isPending: false,
      refetch: state.runtimeTraceRefetchMock,
    };
  }

  return {
    data: {
      items: (state.activeScenario.trace ?? []).map((event) => ({
        runId: Number(runId),
        eventIndex: event.eventIndex,
        eventType: event.eventType,
        stepKey: null,
        capabilityKey: null,
        callerType: "tryout",
        callerId: null,
        createdAt: "2026-04-14T10:05:00Z",
        approvalId: null,
        payload: event.payload ?? {},
      })),
      nextCursor: null,
    },
    isPending: false,
    refetch: state.runtimeTraceRefetchMock,
  };
}

vi.mock("sonner", () => ({
  toast: {
    error: state.toastErrorMock,
    success: state.toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-studio", () => ({
  useStudioWorkflowSpecs: () => ({ data: { items: state.workflowSpecs }, isPending: false }),
  useStudioAgentSpecs: () => ({ data: { items: state.agentSpecs }, isPending: false }),
  useStudioPersonas: () => ({ data: { items: state.personaProfiles }, isPending: false }),
}));

vi.mock("@/hooks/use-tryouts", () => ({
  useCreateTryout: () => ({ isPending: false, mutateAsync: state.createTryoutMock }),
  usePersistTryout: (runId: number | undefined) => ({
    isPending: false,
    mutateAsync: () => state.persistTryoutMock(runId),
  }),
  useTryout: (runId: number | string | undefined) => buildTryoutQuery(runId),
}));

vi.mock("@/hooks/use-runtime", () => ({
  useRuntimeRun: (runId: number | string | undefined) => buildRuntimeRunQuery(runId),
  useRuntimeRunArtifact: (runId: number | string | undefined) => buildArtifactQuery(runId),
  useRuntimeRunTrace: (runId: number | string | undefined) => buildTraceQuery(runId),
  useRuntimeApproval: (approvalId: number | string | undefined) => ({
    data: approvalId
      ? {
          approvalId: Number(approvalId),
          runId: state.activeRunId ?? 0,
          status: state.approvalDetailState.get(Number(approvalId))?.status ?? "PENDING",
          capabilityKey: "connector.market_data",
          stepKey: "review_step",
          callerType: "tryout",
          callerId: null,
          createdAt: "2026-04-14T10:04:00Z",
          summary: {
            approvalMode: "required",
            displayName: "Market data connector",
            transport: "http",
          },
          allowedActions:
            state.approvalDetailState.get(Number(approvalId))?.allowedActions ?? ["approve", "deny"],
        }
      : undefined,
    error: null,
    isError: false,
    isPending: false,
  }),
  useApproveRuntimeApproval: () => ({ isPending: false, mutateAsync: state.approveMutationMock }),
  useDenyRuntimeApproval: () => ({ isPending: false, mutateAsync: state.denyMutationMock }),
}));

describe("TryoutPage", () => {
  beforeEach(() => {
    state.activeRunId = undefined;
    state.activeScenario = {};
    state.approvalDetailState.clear();
    state.workflowSpecs.splice(
      0,
      state.workflowSpecs.length,
      {
        id: 201,
        key: "growth_tryout_v1",
        version: 3,
        origin: "managed",
        status: "ACTIVE",
        name: "Growth workflow",
        graphDefinition: {},
        finalOutputContract: {},
        mentionPolicy: { version: 1, allowCharacterPersonas: true, allowedBuiltinHandles: [] },
        executionMode: null,
        defaultToolIds: [],
        allowedCapabilityBundleKeys: [],
        connectorIds: [],
        reviewMode: null,
        approvalPolicyOverrides: [],
        createdAt: "2026-04-14T09:00:00Z",
        updatedAt: "2026-04-14T09:00:00Z",
        entryAgentKey: "growth_analyst",
      },
    );

    state.toastErrorMock.mockReset();
    state.toastSuccessMock.mockReset();
    state.createTryoutMock.mockReset();
    state.persistTryoutMock.mockReset();
    state.approveMutationMock.mockReset();
    state.denyMutationMock.mockReset();
    state.tryoutRefetchMock.mockClear();
    state.runtimeRunRefetchMock.mockClear();
    state.runtimeArtifactRefetchMock.mockClear();
    state.runtimeTraceRefetchMock.mockClear();
  });

  it("renders the Tryout nav entry and page inside the main layout shell", () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={["/tryout"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/tryout" element={<TryoutPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByTestId("nav-tryout")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tryout/i })).toBeInTheDocument();
    expect(screen.getByTestId("tryout-page")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tryout" })).toBeInTheDocument();
  });

  it("executes a tryout, pins the active run id, and renders persisted detail panels", async () => {
    state.createTryoutMock.mockImplementation(async () => {
      setActiveScenario(501, {
        artifact: {
          finalOutput: { summary: "Queued output" },
          promptReportSlug: "prompt-501",
          resolvedCapabilities: [{ capabilityKey: "connector.market_data" }],
          resolvedPersonaProfileRefs: [{ personaProfileKey: "persona.alpha" }],
        },
        run: {
          executionKind: "workflow",
          pendingApprovalIds: [],
          status: "QUEUED",
          workflowSpecKey: "growth_tryout_v1",
          workflowSpecVersion: 3,
        },
        trace: [{ eventIndex: 3, eventType: "RUN_CREATED", payload: { source: "test" } }],
        tryout: { finalOutput: { summary: "Queued output" }, status: "QUEUED" },
      });

      return { runId: 501, status: "QUEUED", expiresAt: null };
    });

    render(<TryoutPage />);

    fireEvent.click(screen.getByText(/alpha persona/i));
    fireEvent.click(screen.getByRole("button", { name: /add input/i }));
    fireEvent.change(screen.getByPlaceholderText("ticker"), { target: { value: "ticker" } });
    fireEvent.change(screen.getByPlaceholderText("AAPL"), { target: { value: "MSFT" } });
    fireEvent.click(screen.getByTestId("tryout-execute-button"));

    await waitFor(() => expect(state.createTryoutMock).toHaveBeenCalled());

    expect(state.createTryoutMock).toHaveBeenCalledWith(
      expect.objectContaining({
        inputs: { ticker: "MSFT" },
        personaProfileRefs: [
          expect.objectContaining({ personaProfileKey: "persona.alpha", personaProfileVersion: 2 }),
        ],
        workflowSpecKey: "growth_tryout_v1",
        workflowSpecVersion: 3,
      }),
    );
    expect(screen.getByTestId("tryout-status-panel")).toHaveTextContent(/run #501/i);
    expect(screen.getByTestId("tryout-final-output")).toHaveTextContent(/queued output/i);
    expect(screen.getByTestId("tryout-trace-row-3")).toBeInTheDocument();
  });

  it("keeps every workflow spec selectable, including seeded workflow entries", async () => {
    state.workflowSpecs.splice(0, state.workflowSpecs.length, {
      id: 202,
      key: "seeded_review_workflow_v1",
      version: 1,
      origin: "seeded",
      status: "ACTIVE",
      name: "Seeded review workflow",
      graphDefinition: {},
      finalOutputContract: {},
      mentionPolicy: { version: 1, allowCharacterPersonas: true, allowedBuiltinHandles: [] },
      executionMode: null,
      defaultToolIds: [],
      allowedCapabilityBundleKeys: [],
      connectorIds: [],
      reviewMode: null,
      approvalPolicyOverrides: [],
      createdAt: "2026-04-14T09:00:00Z",
      updatedAt: "2026-04-14T09:00:00Z",
      entryAgentKey: "growth_analyst",
    });
    state.createTryoutMock.mockResolvedValue({ runId: 502, status: "QUEUED", expiresAt: null });

    render(<TryoutPage />);

    expect(screen.getByTestId("tryout-workflow-select")).toHaveTextContent(/seeded review workflow/i);

    fireEvent.click(screen.getByTestId("tryout-execute-button"));

    await waitFor(() => expect(state.createTryoutMock).toHaveBeenCalled());
    expect(state.createTryoutMock).toHaveBeenCalledWith(
      expect.objectContaining({
        workflowSpecKey: "seeded_review_workflow_v1",
        workflowSpecVersion: 1,
      }),
    );
  });

  it("renders the approval panel and actions for waiting-approval runs", async () => {
    state.approvalDetailState.set(61, { status: "PENDING", allowedActions: ["approve", "deny"] });
    state.createTryoutMock.mockImplementation(async () => {
      setActiveScenario(601, {
        run: {
          executionKind: "workflow",
          pendingApprovalIds: [61],
          status: "WAITING_APPROVAL",
          workflowSpecKey: "growth_tryout_v1",
          workflowSpecVersion: 3,
        },
        trace: [{ eventIndex: 4, eventType: "APPROVAL_REQUESTED" }],
        tryout: { finalOutput: null, status: "WAITING_APPROVAL" },
      });

      return { runId: 601, status: "WAITING_APPROVAL", expiresAt: null };
    });

    render(<TryoutPage />);
    fireEvent.click(screen.getByTestId("tryout-execute-button"));

    expect(await screen.findByTestId("tryout-approval-panel")).toHaveTextContent(/approval #61/i);
    expect(screen.getByTestId("tryout-approval-approve-61")).toBeInTheDocument();
    expect(screen.getByTestId("tryout-approval-deny-61")).toBeInTheDocument();
  });

  it("persists the active run in place without switching to a new run id", async () => {
    state.createTryoutMock.mockImplementation(async () => {
      setActiveScenario(701, {
        run: {
          executionKind: "workflow",
          pendingApprovalIds: [],
          status: "QUEUED",
          workflowSpecKey: "growth_tryout_v1",
          workflowSpecVersion: 3,
        },
        trace: [{ eventIndex: 5, eventType: "RUN_CREATED" }],
        tryout: { finalOutput: { summary: "Queued output" }, status: "QUEUED" },
      });

      return { runId: 701, status: "QUEUED", expiresAt: null };
    });
    state.persistTryoutMock.mockResolvedValue({ runId: 701, status: "QUEUED", finalOutput: null, reportMarkdown: null, traceSummary: { eventCount: 1, toolCallCount: 0, warningCount: 0, lastEventAt: null }, approvalSummary: { totalCount: 0, pendingCount: 0, approvedCount: 0, deniedCount: 0, expiredCount: 0 }, expiresAt: null, terminalError: null });

    render(<TryoutPage />);
    fireEvent.click(screen.getByTestId("tryout-execute-button"));

    expect(await screen.findByText(/active run #701/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tryout-persist-button"));

    await waitFor(() => expect(state.persistTryoutMock).toHaveBeenCalledWith(701));
    expect(screen.getByText(/active run #701/i)).toBeInTheDocument();
  });

  it("refreshes persisted detail after approval resolution instead of trusting the mutation payload", async () => {
    state.approvalDetailState.set(81, { status: "PENDING", allowedActions: ["approve", "deny"] });
    state.createTryoutMock.mockImplementation(async () => {
      setActiveScenario(801, {
        artifact: { finalOutput: null },
        run: {
          executionKind: "workflow",
          pendingApprovalIds: [81],
          status: "WAITING_APPROVAL",
          workflowSpecKey: "growth_tryout_v1",
          workflowSpecVersion: 3,
        },
        trace: [{ eventIndex: 6, eventType: "APPROVAL_REQUESTED" }],
        tryout: { finalOutput: null, status: "WAITING_APPROVAL" },
      });

      return { runId: 801, status: "WAITING_APPROVAL", expiresAt: null };
    });
    state.approveMutationMock.mockImplementation(async () => {
      state.approvalDetailState.set(81, { status: "APPROVED", allowedActions: [] });
      setActiveScenario(801, {
        artifact: { finalOutput: { summary: "Resolved after refresh" } },
        run: {
          executionKind: "workflow",
          pendingApprovalIds: [],
          status: "SUCCEEDED",
          workflowSpecKey: "growth_tryout_v1",
          workflowSpecVersion: 3,
        },
        trace: [{ eventIndex: 7, eventType: "APPROVAL_RESOLVED", payload: { outcome: "approved" } }],
        tryout: { finalOutput: { summary: "Resolved after refresh" }, status: "SUCCEEDED" },
      });

      return {
        approvalId: 81,
        status: "APPROVED",
        runId: 801,
        resolvedAt: "2026-04-14T10:08:00Z",
        runStatus: "WAITING_APPROVAL",
      };
    });

    const view = render(<TryoutPage />);
    fireEvent.click(screen.getByTestId("tryout-execute-button"));

    expect(await screen.findByTestId("tryout-approval-approve-81")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tryout-approval-approve-81"));

    await waitFor(() => expect(state.approveMutationMock).toHaveBeenCalled());
    await waitFor(() => expect(state.tryoutRefetchMock).toHaveBeenCalled());
    await waitFor(() => expect(state.runtimeRunRefetchMock).toHaveBeenCalled());
    view.rerender(<TryoutPage />);

    expect(screen.getByTestId("tryout-status-panel")).toHaveTextContent(/succeeded/i);
    expect(screen.getByTestId("tryout-final-output")).toHaveTextContent(/resolved after refresh/i);
    expect(screen.getByTestId("tryout-approval-panel")).toHaveTextContent(
      /not waiting on approvals/i,
    );
  });
});
