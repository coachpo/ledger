import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { SkillRead } from "../src/lib/types/skill";

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

type McpServerRead = {
  id: number;
  key: string;
  version: number;
};

function readTickerFromPayload(payload: Record<string, unknown> | null): string {
  return typeof payload?.ticker === "string" ? payload.ticker : "AAPL";
}

async function createOutputSchema(
  request: APIRequestContext,
  key: string,
): Promise<OutputSchemaRead> {
  const response = await request.post(`${PLATFORM_API}/output-schemas`, {
    data: {
      builder: {
        allowAdditionalProperties: false,
        fields: [
          {
            name: "summary",
            required: true,
            schema: { kind: "string" },
          },
        ],
        kind: "object",
      },
      jsonSchema: {
        additionalProperties: false,
        properties: {
          summary: { type: "string" },
        },
        required: ["summary"],
        type: "object",
      },
      key,
      kind: "standalone",
      name: `Schema ${key}`,
    },
  });

  expect(response.ok()).toBeTruthy();
  const created = (await response.json()) as OutputSchemaRead;
  const activateResponse = await request.post(`${PLATFORM_API}/output-schemas/${created.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as OutputSchemaRead;
}

async function createModelConnection(
  request: APIRequestContext,
  key: string,
): Promise<ModelConnectionRead> {
  const response = await request.post(`${PLATFORM_API}/model-connections`, {
    data: {
      apiKey: "sk-playwright-agent-platform",
      baseUrl: "https://api.openai.com/v1",
      description: "Playwright-only agent-platform model connection.",
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

async function createAndActivateSkill(
  request: APIRequestContext,
  key: string,
): Promise<SkillRead> {
  const createResponse = await request.post(`${PLATFORM_API}/skills`, {
    data: {
      key,
      name: `Skill ${key}`,
      description: "Condenses responses.",
      toolDefinitions: [{ tool: "ledger.market_data.quote_lookup" }],
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const created = (await createResponse.json()) as SkillRead;

  const activateResponse = await request.post(`${PLATFORM_API}/skills/${created.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as SkillRead;
}

async function createAndActivateMcpServer(
  request: APIRequestContext,
  key: string,
): Promise<McpServerRead> {
  const createResponse = await request.post(`${PLATFORM_API}/mcp-servers`, {
    data: {
      key,
      name: `MCP ${key}`,
      description: "Serves external quote lookups.",
      transport: "stdio",
      command: "python3",
      args: ["-c", "print('ledger mcp stub')"],
      enabled: true,
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const created = (await createResponse.json()) as McpServerRead;

  const activateResponse = await request.post(`${PLATFORM_API}/mcp-servers/${created.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as McpServerRead;
}

async function expectLegacyAgentAuthoringAbsent(page: Page) {
  await expect(page.getByTestId("agents-editor")).toHaveCount(0);
  await expect(page.getByLabel("Input Schema JSON")).toHaveCount(0);
  await expect(page.getByLabel("Sample Input JSON")).toHaveCount(0);
  await expect(page.getByLabel("Skills")).toHaveCount(0);
  await expect(page.getByLabel("MCP Servers")).toHaveCount(0);
  await expect(page.getByTestId("agent-input-schema-raw-json")).toHaveCount(0);
  await expect(page.getByTestId("output-schema-add-field")).toHaveCount(0);
}

async function expectYamlOnlyAgentEditor(page: Page) {
  await expect(page.getByTestId("agent-yaml-editor-shell")).toBeVisible();
  await expect(page.getByTestId("agent-yaml-editor")).toBeVisible();
  await expect(page.getByTestId("agent-outline-rail")).toBeVisible();
  await expect(page.getByTestId("agent-inspector-shell")).toBeVisible();
  await expect(page.getByTestId("agents-validate-manifest")).toBeVisible();
  await expect(page.getByTestId("agents-save")).toBeVisible();
  await expect(page.getByRole("tab", { name: /configuration/i })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /^run$/i })).toHaveCount(0);
  await expect(page.getByLabel("Key")).toHaveCount(0);
  await expect(page.getByLabel("Name")).toHaveCount(0);
  await expect(page.getByLabel("Model Connection")).toHaveCount(0);
  await expect(page.getByLabel("System Prompt")).toHaveCount(0);
  await expectLegacyAgentAuthoringAbsent(page);
}

function agentManifest(options: {
  description: string;
  key: string;
  mcpServerRef: string;
  modelConnectionKey: string;
  name: string;
  outputSchemaRef: string;
  skillRef: string;
  systemPrompt: string;
}): string {
  return `apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: ${options.key}
  name: ${options.name}
  description: ${options.description}
spec:
  modelConnection: ${options.modelConnectionKey}
  systemPrompt: |
    ${options.systemPrompt}
  inputSchema:
    type: object
    properties:
      ticker:
        type: string
    required:
      - ticker
    additionalProperties: false
  outputSchema: ${options.outputSchemaRef}
  skills:
    - ${options.skillRef}
  mcpServers:
    - ${options.mcpServerRef}
  budgetUsd: "0.25"
`;
}

test.describe("Agent platform CRUD flows", () => {
  test("covers YAML-only agent authoring, duplicate behavior, and saved run launch", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const outputSchema = await createOutputSchema(request, `summary_schema_${timestamp}`);
    const modelConnection = await createModelConnection(request, `macro_model_${timestamp}`);
    const skillKey = `summarize_skill_${timestamp}`;
    const serverKey = `quotes_mcp_${timestamp}`;
    const agentKey = `macro_agent_${timestamp}`;
    const duplicateAgentKey = `macro_agent_copy_${timestamp}`;
    let createdRunPayload: Record<string, unknown> | null = null;
    let createdRunRequestUrl: string | null = null;
    const skill = await createAndActivateSkill(request, skillKey);
    const server = await createAndActivateMcpServer(request, serverKey);
    const initialManifest = agentManifest({
      description: "Tracks macro context.",
      key: agentKey,
      mcpServerRef: `${server.key}@${server.version}`,
      modelConnectionKey: modelConnection.key,
      name: `Macro Agent ${timestamp}`,
      outputSchemaRef: `${outputSchema.key}@${outputSchema.version}`,
      skillRef: `${skill.key}@${skill.version}`,
      systemPrompt: "Summarize macro context clearly.",
    });
    const duplicateManifest = agentManifest({
      description: "Tracks macro context as a duplicate.",
      key: duplicateAgentKey,
      mcpServerRef: `${server.key}@${server.version}`,
      modelConnectionKey: modelConnection.key,
      name: `Macro Agent ${timestamp} Copy`,
      outputSchemaRef: `${outputSchema.key}@${outputSchema.version}`,
      skillRef: `${skill.key}@${skill.version}`,
      systemPrompt: "Summarize macro context clearly.",
    });

    await page.route(/\/api\/skills(?:\?.*)?$/, async (route) => {
      await route.fulfill({
        body: JSON.stringify({ items: [skill] }),
        contentType: "application/json",
      });
    });

    await page.route("**/api/agents/*/runs?*", async (route) => {
      createdRunPayload = route.request().postDataJSON() as Record<string, unknown>;
      createdRunRequestUrl = route.request().url();
      const launchedAgentId = Number(route.request().url().match(/\/agents\/(\d+)\/runs/)?.[1] ?? 0);

      await route.fulfill({
        body: JSON.stringify({
          createdAt: "2026-04-26T12:00:00Z",
          id: 321,
          status: "running",
          targetId: launchedAgentId,
          targetKey: agentKey,
          targetKind: "agent",
          targetVersion: 1,
          traceId: "trace-321",
        }),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/321", async (route) => {
      const ticker = readTickerFromPayload(createdRunPayload);

      await route.fulfill({
        body: JSON.stringify({
          createdAt: "2026-04-26T12:00:00Z",
          error: null,
          finalOutput: { summary: `Agent summary for ${ticker}` },
          finishedAt: "2026-04-26T12:00:03Z",
          id: 321,
          input: createdRunPayload ?? {},
          perStepOutputs: {
            "1": [
              {
                agentId: 1,
                agentKey,
                agentVersion: 1,
                costUsd: "0.01000000",
                durationMs: 5,
                error: null,
                output: { summary: `Agent summary for ${ticker}` },
                outputSchemaId: outputSchema.id,
                outputSchemaVersion: outputSchema.version,
                resolvedInput: createdRunPayload ?? {},
                slot: "result",
                status: "succeeded",
                tokens: 18,
                traceSpanId: null,
              },
            ],
          },
          startedAt: "2026-04-26T12:00:01Z",
          status: "succeeded",
          targetId: 1,
          targetKey: agentKey,
          targetKind: "agent",
          targetVersion: 1,
          totalCostUsd: "0.01000000",
          totalTokens: 18,
          traceId: "trace-321",
          updatedAt: "2026-04-26T12:00:03Z",
        }),
        contentType: "application/json",
      });
    });

    await page.goto(`/skills/${skill.id}/edit`);
    await expect(page).toHaveURL(new RegExp(`/skills/${skill.id}/edit$`));

    await page.goto(`/mcp-servers/${server.id}/edit`);
    await expect(page).toHaveURL(new RegExp(`/mcp-servers/${server.id}/edit$`));
    await page.getByTestId("mcp-server-test-connection").click();
    await expect(page.getByTestId("mcp-server-connection-feedback")).toBeVisible();

    await page.goto("/agents/new");
    await expectYamlOnlyAgentEditor(page);
    await expect(page.getByTestId("agent-run-unavailable")).toBeVisible();
    await page.getByTestId("agent-yaml-editor").fill(initialManifest);
    await page.getByTestId("agents-validate-manifest").click();
    await expect(page.getByTestId("agent-backend-validation-status")).toContainText("Backend validation passed");
    await expect(page.getByTestId("agent-compiled-preview").locator("textarea")).toHaveValue(/macro_agent_/);
    await expect(page.getByTestId("agent-run-input-preview").locator("textarea")).toHaveValue(/"ticker"/);

    await page.getByTestId("agents-save").click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);
    const agentEditUrl = page.url();
    await expectYamlOnlyAgentEditor(page);
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(initialManifest);

    await expect(page.getByRole("tab", { name: /test panel/i })).toHaveCount(0);
    await expect(page.getByLabel("Sample Input JSON")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /^launch run$/i })).toBeVisible();
    await expect(page.getByTestId("agent-run-panel-input-form")).toBeVisible();
    await expect(page.getByTestId("agent-run-panel-input-raw-json")).toBeVisible();
    await expect(page.getByTestId("agent-test-panel-result")).toHaveCount(0);
    await expect(page.getByLabel("Exact raw result JSON")).toHaveCount(0);
    await expect(page.getByTestId("agent-run-panel-input-raw-json").locator("textarea")).toHaveValue(
      /"ticker": "example"/,
    );
    await page.getByTestId("agent-run-panel-input-form").getByRole("textbox").fill("MSFT");
    await expect(page.getByTestId("agent-run-panel-input-raw-json").locator("textarea")).toHaveValue(
      /"ticker": "MSFT"/,
    );
    await page.getByTestId("agent-run-panel-launch").click();
    await expect(page.getByText("Agent run started")).toBeVisible();
    await expect(page).toHaveURL(/\/runs\/321$/);
    expect(createdRunPayload).toEqual({ ticker: "MSFT" });
    expect(createdRunRequestUrl).toMatch(/version=1/);
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-status")).toContainText("succeeded");
    await expect(page.getByTestId("runs-detail-page")).toContainText("MSFT");
    await expect(page.getByTestId("runs-detail-final-output")).toContainText("Agent summary for MSFT");

    await page.goto(agentEditUrl);
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);
    await page.getByTestId("agents-duplicate").click();
    await expect(page).toHaveURL(/\/agents\/new\?duplicateFrom=\d+$/);
    await expectYamlOnlyAgentEditor(page);
    await expect(page.getByText("Duplicate source")).toBeVisible();
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(/key: new_agent/);
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(
      new RegExp(`name: Macro Agent ${timestamp} Copy`),
    );
    await page.getByTestId("agent-yaml-editor").fill(duplicateManifest);
    await page.getByTestId("agents-save").click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);

    await page.getByTestId("agents-archive").click();
    await expect(page.getByText("Agent archived")).toBeVisible();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.getByTestId(`agents-row-${duplicateAgentKey}`)).toBeVisible();
    await expect(page.getByTestId(`agents-archive-${duplicateAgentKey}`)).toHaveCount(0);
  });
});
