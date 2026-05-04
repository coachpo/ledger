import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  buildRerunDraft,
  buildRunCreated,
  buildRunDetail,
  buildRunInvocation,
  buildRunStep,
  buildStepReplayDraft,
} from "./run-detail-fixtures";

const PLATFORM_API = "http://127.0.0.1:8001/api";

type OutputSchemaRead = {
  id: number;
  key: string;
  version: number;
};

type ModelConnectionRead = {
  id: number;
  key: string;
};

type AgentRead = {
  id: number;
  key: string;
  version: number;
};

async function createPublishedOutputSchema(
  request: APIRequestContext,
  key: string,
): Promise<OutputSchemaRead> {
  const createResponse = await request.post(`${PLATFORM_API}/output-schemas`, {
    data: {
      builder: {
        allowAdditionalProperties: false,
        fields: [{ name: "summary", required: true, schema: { kind: "string" } }],
        kind: "object",
      },
      key,
      kind: "standalone",
      name: `Schema ${key}`,
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const draft = (await createResponse.json()) as OutputSchemaRead;
  const activateResponse = await request.post(`${PLATFORM_API}/output-schemas/${draft.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as OutputSchemaRead;
}

async function createModelConnection(
  request: APIRequestContext,
  key: string,
): Promise<ModelConnectionRead> {
  const response = await request.post(`${PLATFORM_API}/model-connections`, {
    data: {
      apiKey: "playwright-redacted-key",
      baseUrl: "https://api.openai.com/v1",
      description: "Playwright-only workflow YAML model connection.",
      key,
      modelId: `gpt-${key}`,
      name: `Model ${key}`,
      reasoningEffort: "low",
      timeoutSeconds: 10,
    },
  });

  expect(response.ok()).toBeTruthy();
  return (await response.json()) as ModelConnectionRead;
}

async function createPublishedAgent(
  request: APIRequestContext,
  options: {
    key: string;
    modelConnectionKey: string;
    outputSchemaKey: string;
    outputSchemaVersion: number;
  },
): Promise<AgentRead> {
  const manifestSource = `apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: ${options.key}
  name: Agent ${options.key}
  description: Summarizes ticker research for a workflow YAML E2E test.
spec:
  modelConnection: ${options.modelConnectionKey}
  systemPrompt: Return a concise summary.
  inputSchema:
    type: object
    properties:
      ticker:
        type: string
    required:
      - ticker
    additionalProperties: false
  outputSchema: ${options.outputSchemaKey}@${options.outputSchemaVersion}
  capabilities: []
  mcpServers: []
  budgetUsd: "0.25"
`;
  const response = await request.post(`${PLATFORM_API}/agents`, {
    data: {
      manifestSource,
    },
  });

  expect(response.ok()).toBeTruthy();
  return (await response.json()) as AgentRead;
}

function workflowManifest(options: {
  agentKey: string;
  description: string;
  key: string;
  name: string;
}): string {
  return `apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: ${options.key}
  name: ${options.name}
  description: ${options.description}
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: ${options.agentKey}@1
        with:
          ticker: \${{ inputs.ticker }}
  - id: final_review
    agents:
      - slot: decision
        uses: ${options.agentKey}@1
        with:
          ticker: \${{ steps.research.outputs.analysis.summary }}
output:
  from: \${{ steps.final_review.outputs.decision }}
`;
}

function workflowV2Manifest(options: { agentKey: string; key: string; loopMaxIterations?: number }): string {
  const loopBound = options.loopMaxIterations ? `      maxIterations: ${options.loopMaxIterations}\n` : "";
  return `apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: ${options.key}
  name: Workflow Graph Preview
  description: Validates graph preview without replacing YAML source editing.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
  additionalProperties: false
flow:
  kind: sequence
  id: root_sequence
  nodes:
    - kind: fanout
      id: analyst_fanout
      branches:
        - id: market
          node:
            kind: step
            id: market_analysis
            slot: market
            uses: ${options.agentKey}@1
            with:
              ticker: \${{ inputs.ticker }}
        - id: news
          node:
            kind: step
            id: news_analysis
            slot: news
            uses: ${options.agentKey}@1
            with:
              ticker: \${{ inputs.ticker }}
    - kind: loop
      id: review_loop
${loopBound}      sequence:
        kind: sequence
        id: review_sequence
        nodes:
          - kind: step
            id: risk_review
            slot: risk
            uses: ${options.agentKey}@1
            with:
              ticker: \${{ inputs.ticker }}
    - kind: step
      id: decision
      slot: final
      uses: ${options.agentKey}@1
      with:
        marketReport: \${{ nodes.analyst_fanout.outputs.market }}
        newsReport: \${{ nodes.analyst_fanout.outputs.news }}
        riskReport: \${{ nodes.review_loop.outputs.risk }}
output:
  from: \${{ nodes.root_sequence.outputs.final }}
postRunMemory:
  enabled: true
  source:
    ticker: \${{ inputs.ticker }}
    action: \${{ nodes.decision.outputs.final.action }}
    rationale: \${{ nodes.decision.outputs.final.rationale }}
    riskSummary: \${{ nodes.decision.outputs.final.riskSummary }}
    executionPlan: \${{ nodes.decision.outputs.final.executionPlan }}
`;
}

async function expectYamlOnlyEditor(page: Page) {
  await expect(page.getByTestId("workflow-yaml-editor-shell")).toBeVisible();
  await expect(page.getByTestId("workflow-yaml-editor")).toBeVisible();
  await expect(page.getByTestId("workflow-validate-manifest")).toBeVisible();
  await expect(page.getByTestId("workflow-save")).toBeVisible();
  await expect(page.getByRole("tab", { name: /input|steps|output|review/i })).toHaveCount(0);
  await expect(page.getByTestId("workflow-wizard-next")).toHaveCount(0);
  await expect(page.getByLabel("Input Schema JSON")).toHaveCount(0);
  await expect(page.getByLabel("Run Input JSON")).toHaveCount(0);
}

test.describe("Workflow YAML editor", () => {
  test("renders a stubbed TradingAgents v2 run detail without exposing secrets", async ({ page }) => {
    await page.route("**/api/runs/9901", async (route) => {
      await route.fulfill({
        body: JSON.stringify(
          buildRunDetail({
            finalOutput: {
              action: "buy",
              rationale: "Analyst fanout and bounded debates support a staged buy.",
              riskSummary: "Valuation and volatility remain the main risks.",
              executionPlan: "Research-only staged accumulation.",
            },
            id: 9901,
            input: { ticker: "NVDA" },
            memoryArtifacts: [
              {
                reportId: 990101,
                slug: "agent_memory_nvda_portfolio_manager_run_9901_buy",
                name: "NVDA portfolio manager memory",
                status: "pending",
                createdAt: "2026-05-03T10:00:05Z",
                sourceGraphMetadata: { nodeId: "portfolio_manager", nodeKind: "step", loopId: "risk_debate_loop", loopIteration: 2 },
              },
            ],
            steps: [
              buildRunStep({
                graphMetadata: { nodeKind: "fanout", fanoutId: "analyst_fanout", sourceRefs: { branches: [] } },
                id: 990101,
                invocations: [
                  buildRunInvocation({
                    agentKey: "market_analyst",
                    graphMetadata: { nodeId: "market_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "market" },
                    id: 9901001,
                    output: { summary: "market_report:NVDA" },
                    runId: 9901,
                    runStepId: 990101,
                    slot: "market_report",
                  }),
                  buildRunInvocation({
                    agentKey: "news_analyst",
                    graphMetadata: { nodeId: "news_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "news" },
                    id: 9901002,
                    output: { summary: "news_report:NVDA" },
                    position: 2,
                    runId: 9901,
                    runStepId: 990101,
                    slot: "news_report",
                  }),
                ],
                runId: 9901,
              }),
              buildRunStep({
                id: 990102,
                index: 2,
                invocations: [
                  buildRunInvocation({
                    agentKey: "bull_researcher",
                    graphMetadata: { nodeId: "bull_research", nodeKind: "step", loopId: "investment_debate_loop", loopIteration: 1 },
                    id: 9901003,
                    output: { nextState: { bullCase: "Constructive." } },
                    runId: 9901,
                    runStepId: 990102,
                    slot: "bull",
                    stepIndex: 2,
                  }),
                ],
                runId: 9901,
              }),
              buildRunStep({
                id: 990103,
                index: 3,
                invocations: [
                  buildRunInvocation({
                    agentKey: "portfolio_manager",
                    graphMetadata: { nodeId: "portfolio_manager", nodeKind: "step", loopId: "risk_debate_loop", loopIteration: 2 },
                    id: 9901004,
                    output: { action: "buy", rationale: "Analyst fanout and bounded debates support a staged buy." },
                    runId: 9901,
                    runStepId: 990103,
                    slot: "decision",
                    stepIndex: 3,
                  }),
                ],
                runId: 9901,
              }),
            ],
            targetId: 55,
            targetKey: "tradingagents_v2_practical_fanout_review",
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-tradingagents-v2-9901",
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.goto("/runs/9901");

    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-target-identity")).toContainText("tradingagents_v2_practical_fanout_review@1");
    await expect(page.getByTestId("runs-detail-final-output")).toContainText("Analyst fanout and bounded debates support a staged buy");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("Fanout analyst_fanout");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("branch market");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("Loop investment_debate_loop iteration 1");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("Loop risk_debate_loop iteration 2");
    await expect(page.getByTestId("runs-memory-artifacts")).toContainText("NVDA portfolio manager memory");
    await expect(page.getByRole("link", { name: /open report/i })).toHaveAttribute("href", "/reports/agent_memory_nvda_portfolio_manager_run_9901_buy");
    await expect(page.locator("body")).not.toContainText(/sk-[A-Za-z0-9_-]+/);
    await expect(page.locator("body")).not.toContainText(/api[_ -]?key/i);
  });

  test("renders v2 graph preview and local loop diagnostics without exposing secrets", async ({ page }) => {
    const v2Manifest = workflowV2Manifest({ agentKey: "graph_agent", key: `workflow_graph_${Date.now()}`, loopMaxIterations: 2 });
    const unboundedLoopManifest = workflowV2Manifest({ agentKey: "graph_agent", key: `workflow_graph_${Date.now()}` });
    const compiledGraph = {
      apiVersion: "ledger.workflow/v2",
      rootNodeId: "root_sequence",
      nodes: [
        { id: "root_sequence", nodeId: "root_sequence", kind: "sequence", childNodeIds: ["analyst_fanout", "review_loop", "decision"] },
        { id: "root_sequence.analyst_fanout", nodeId: "analyst_fanout", kind: "fanout", branchIds: ["market", "news"], mode: "concurrent" },
        { id: "root_sequence.analyst_fanout.market.market_analysis", nodeId: "market_analysis", kind: "step", stepIndex: 1, slot: "market", agentKey: "graph_agent", agentVersion: 1, branchId: "market", refs: { ticker: { source: "inputs", path: "ticker" } } },
        { id: "root_sequence.review_loop", nodeId: "review_loop", kind: "loop", maxIterations: 2, sequenceNodeId: "review_sequence" },
        { id: "root_sequence.review_loop.iteration_1.review_sequence.risk_review", nodeId: "risk_review", kind: "step", stepIndex: 2, slot: "risk", agentKey: "graph_agent", agentVersion: 1, loopId: "review_loop", loopIteration: 1 },
      ],
      output: { source: "nodes", nodeId: "root_sequence", slot: "final", stepIndex: 3, compiledSlot: "final" },
      validation: { loopMaxIterations: 10, fanoutMaxBranches: 16 },
      postRunMemory: { enabled: true, sourceRefs: { ticker: { source: "inputs", path: "ticker" } } },
    };

    await page.route("**/api/workflows/validate-manifest", async (route) => {
      await route.fulfill({
        body: JSON.stringify({
          compiledGraph,
          compiledPayload: {
            key: "workflow_graph_preview",
            name: "Workflow Graph Preview",
            inputSchema: { type: "object" },
            steps: [],
            outputSpec: { kind: "slot", stepIndex: 3, slot: "final" },
          },
          diagnostics: [],
          metadata: {
            apiVersion: "ledger.workflow/v2",
            key: "workflow_graph_preview",
            name: "Workflow Graph Preview",
            description: "Validates graph preview without replacing YAML source editing.",
          },
          runInputSchema: { type: "object", properties: { ticker: { type: "string" } } },
        }),
        contentType: "application/json",
      });
    });

    await page.goto("/workflows/new");
    await expectYamlOnlyEditor(page);
    await page.getByTestId("workflow-yaml-editor").fill(unboundedLoopManifest);
    await expect(page.getByTestId("workflow-validation-feedback")).toContainText("maxIterations");
    await page.getByTestId("workflow-yaml-editor").fill(v2Manifest);
    await page.getByTestId("workflow-validate-manifest").click();
    await expect(page.getByTestId("workflow-compiled-graph-preview")).toContainText("analyst_fanout");
    await expect(page.getByTestId("workflow-compiled-graph-preview")).toContainText("review_loop");
    await expect(page.getByTestId("workflow-compiled-graph-preview")).toContainText("iteration 1");
    await expect(page.getByTestId("workflow-compiled-graph-preview")).toContainText("postRunMemory");
    await expect(page.getByLabel("Exact raw compiled graph JSON")).toHaveValue(/ledger\.workflow\/v2/);
    await expect(page.locator("body")).not.toContainText(/sk-[A-Za-z0-9_-]+/);
    await expect(page.locator("body")).not.toContainText(/api[_ -]?key/i);
  });

  test("covers create, reopen, edit, invalid diagnostics, and run launch", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const schema = await createPublishedOutputSchema(request, `workflow_yaml_schema_${timestamp}`);
    const modelConnection = await createModelConnection(request, `workflow_yaml_${timestamp}`);
    const agent = await createPublishedAgent(request, {
      key: `workflow_yaml_agent_${timestamp}`,
      modelConnectionKey: modelConnection.key,
      outputSchemaKey: schema.key,
      outputSchemaVersion: schema.version,
    });
    const workflowKey = `workflow_yaml_${timestamp}`;
    const initialManifest = workflowManifest({
      agentKey: agent.key,
      description: "Reviews YAML-created workflow input.",
      key: workflowKey,
      name: `Workflow YAML ${timestamp}`,
    });
    const editedManifest = workflowManifest({
      agentKey: agent.key,
      description: "Updated YAML workflow description.",
      key: workflowKey,
      name: `Workflow YAML ${timestamp}`,
    });
    let rerunPayload: Record<string, unknown> | null = null;
    let stepReplayPayload: Record<string, unknown> | null = null;
    let runPayload: Record<string, unknown> | null = null;

    await page.route("**/api/workflows/*/launches", async (route) => {
      const launchPayload = route.request().postDataJSON() as { parameters?: Record<string, unknown>; version?: number };
      runPayload = launchPayload.parameters ?? {};
      expect(launchPayload.parameters).toEqual({ ticker: "MSFT" });
      expect(typeof launchPayload.version).toBe("number");
      const workflowId = Number(route.request().url().match(/\/workflows\/(\d+)\/launches/)?.[1] ?? 0);
      await route.fulfill({
        body: JSON.stringify({
          ...buildRunCreated({
            createdAt: "2026-04-29T10:00:00Z",
            id: 8801,
            targetId: workflowId,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-workflow-yaml-8801",
          }),
        }),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/8801", async (route) => {
      await route.fulfill({
        body: JSON.stringify(
          buildRunDetail({
            finalOutput: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
            id: 8801,
            input: runPayload ?? {},
            memoryArtifacts: [
              {
                reportId: 9021,
                slug: "memory_msft_decision",
                name: "MSFT decision memory",
                status: "pending",
                createdAt: "2026-04-29T10:00:05Z",
                sourceGraphMetadata: { nodeId: "decision", nodeKind: "step", loopId: "review_loop", loopIteration: 2 },
              },
            ],
            steps: [
              buildRunStep({
                id: 880101,
                graphMetadata: {
                  nodeKind: "fanout",
                  fanoutId: "analyst_fanout",
                  sourceRefs: { branches: [] },
                },
                invocations: [
                  buildRunInvocation({
                    agentKey: agent.key,
                    agentVersion: agent.version,
                    graphMetadata: { nodeId: "market_analysis", nodeKind: "step", fanoutId: "analyst_fanout", branchId: "market" },
                    id: 8801001,
                    output: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
                    resolvedInput: runPayload ?? {},
                    runId: 8801,
                    runStepId: 880101,
                    traceSpanId: "span-workflow-yaml-1",
                  }),
                ],
                runId: 8801,
              }),
              buildRunStep({
                id: 880102,
                index: 2,
                invocations: [
                  buildRunInvocation({
                    agentKey: agent.key,
                    agentVersion: agent.version,
                    graphMetadata: { nodeId: "risk_review", nodeKind: "step", loopId: "review_loop", loopIteration: 1 },
                    id: 8801002,
                    output: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
                    resolvedInput: { ticker: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
                    runId: 8801,
                    runStepId: 880102,
                    slot: "decision",
                    stepIndex: 2,
                    traceSpanId: "span-workflow-yaml-2",
                  }),
                ],
                runId: 8801,
              }),
            ],
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-workflow-yaml-8801",
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.route("**/api/runs/8801/rerun-draft", async (route) => {
      await route.fulfill({
        body: JSON.stringify(
          buildRerunDraft({
            parameters: runPayload ?? {},
            sourceRunId: 8801,
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.route("**/api/runs/8801/reruns", async (route) => {
      rerunPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        body: JSON.stringify(
          buildRunCreated({
            id: 8803,
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-workflow-yaml-8803",
          }),
        ),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/8801/step-replay-draft?*", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("stepIndex")).toBe("1");
      await route.fulfill({
        body: JSON.stringify(
          buildStepReplayDraft({
            parameters: runPayload ?? {},
            replayStepIndex: 1,
            sourceRunId: 8801,
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.route("**/api/runs/8801/step-replays", async (route) => {
      stepReplayPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        body: JSON.stringify(
          buildRunCreated({
            id: 8802,
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-workflow-yaml-8802",
          }),
        ),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/8803", async (route) => {
      await route.fulfill({
        body: JSON.stringify(
          buildRunDetail({
            finalOutput: { summary: `Rerun workflow summary for ${String(rerunPayload?.parameters ? "TSLA" : "AAPL")}` },
            id: 8803,
            input: { ticker: "TSLA" },
            lineageRootRunId: 8801,
            sourceRunId: 8801,
            steps: [],
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            traceId: "trace-workflow-yaml-8803",
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.route("**/api/runs/8802", async (route) => {
      await route.fulfill({
        body: JSON.stringify(
          buildRunDetail({
            executedCostUsd: "0.00000000",
            executedTokens: 0,
            finalOutput: { summary: `Step replay workflow summary for ${String(stepReplayPayload?.parameters ? "NVDA" : "AAPL")}` },
            id: 8802,
            inheritedCostUsd: "0.01000000",
            inheritedTokens: 18,
            input: { ticker: "NVDA" },
            lineageRootRunId: 8801,
            replayStepIndex: 1,
            resumeStepIndex: 1,
            sourceRunId: 8801,
            steps: [
              buildRunStep({
                id: 880201,
                invocations: [
                  buildRunInvocation({
                    agentKey: agent.key,
                    agentVersion: agent.version,
                    id: 8802001,
                    output: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
                    outputOrigin: "copied",
                    resolvedInput: runPayload ?? {},
                    resolvedInputOrigin: "copied",
                    runId: 8802,
                    runStepId: 880201,
                    sourceInvocationId: 8801001,
                    traceSpanId: "span-workflow-yaml-1",
                  }),
                ],
                origin: "copied",
                runId: 8802,
                sourceRunId: 8801,
                sourceRunStepId: 880101,
                sourceStepIndex: 1,
              }),
            ],
            targetId: 1,
            targetKey: workflowKey,
            targetKind: "workflow",
            targetVersion: 1,
            totalCostUsd: "0.01000000",
            totalTokens: 18,
            traceId: "trace-workflow-yaml-8802",
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.goto("/workflows/new");
    await expectYamlOnlyEditor(page);
    await expect(page.getByTestId("workflow-run-panel")).toHaveCount(0);
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Saved baseline");
    await page.getByTestId("workflow-yaml-editor").fill(initialManifest);
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Unsaved changes");

    await page.getByTestId("workflow-validate-manifest").click();
    await expect(page.getByTestId("workflow-backend-validation-status")).toContainText(
      "Backend validation passed",
    );
    await expect(page.getByTestId("workflow-backend-validation-feedback")).toContainText(
      "No backend diagnostics",
    );
    await expect(page.getByTestId("workflow-compiled-preview").locator("textarea")).toHaveValue(
      /workflow_yaml_/,
    );
    await expect(page.getByTestId("workflow-run-input-preview").locator("textarea")).toHaveValue(
      /"ticker"/,
    );

    await Promise.all([
      page.waitForURL(/\/workflows\/\d+\/edit$/),
      page.getByTestId("workflow-save").click(),
    ]);
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Saved baseline");
    let workflowEditUrl = page.url();

    await page.goto("/workflows");
    await expect(page.getByTestId(`workflows-row-${workflowKey}`)).toContainText(
      "Reviews YAML-created workflow input.",
    );
    await page.getByTestId(`workflows-open-${workflowKey}`).click();
    await expect(page).toHaveURL(/\/workflows\/\d+\/edit$/);
    await expectYamlOnlyEditor(page);
    await expect(page.getByTestId("workflow-yaml-editor")).toHaveValue(initialManifest);

    await page.getByTestId("workflow-yaml-editor").fill(editedManifest);
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Unsaved changes");
    await page.getByTestId("workflow-save").click();
    await expect(page.getByText("Workflow manifest saved")).toBeVisible();
    await expect(page).toHaveURL(/\/workflows\/\d+\/edit$/);
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Saved baseline");
    await page.reload();
    await expect(page.getByTestId("workflow-yaml-editor")).toHaveValue(editedManifest);

    const invalidManifest = editedManifest.replace(`${agent.key}@1`, `missing_${agent.key}@1`);
    await page.getByTestId("workflow-yaml-editor").fill(invalidManifest);
    await page.getByTestId("workflow-validate-manifest").click();
    await expect(page.getByTestId("workflow-backend-validation-status")).toContainText(
      "Backend validation found errors",
    );
    const backendDiagnostic = page
      .getByTestId("workflow-backend-validation-feedback")
      .getByRole("button")
      .filter({ hasText: `missing_${agent.key}` })
      .first();
    await expect(backendDiagnostic).toBeVisible();
    await backendDiagnostic.click();
    await expect(page.getByTestId("workflow-yaml-editor")).toBeFocused();

    await page.getByTestId("workflow-yaml-editor").fill(editedManifest);
    await page.getByTestId("workflow-save").click();
    await expect(page.getByTestId("workflow-dirty-indicator")).toContainText("Saved baseline");
    workflowEditUrl = page.url();

    await page.goto(`${workflowEditUrl}#review`);
    await expect(page).toHaveURL(/\/workflows\/\d+\/edit#review$/);
    await expect(page.getByTestId("workflow-yaml-editor")).toHaveValue(editedManifest);
    await expect(page.getByTestId("workflow-run-panel")).toHaveCount(0);
    await expect(page.getByTestId("workflow-run-now")).toHaveCount(0);

    await page.goto("/workflows");
    await page.getByTestId(`workflows-run-${workflowKey}`).click();
    await expect(page).toHaveURL(/\/workflows\/\d+\/run$/);
    await expect(page.getByTestId("workflow-launch-page")).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/fork/i);
    await expect(page.getByTestId("workflow-launch-parameters-json").locator("textarea")).toHaveValue(
      /"ticker": "AAPL"/,
    );
    await page.getByTestId("workflow-launch-input-form").getByRole("textbox").fill("MSFT");
    await expect(page.getByTestId("workflow-launch-parameters-json").locator("textarea")).toHaveValue(
      /"ticker": "MSFT"/,
    );
    await page.getByTestId("workflow-launch-submit").click();
    await expect(page).toHaveURL(/\/runs\/8801$/);
    expect(runPayload).toEqual({ ticker: "MSFT" });
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-final-output")).toContainText(
      "Workflow summary for MSFT",
    );
    await expect(page.getByTestId("runs-trace-linkage")).toContainText("trace-workflow-yaml-8801");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("Fanout analyst_fanout");
    await expect(page.getByTestId("runs-graph-summary")).toContainText("Loop review_loop iteration 1");
    await expect(page.getByTestId("runs-memory-artifacts")).toContainText("MSFT decision memory");
    await expect(page.getByRole("link", { name: /open report/i })).toHaveAttribute("href", "/reports/memory_msft_decision");
    await expect(page.getByTestId("runs-detail-workflow-link")).toHaveAttribute("href", "/workflows/1");
    await expect(page.getByTestId("runs-detail-rerun")).toBeVisible();
    await page.getByTestId("runs-detail-rerun").click();
    await expect(page).toHaveURL(/\/runs\/8801\?rerun=1$/);
    await expect(page.getByRole("dialog", { name: /rerun draft/i })).toBeVisible();
    await page.getByLabel("Rerun parameters JSON").fill(JSON.stringify({ ticker: "TSLA" }, null, 2));
    await page.getByRole("button", { name: /^create rerun$/i }).click();
    await expect(page).toHaveURL(/\/runs\/8803$/);
    expect(rerunPayload).toEqual({ parameters: { ticker: "TSLA" } });
    await expect(page.getByTestId("runs-detail-page")).toContainText("Rerun workflow summary for TSLA");
    await expect(page.getByTestId("runs-lineage-summary")).toContainText("Run #8801");
    await page.goto("/runs/8801");
    await expect(page.getByTestId("runs-step-1-replay-entry")).toContainText("Replay from this succeeded step");
    await expect(page.getByTestId("runs-step-2-replay-entry")).toContainText("Replay from this succeeded step");
    await expect(page.locator("#step-1")).toBeVisible();

    await page.getByTestId("runs-step-1-replay-entry").getByRole("button", { name: /replay step/i }).click();
    await expect(page).toHaveURL(/\/runs\/8801\?stepReplay=1&stepIndex=1$/);
    await expect(page.getByRole("dialog", { name: /step replay draft/i })).toBeVisible();
    await page.getByLabel("Step replay parameters JSON").fill(JSON.stringify({ ticker: "NVDA" }, null, 2));
    await page.getByRole("button", { name: /^create step replay$/i }).click();
    await expect(page).toHaveURL(/\/runs\/8802$/);
    expect(stepReplayPayload).toEqual({ replayStepIndex: 1, parameters: { ticker: "NVDA" } });
    await expect(page.getByTestId("runs-detail-page")).toContainText("Step replay workflow summary for NVDA");
    await expect(page.getByTestId("runs-lineage-summary")).toContainText("Run #8801");
    await expect(page.getByTestId("runs-lineage-summary")).toContainText("Replay step");
    await expect(page.locator("body")).not.toContainText(/fork/i);

    expect(workflowEditUrl).toMatch(/\/workflows\/\d+\/edit$/);
  });
});
