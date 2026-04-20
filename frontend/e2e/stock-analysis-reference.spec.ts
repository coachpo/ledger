import { expect, test, type APIRequestContext } from "@playwright/test";

const PLATFORM_API = "http://127.0.0.1:8001/api";
const V1_API = "http://127.0.0.1:8001/api/v1";
const STEP_ONE_AGENT_KEYS = [
  "financials_analyst",
  "news_analyst",
  "market_analyst",
  "industry_analyst",
  "economy_analyst",
  "price_analyst",
  "position_reader",
  "history_reader",
] as const;
const SYNTHESIZER_KEY = "decision_synthesizer";
const MCP_COMMAND = "python3 -m app.agents.mcp.stock_analysis_reference_server";

type ResourceRead = {
  id: number;
  key: string;
  version: number;
  status?: string;
  name: string;
};

type WorkflowRead = {
  id: number;
  key: string;
  version: number;
};

function workflowInputSchema() {
  return {
    type: "object",
    properties: {
      ticker: { type: "string" },
      horizon_days: { type: "integer" },
    },
    required: ["ticker", "horizon_days"],
    additionalProperties: false,
  };
}

function noteSchema() {
  return {
    type: "object",
    properties: {
      summary: { type: "string" },
      signal: { type: "string" },
    },
    required: ["summary", "signal"],
    additionalProperties: false,
  };
}

function tradingDecisionSchema() {
  return {
    type: "object",
    properties: {
      action: { type: "string", enum: ["buy", "sell", "hold"] },
      confidence: { type: "number" },
      rationale: { type: "string" },
      price_targets: { type: "array", items: { type: "number" } },
      risks: { type: "array", items: { type: "string" } },
    },
    required: ["action", "confidence", "rationale", "price_targets", "risks"],
    additionalProperties: false,
  };
}

function synthesizerInputSchema() {
  return {
    type: "object",
    properties: Object.fromEntries(STEP_ONE_AGENT_KEYS.map((key) => [key, noteSchema()])),
    required: [...STEP_ONE_AGENT_KEYS],
    additionalProperties: false,
  };
}

async function expectOk(response: ResponseLike, label: string) {
  expect(response.ok(), `${label} failed: ${await response.text()}`).toBeTruthy();
}

type ResponseLike = Awaited<ReturnType<APIRequestContext["get"]>>;

async function listItems<T extends { key: string }>(request: APIRequestContext, path: string): Promise<T[]> {
  const response = await request.get(`${PLATFORM_API}/${path}`);
  await expectOk(response, `GET ${path}`);
  return ((await response.json()) as { items: T[] }).items;
}

async function findLatestByKey<T extends { key: string; version: number }>(
  request: APIRequestContext,
  path: string,
  key: string,
): Promise<T | null> {
  const items = await listItems<T>(request, path);
  return items.find((item) => item.key === key) ?? null;
}

async function postJson<T>(request: APIRequestContext, url: string, data: unknown): Promise<T> {
  const response = await request.post(url, { data });
  await expectOk(response, `POST ${url}`);
  return (await response.json()) as T;
}

async function waitForRunToFinish(
  request: APIRequestContext,
  runId: number,
  expectedStatus: "succeeded" | "failed",
) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await request.get(`${PLATFORM_API}/runs/${runId}`);
    await expectOk(response, `GET runs/${runId}`);
    const body = (await response.json()) as { status: string };
    if (body.status === expectedStatus) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Run ${runId} did not reach ${expectedStatus} in time.`);
}

async function createAndActivateOutputSchema(
  request: APIRequestContext,
  key: string,
  name: string,
  jsonSchema: unknown,
): Promise<ResourceRead> {
  const draft = await postJson<ResourceRead>(request, `${PLATFORM_API}/output-schemas`, {
    key,
    kind: "standalone",
    name,
    description: `${name} for the real stock-analysis reference flow.`,
    jsonSchema,
  });
  return postJson<ResourceRead>(request, `${PLATFORM_API}/output-schemas/${draft.id}/activate`, {});
}

async function createAndActivateSkill(
  request: APIRequestContext,
  key: string,
): Promise<ResourceRead> {
  const draft = await postJson<ResourceRead>(request, `${PLATFORM_API}/skills`, {
    key,
    name: "Stock Analysis Tools",
    description: "Real stock-analysis skill wiring.",
    toolDefinitions: [
      { tool: "ledger.stock_analysis.market_snapshot" },
      { tool: "ledger.stock_analysis.price_history" },
      { tool: "ledger.stock_analysis.position_inventory" },
      { tool: "ledger.stock_analysis.report_lookup" },
      { tool: "ledger.stock_analysis.market_context" },
    ],
  });
  return postJson<ResourceRead>(request, `${PLATFORM_API}/skills/${draft.id}/activate`, {});
}

async function createAndActivateMcpServer(
  request: APIRequestContext,
  key: string,
): Promise<ResourceRead> {
  const draft = await postJson<ResourceRead>(request, `${PLATFORM_API}/mcp-servers`, {
    key,
    name: "Stock Analysis Reference MCP",
    description: "App-side reference MCP for the real stock-analysis flow.",
    transport: "stdio",
    command: MCP_COMMAND,
    enabled: true,
  });
  return postJson<ResourceRead>(request, `${PLATFORM_API}/mcp-servers/${draft.id}/activate`, {});
}

function toAgentName(key: string): string {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

async function upsertAgent(
  request: APIRequestContext,
  payload: Record<string, unknown>,
): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "agents", String(payload.key));
  if (!existing) {
    return postJson<ResourceRead>(request, `${PLATFORM_API}/agents`, payload);
  }
  const { key: _key, ...updatePayload } = payload;
  return postJson<ResourceRead>(request, `${PLATFORM_API}/agents/${existing.id}`, updatePayload);
}

function stepOneAgentPayload(
  key: string,
  noteSchemaResource: ResourceRead,
  skill: ResourceRead,
  mcpServer: ResourceRead,
) {
  return {
    key,
    name: toAgentName(key),
    description: `Real stock-analysis reference agent for ${key}.`,
    model: "openai:gpt-5.4-mini",
    systemPrompt: `Use the real Ledger stock-analysis reference path for ${key}.`,
    inputSchema: workflowInputSchema(),
    outputSchemaKey: noteSchemaResource.key,
    outputSchemaVersion: noteSchemaResource.version,
    skills: [{ skillKey: skill.key, skillVersion: skill.version }],
    mcpServers: [{ mcpServerKey: mcpServer.key, mcpServerVersion: mcpServer.version }],
    budgetUsd: key === "price_analyst" ? "0.02000000" : "0.05000000",
    streaming: false,
  };
}

function synthesizerPayload(
  decisionSchema: ResourceRead,
  skill: ResourceRead,
  mcpServer: ResourceRead,
) {
  return {
    key: SYNTHESIZER_KEY,
    name: "Decision Synthesizer",
    description: "Combines the real stock-analysis notes into a TradingDecision.",
    model: "openai:gpt-5.4-mini",
    systemPrompt: "Combine the real stock-analysis notes into a TradingDecision.",
    inputSchema: synthesizerInputSchema(),
    outputSchemaKey: decisionSchema.key,
    outputSchemaVersion: decisionSchema.version,
    skills: [{ skillKey: skill.key, skillVersion: skill.version }],
    mcpServers: [{ mcpServerKey: mcpServer.key, mcpServerVersion: mcpServer.version }],
    budgetUsd: "0.10000000",
    streaming: false,
  };
}

function workflowPayload(
  workflowKey: string,
): Record<string, unknown> {
  return {
    key: workflowKey,
    name: "Stock Analysis Reference",
    description: "Real stock-analysis reference workflow.",
    inputSchema: workflowInputSchema(),
    steps: [
      {
        index: 1,
        agents: STEP_ONE_AGENT_KEYS.map((key) => ({
          agentKey: key,
          slot: key,
          wiring: {
            ticker: { from: "input", path: "ticker" },
            horizon_days: { from: "input", path: "horizon_days" },
          },
        })),
      },
    ],
    outputSpec: {
      kind: "agent",
      agentKey: SYNTHESIZER_KEY,
      wiring: Object.fromEntries(
        STEP_ONE_AGENT_KEYS.map((key) => [key, { from: "step", stepIndex: 1, slot: key }]),
      ),
    },
  };
}

test("runs the real stock-analysis reference workflow through the UI", async ({ page, request }) => {
  test.setTimeout(90_000);

  const suffix = `${Date.now()}`;
  const noteSchemaResource = await createAndActivateOutputSchema(
    request,
    `stock_analysis_note_${suffix}`,
    "Stock Analysis Note",
    noteSchema(),
  );
  const decisionSchema = await createAndActivateOutputSchema(
    request,
    `trading_decision_${suffix}`,
    "Trading Decision",
    tradingDecisionSchema(),
  );
  const skill = await createAndActivateSkill(request, `stock_analysis_tools_${suffix}`);
  const mcpServer = await createAndActivateMcpServer(request, `stock_analysis_data_${suffix}`);

  for (const key of STEP_ONE_AGENT_KEYS) {
    await upsertAgent(request, stepOneAgentPayload(key, noteSchemaResource, skill, mcpServer));
  }
  await upsertAgent(request, synthesizerPayload(decisionSchema, skill, mcpServer));

  const portfolioSlug = `stock_analysis_reference_${suffix}`;
  const reportSlug = `nvda_reference_report_${suffix}`;
  const portfolio = await postJson<{ id: number }>(request, `${V1_API}/portfolios`, {
    name: "Stock Analysis Reference",
    slug: portfolioSlug,
    description: "Reference portfolio for the real stock-analysis browser proof.",
    baseCurrency: "USD",
  });
  await postJson(request, `${V1_API}/portfolios/${portfolio.id}/positions`, {
    symbol: "NVDA",
    name: "NVIDIA Corporation",
    quantity: "12.00000000",
    averageCost: "101.50000000",
  });
  await postJson(request, `${V1_API}/reports`, {
    name: reportSlug,
    slug: reportSlug,
    source: "external",
    content: "# NVDA reference\n\nRevenue acceleration remains intact.",
    metadata: {
      tags: ["news", "earnings"],
      analysis: { ticker: "NVDA", reviewType: "fundamental" },
    },
  });

  const workflow = await postJson<WorkflowRead>(
    request,
    `${PLATFORM_API}/workflows`,
    workflowPayload(`stock_analysis_reference_${suffix}`),
  );
  const run = await postJson<{ id: number }>(
    request,
    `${PLATFORM_API}/workflows/${workflow.id}/runs`,
    { ticker: "NVDA", horizon_days: 30 },
  );
  await waitForRunToFinish(request, run.id, "succeeded");

  await page.goto(`/runs/${run.id}`);
  await expect(page.getByTestId("runs-detail-status")).toContainText(/succeeded/i, {
    timeout: 60000,
  });

  const finalOutput = JSON.parse(await page.getByTestId("runs-detail-final-output").innerText()) as {
    action: string;
    rationale: string;
  };

  expect(finalOutput.action).toBe("buy");
  expect(finalOutput.rationale).toContain(portfolioSlug);
  expect(finalOutput.rationale).toContain(reportSlug);
  expect(finalOutput.rationale).not.toContain("stub summary");
  await expect(page.getByTestId("runs-trace-linkage")).toContainText(/[0-9a-f]{32}/);
  await expect(page.getByTestId("runs-trace-linkage")).toContainText(/Span id: [0-9a-f]{16}/);
  await expect(page.getByTestId("runs-trace-linkage")).toContainText("step 1 / position_reader");
  await expect(page.getByTestId("runs-trace-linkage")).toContainText("step 2 / final_output");
});
