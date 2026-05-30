import { expect, test } from "@playwright/test";
const NOW = "2026-04-20T10:00:00Z";

const packageRead = {
  compiledHash: "compiled-hash-123",
  createdAt: "2026-05-01T10:00:00Z",
  description: "Package for neutral research workflows.",
  id: 42,
  key: "market_review_package",
  manifestHash: "manifest-hash-123",
  name: "Market Review Package",
  updatedAt: "2026-05-05T10:00:00Z",
};

const launchRead = {
  blockingErrors: [
    {
      field: "spec.agents[0].modelConnection",
      issue: "This workflow requires native tool calls",
      severity: "error",
    },
  ],
  description: "Run market review",
  inputSchema: {
    properties: {
      ticker: { description: "Ticker symbol", title: "Ticker", type: "string" },
    },
    required: ["ticker"],
    type: "object",
  },
  manifestHash: "manifest-hash-123",
  name: "Market Review",
  packageId: 42,
  packageKey: "market_review_package",
  ready: false,
  warnings: [
    {
      field: "spec.agents[1].modelConnection",
      issue:
        "This model connection omits usage metadata, so run usage totals will be derived from the response body.",
      severity: "warning",
    },
  ],
  workflowKey: "market_review",
};

const runtimeInputRegistry = {
  currentMetadata: null,
  history: [],
  packageId: 42,
  packageKey: "market_review_package",
  personal: [],
  workflowKey: "market_review",
};

const runDetail = {
  createdAt: NOW,
  error: null,
  executedTokens: 0,
  finalOutput: { summary: "usage omitted" },
  finishedAt: "2026-04-20T10:00:04Z",
  id: 42,
  inheritedTokens: 0,
  input: { ticker: "AAPL" },
  lineageRootRunId: null,
  memoryArtifacts: [],
  memoryEvents: [],
  packageProvenance: {
    compiledPlan: { workflow: { key: "market_review" } },
    currentPackage: {
      available: true,
      compiledHash: "compiled-hash-abc",
      compiledHashMatchesSnapshot: true,
      manifestHash: "manifest-hash-abc",
      manifestHashMatchesSnapshot: true,
    },
    extensionDependencies: [],
    launchSnapshot: {
      inputSchema: { type: "object" },
      parameters: { ticker: "AAPL" },
      workflowDescription: "Review market context.",
      workflowKey: "market_review",
      workflowName: "Market review",
    },
    localResourceRefs: {
      agents: ["research_agent"],
      capabilityProfiles: [],
      mcpServers: [],
      outputSchemas: [],
      workflows: ["market_review"],
    },
    manifestSource: "apiVersion: signaldeck.workflowPackage/v1",
    preflightSummary: { ready: true, blockingErrors: [], warnings: [] },
    packageDefinition: { package: { key: "market_review_package" } },
    resolvedModelConnections: [
      {
        apiStyle: "responses",
        baseUrl: "https://api.openai.com/v1",
        capabilities: {
          chatCompletions: {
            detail: "Chat completions support was recorded for the frozen run profile.",
            lastProbedAt: "2026-05-08T07:10:00Z",
            status: "supported",
          },
          jsonObjectOutput: {
            detail: "JSON object validation is available.",
            lastProbedAt: "2026-05-08T07:11:00Z",
            status: "supported",
          },
          nativeToolCalls: {
            detail: "Native tool calls are not available on this run snapshot.",
            lastProbedAt: "2026-05-08T07:13:00Z",
            status: "unsupported",
          },
          parallelToolCalls: {
            detail: "Parallel tool calls were serialized to preserve compatibility.",
            lastProbedAt: "2026-05-08T07:14:00Z",
            status: "unsupported",
          },
          reasoningHints: {
            detail: "Reasoning hints were accepted.",
            lastProbedAt: "2026-05-08T07:15:00Z",
            status: "supported",
          },
          responsesApi: {
            detail: "Responses API support was recorded for the frozen run profile.",
            lastProbedAt: "2026-05-08T07:16:00Z",
            status: "supported",
          },
          streaming: {
            detail: "Streaming was available during the probe.",
            lastProbedAt: "2026-05-08T07:17:00Z",
            status: "supported",
          },
          strictJsonSchemaOutput: {
            detail: "Strict JSON schema output was accepted.",
            lastProbedAt: "2026-05-08T07:18:00Z",
            status: "supported",
          },
          systemMessages: {
            detail: "System messages were accepted.",
            lastProbedAt: "2026-05-08T07:19:00Z",
            status: "supported",
          },
          textGeneration: {
            detail: "Text generation is supported.",
            lastProbedAt: "2026-05-08T07:20:00Z",
            status: "supported",
          },
          usageReporting: {
            detail: "Usage metadata was not reported by the fake provider.",
            lastProbedAt: "2026-05-08T07:21:00Z",
            status: "unsupported",
          },
        },
          hasApiKey: true,
        key: "primary_openai",
        modelId: "gpt-5.5",
        name: "Primary OpenAI",
        outputStrategyPolicy: "prefer_strict_schema",
        parallelToolCallsPolicy: "serialize",
        probeCacheTtlSeconds: 900,
        protocolProfile: "openai_responses",
        reasoningEffort: "medium",
        reasoningPolicy: "allow",
        streamingPolicy: "allow",
        timeoutSeconds: 60,
      },
    ],
    workflowDescription: "Review market context.",
    workflowKey: "market_review",
    workflowName: "Market review",
    workflowPackageCompiledHash: "compiled-hash-abc",
    workflowPackageDescription: "Snapshot package for market reviews.",
    workflowPackageId: 7,
    workflowPackageKey: "market_review_package",
    workflowPackageManifestHash: "manifest-hash-abc",
    workflowPackageName: "Market Review Package",
    workflowPackageStatus: "active",
  },
  progress: {
    percent: 100,
    terminalCount: 1,
    totalCount: 1,
    unit: "invocation",
  },
  queue: null,
  queuedAt: NOW,
  extensionDependencies: [],
  replayStepIndex: null,
  resumeStepIndex: 1,
  sourceRunId: null,
  startedAt: NOW,
  status: "succeeded",
  steps: [
    {
      id: 101,
      index: 1,
      invocations: [
        {
          agentKey: "research_agent",
          agentRef: { scope: "global", id: 11, key: "research_agent", version: 3 },
          agentVersion: 3,
          createdAt: NOW,
          durationMs: 8,
          errorCode: null,
          errorDetails: [],
          errorMessage: null,
          finishedAt: "2026-04-20T10:00:03Z",
          graphMetadata: {
            modelGateway: {
              selectedStrategies: {
                outputStrategy: "strictJsonSchema",
                parallelToolCalls: false,
                reasoningEffort: "medium",
                reasoningStrategy: "enabled",
                streamingStrategy: "disabled",
                toolCallStrategy: "none",
              },
              usage: null,
            },
          },
          id: 1001,
          inputMode: "wired",
          optional: false,
          output: { summary: "usage omitted" },
          outputOrigin: "executed",
          outputSchemaRef: { scope: "global", id: 21, version: 4 },
          outputSchemaVersion: 4,
          persistedAt: "2026-04-20T10:00:03Z",
          position: 1,
          resolvedInput: { ticker: "AAPL" },
          resolvedInputOrigin: "derived",
          runId: 42,
          runStepId: 101,
          slot: "analysis",
          sourceInvocationId: null,
          startedAt: NOW,
          status: "succeeded",
          stepIndex: 1,
          tokens: 0,
          traceSpanId: "span-1",
          updatedAt: "2026-04-20T10:00:03Z",
          wiring: { from: "inputs.ticker" },
        },
      ],
      origin: "executed",
      operationInvocations: [],
    },
  ],
  targetId: 7,
  targetKey: "market_review_package",
  targetKind: "workflowPackage",
  totalTokens: 0,
  traceId: "trace-42",
  updatedAt: "2026-04-20T10:00:04Z",
};

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("http://127.0.0.1:8001/api/**", async (route) => {
    const { pathname, searchParams } = new URL(route.request().url());
    const method = route.request().method();

    if (pathname === "/api/extensions" && method === "GET") {
      return route.fulfill({ json: { items: [{ enabled: true, key: "signaldeck.finance", label: "Finance Workspace" }] } });
    }

    if (pathname === "/api/tools" && method === "GET") {
      return route.fulfill({ json: { items: [] } });
    }

    if (pathname === "/api/workflow-packages/42" && method === "GET") {
      return route.fulfill({ json: packageRead });
    }

    if (pathname === "/api/workflow-packages/42/launch" && method === "GET") {
      return route.fulfill({ json: launchRead });
    }

    if (pathname === "/api/workflow-packages/42/runtime-input-registry" && method === "GET") {
      if (searchParams.get("workflowKey") === "market_review") {
        return route.fulfill({ json: runtimeInputRegistry });
      }
    }

    if (pathname === "/api/runs/42" && method === "GET") {
      return route.fulfill({ json: runDetail });
    }

    return route.fulfill({ json: {} });
  });
}

test.describe("provider compatibility browser mocks", () => {
  test("renders launch blockers, warnings, and run runtime profile deterministically", async ({ page }) => {
    await mockApi(page);

    await page.goto("/workflow-packages/42/run");
    await expect(page.getByTestId("workflow-package-launch-page")).toBeVisible();
    await expect(page.getByTestId("workflow-package-launch-blockers")).toContainText(
      "This workflow requires native tool calls",
    );
    await expect(page.getByTestId("workflow-package-launch-warnings")).toContainText(
      "omits usage metadata",
    );
    await expect(page.getByTestId("workflow-package-preflight-status")).toContainText(
      "Needs attention",
    );
    await expect(page.getByRole("button", { name: "Launch Run" })).toBeEnabled();

    await page.goto("/runs/42");
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-runtime-profile")).toContainText("Usage reporting");
    await expect(page.getByTestId("runs-runtime-profile")).toContainText("Unsupported");
    await expect(page.getByTestId("runs-runtime-strategy-1-1001")).toContainText(
      "strictJsonSchema",
    );
    await expect(page.getByTestId("runs-summary-usage-row")).toContainText("0");
  });
});
