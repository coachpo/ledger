import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const PLATFORM_API = "http://127.0.0.1:8001/api";
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
const NOTE_SCHEMA_KEY = "stock_analysis_note";
const DECISION_SCHEMA_KEY = "trading_decision";
const SKILL_KEY = "stock_analysis_tools";
const MCP_SERVER_KEY = "stock_analysis_data";

type ResourceRead = {
  id: number;
  key: string;
  name: string;
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




async function expectOk(response: Awaited<ReturnType<APIRequestContext["get"]>>, label: string) {
  expect(response.ok(), `${label} failed: ${await response.text()}`).toBeTruthy();
}

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
  return items
    .filter((item) => item.key === key)
    .sort((left, right) => right.version - left.version)[0] ?? null;
}

async function createViaApi<T>(request: APIRequestContext, path: string, data: unknown): Promise<T> {
  const response = await request.post(`${PLATFORM_API}/${path}`, { data });
  await expectOk(response, `POST ${path}`);
  return (await response.json()) as T;
}

function toAgentName(key: string): string {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

async function ensureSkill(request: APIRequestContext): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "skills", SKILL_KEY);
  if (existing) {
    return existing;
  }

  return createViaApi<ResourceRead>(request, "skills", {
    key: SKILL_KEY,
    name: "Stock Analysis Tools",
    description: "Stub-only stock-analysis skill wiring.",
    toolDefinitions: [{ tool: "ledger.market_data.quote_lookup" }],
  });
}

async function ensureMcpServer(request: APIRequestContext): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "mcp-servers", MCP_SERVER_KEY);
  if (existing) {
    return existing;
  }

  return createViaApi<ResourceRead>(request, "mcp-servers", {
    key: MCP_SERVER_KEY,
    name: "Stock Analysis Data",
    description: "Stub-only MCP placeholder for stock-analysis.",
    transport: "stdio",
    command: "definitely_missing_stock_analysis_mcp_binary",
    enabled: true,
  });
}

async function ensureNoteSchema(request: APIRequestContext): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "output-schemas", NOTE_SCHEMA_KEY);
  if (existing) {
    return existing;
  }

  return createViaApi<ResourceRead>(request, "output-schemas", {
    key: NOTE_SCHEMA_KEY,
    kind: "standalone",
    name: "Stock Analysis Note",
    description: "Deterministic stock-analysis note schema.",
    jsonSchema: noteSchema(),
  });
}

async function ensureTradingDecisionSchema(
  page: Page,
  request: APIRequestContext,
): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "output-schemas", DECISION_SCHEMA_KEY);
  if (existing) {
    return existing;
  }

  await page.goto("/output-schemas/new");
  await page.getByLabel("Key").fill(DECISION_SCHEMA_KEY);
  await page.getByLabel("Name").fill("Trading Decision");
  await page.getByLabel("Description").fill("Deterministic TradingDecision output contract.");
  await page.getByRole("tab", { name: "JSON Schema" }).click();
  await page
    .getByTestId("output-schema-json-editor")
    .fill(JSON.stringify(tradingDecisionSchema(), null, 2));
  await page.getByTestId("output-schemas-save").click();
  await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);

  const created = await findLatestByKey<ResourceRead>(request, "output-schemas", DECISION_SCHEMA_KEY);
  expect(created).not.toBeNull();
  return created as ResourceRead;
}

async function ensureStepOneAgents(
  request: APIRequestContext,
  noteSchemaResource: ResourceRead,
  skill: ResourceRead,
  mcpServer: ResourceRead,
): Promise<Record<string, ResourceRead>> {
  const agents: Partial<Record<string, ResourceRead>> = {};

  for (const key of STEP_ONE_AGENT_KEYS) {
    const existing = await findLatestByKey<ResourceRead>(request, "agents", key);
    if (existing) {
      agents[key] = existing;
      continue;
    }

    agents[key] = await createViaApi<ResourceRead>(request, "agents", {
      key,
      name: toAgentName(key),
      description: `Stub stock-analysis agent for ${key}.`,
      model: "openai:gpt-5.4-mini",
      systemPrompt: `Return the deterministic stub analysis for ${key}.`,
      inputSchema: workflowInputSchema(),
      outputSchemaKey: noteSchemaResource.key,
      outputSchemaVersion: noteSchemaResource.version,
      skills: [{ skillKey: skill.key, skillVersion: skill.version }],
      mcpServers: [{ mcpServerKey: mcpServer.key, mcpServerVersion: mcpServer.version }],
      budgetUsd: "0.05000000",
      streaming: false,
    });
  }

  return agents as Record<string, ResourceRead>;
}

async function selectOption(page: Page, label: string, optionName: string) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("listbox").waitFor({ state: "visible" });
  const normalizedTarget = optionName.replace(/\s+/g, " ").trim();
  await page.waitForFunction(
    (target) =>
      Array.from(document.querySelectorAll('[role="option"]')).some((element) =>
        element.textContent?.replace(/\s+/g, " ").trim().includes(target),
      ),
    normalizedTarget,
  );
  const optionTexts = await page.getByRole("option").allTextContents();
  const optionIndex = optionTexts.findIndex((text) =>
    text.replace(/\s+/g, " ").trim().includes(normalizedTarget),
  );

  if (optionIndex < 0) {
    throw new Error(`Option not found: ${optionName}`);
  }

  const selectedText = await page.getByRole("option").nth(optionIndex).innerText();
  await page.getByRole("option").nth(optionIndex).click();
  return selectedText;
}

async function ensureSynthesizerAgent(
  page: Page,
  request: APIRequestContext,
  decisionSchema: ResourceRead,
  skill: ResourceRead,
  mcpServer: ResourceRead,
): Promise<ResourceRead> {
  const existing = await findLatestByKey<ResourceRead>(request, "agents", SYNTHESIZER_KEY);
  if (existing) {
    return existing;
  }

  await page.goto("/agents/new");
  await page.getByLabel("Key").fill(SYNTHESIZER_KEY);
  await page.getByLabel("Name").fill("Decision Synthesizer");
  await page.getByLabel("Model").fill("openai:gpt-5.4-mini");
  await page
    .getByLabel("System Prompt")
    .fill("Combine the wired analyses into a deterministic TradingDecision.");
  await page
    .getByLabel("Description")
    .fill("Combines the stub analyses into a TradingDecision.");
  await page
    .getByLabel("Input Schema JSON")
    .fill(JSON.stringify(synthesizerInputSchema(), null, 2));
  await selectOption(
    page,
    "Output Schema",
    `Trading Decision (${decisionSchema.key}@${decisionSchema.version})`,
  );
  await page.getByLabel("Skills").fill(`${skill.key}@${skill.version}`);
  await page.getByLabel("MCP Servers").fill(`${mcpServer.key}@${mcpServer.version}`);
  await page.getByLabel("Budget USD").fill("0.10000000");
  await page.getByRole("button", { name: /save agent/i }).click();
  await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);

  const created = await findLatestByKey<ResourceRead>(request, "agents", SYNTHESIZER_KEY);
  expect(created).not.toBeNull();
  return created as ResourceRead;
}

async function configureStepAgent(
  page: Page,
  heading: string,
  agent: ResourceRead,
  index: number,
) {
  const selectedAgentText = await selectOption(page, `${heading} agent`, agent.key);
  const selectedVersion = selectedAgentText.match(/@(\d+)/)?.[1] ?? String(agent.version);
  await page.getByLabel(`${heading} version`).fill(selectedVersion);
  await page.getByLabel(`${heading} slot`).fill(agent.key);
  await page.getByLabel("ticker source").nth(index).click();
  await page.getByRole("option", { name: "Workflow input" }).click();
  await page.getByLabel("horizon_days source").nth(index).click();
  await page.getByRole("option", { name: "Workflow input" }).click();
}

async function wireOutputField(page: Page, fieldName: string, slot: string) {
  await selectOption(page, `${fieldName} source`, "Previous step slot");
  await selectOption(page, `${fieldName} slot`, slot);
}

test.describe.configure({ mode: "serial" });

test.describe("stock-analysis stub proof", () => {
  test("broken stock-analysis output wiring blocks workflow save", async ({ page }) => {
    const workflowKey = `stock_analysis_invalid_${Date.now()}`;

    await page.goto("/workflows/new");
    await page.getByLabel("Workflow Key").fill(workflowKey);
    await page.getByLabel("Workflow Name").fill("Stock Analysis Invalid");
    await page
      .getByLabel("Input Schema JSON")
      .fill(JSON.stringify(workflowInputSchema(), null, 2));
    await page.getByTestId("workflow-wizard-next").click();
    await page.getByTestId("workflow-wizard-next").click();
    await page.getByTestId("workflow-wizard-next").click();

    await page.getByTestId("workflow-save").click();
    await expect(page.getByTestId("workflow-validation-feedback")).toContainText(
      "steps[0].agents[0].agentKey: Select an agent",
    );
    await expect(page).toHaveURL(/\/workflows\/new$/);
  });

  test("creates the stock-analysis stub resources and runs NVDA through the UI", async ({
    page,
    request,
  }) => {
    const noteSchemaResource = await ensureNoteSchema(request);
    const skill = await ensureSkill(request);
    const mcpServer = await ensureMcpServer(request);
    const decisionSchema = await ensureTradingDecisionSchema(page, request);
    const stepAgents = await ensureStepOneAgents(request, noteSchemaResource, skill, mcpServer);
    const synthesizer = await ensureSynthesizerAgent(page, request, decisionSchema, skill, mcpServer);
    const workflowKey = `stock_analysis_run_${Date.now()}`;

    await page.goto("/workflows/new");
    await page.getByLabel("Workflow Key").fill(workflowKey);
    await page.getByLabel("Workflow Name").fill("Stock Analysis");
    await page
      .getByLabel("Input Schema JSON")
      .fill(JSON.stringify(workflowInputSchema(), null, 2));
    await page.getByTestId("workflow-wizard-next").click();

    for (let index = 0; index < STEP_ONE_AGENT_KEYS.length - 1; index += 1) {
      await page.getByRole("button", { name: /add agent/i }).click();
    }

    for (const [index, key] of STEP_ONE_AGENT_KEYS.entries()) {
      await configureStepAgent(page, `Step 1 Agent ${index + 1}`, stepAgents[key], index);
    }

    await page.getByTestId("workflow-wizard-next").click();
    await page.getByRole("button", { name: /switch to output agent/i }).click();
    const selectedOutputAgentText = await selectOption(page, "Output agent", synthesizer.key);
    const selectedOutputVersion = selectedOutputAgentText.match(/@(\d+)/)?.[1] ?? String(synthesizer.version);
    await page.getByLabel("Output agent version").fill(selectedOutputVersion);
    for (const key of STEP_ONE_AGENT_KEYS) {
      await wireOutputField(page, key, key);
    }
    await page.getByTestId("workflow-wizard-next").click();

    await page
      .getByLabel("Run Input JSON")
      .fill(JSON.stringify({ ticker: "NVDA", horizon_days: 30 }, null, 2));

    await page.getByTestId("workflow-save").click();
    await expect(page).toHaveURL(/\/workflows\/\d+\/edit$/);

    await page.getByTestId("workflow-run-now").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
    await expect(page.getByTestId("runs-detail-status")).toContainText(/succeeded/i);

    await expect(page.getByTestId("runs-trace-linkage")).toContainText(/[0-9a-f]{32}/);
    await expect(page.getByTestId("runs-trace-linkage")).toContainText(/Span id: [0-9a-f]{16}/);
    await expect(page.getByTestId("runs-trace-linkage")).toContainText("step 1 / financials_analyst");
    await expect(page.getByTestId("runs-trace-linkage")).toContainText("step 2 / final_output");

    const finalOutput = JSON.parse(await page.getByTestId("runs-detail-final-output").innerText()) as {
      action: string;
      confidence: number;
      rationale: string;
      price_targets: number[];
      risks: string[];
    };

    expect(finalOutput.action).toBe("buy");
    expect(finalOutput.confidence).toBeGreaterThan(0);
    expect(finalOutput.price_targets).toHaveLength(2);
    expect(finalOutput.rationale).toContain("NVDA");
    expect(finalOutput.risks.length).toBeGreaterThan(0);
  });
});
