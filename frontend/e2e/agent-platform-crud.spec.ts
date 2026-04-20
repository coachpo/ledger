import { expect, test, type APIRequestContext } from "@playwright/test";

const PLATFORM_API = "http://127.0.0.1:8001/api";

type OutputSchemaRead = {
  id: number;
  key: string;
  version: number;
};

type SkillRead = {
  id: number;
  key: string;
};

type McpServerRead = {
  id: number;
  key: string;
};

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
  return (await response.json()) as OutputSchemaRead;
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
      command: `definitely_missing_mcp_binary_${Date.now()}`,
      enabled: true,
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const created = (await createResponse.json()) as McpServerRead;

  const activateResponse = await request.post(`${PLATFORM_API}/mcp-servers/${created.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as McpServerRead;
}

test.describe("Agent platform CRUD flows", () => {
  test("covers lifecycle actions, duplicate behavior, and the agent test panel", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const outputSchema = await createOutputSchema(request, `summary_schema_${timestamp}`);
    const skillKey = `summarize_skill_${timestamp}`;
    const serverKey = `quotes_mcp_${timestamp}`;
    const agentKey = `macro_agent_${timestamp}`;
    const duplicateAgentKey = `macro_agent_copy_${timestamp}`;
    await createAndActivateSkill(request, skillKey);
    await createAndActivateMcpServer(request, serverKey);

    await page.goto("/skills");
    await expect(page.getByTestId(`skills-row-${skillKey}`)).toContainText(/published/i);
    await page.getByTestId(`skills-open-${skillKey}`).click();
    await expect(page).toHaveURL(/\/skills\/\d+\/edit$/);

    await page.goto("/mcp-servers");
    await expect(page.getByTestId(`mcp-servers-row-${serverKey}`)).toContainText(/published/i);
    await page.getByTestId(`mcp-servers-open-${serverKey}`).click();
    await expect(page).toHaveURL(/\/mcp-servers\/\d+\/edit$/);
    await page.getByTestId("mcp-server-test-connection").click();
    await expect(page.getByTestId("mcp-server-connection-feedback")).toBeVisible();

    await page.goto("/agents/new");
    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page.getByText("Key is required.")).toBeVisible();

    await page.getByLabel("Key").fill(agentKey);
    await page.getByLabel("Name").fill(`Macro Agent ${timestamp}`);
    await page.getByLabel("Model").fill("openai:gpt-5.4-mini");
    await page.getByLabel("System Prompt").fill("Summarize macro context clearly.");
    await page.getByLabel("Description").fill("Tracks macro context.");
    await page.getByLabel("Input Schema JSON").fill('{"type":"object","properties":{"ticker":{"type":"string"}},"required":["ticker"]}');
    await page.getByTestId("agent-output-schema-select").click();
    await page.getByText(`Schema ${outputSchema.key} (${outputSchema.key}@${outputSchema.version})`).click();
    await page.getByLabel("Skills").fill(`${skillKey}@1`);
    await page.getByLabel("MCP Servers").fill(`${serverKey}@1`);
    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);

    await page.getByRole("tab", { name: /test panel/i }).click();
    await page.getByTestId("agent-test-panel-run").click();
    await expect(page.getByTestId("agent-test-panel-result")).toBeVisible();
    await expect(page.getByTestId("agent-test-panel-result")).toContainText(/macro_agent_/i);

    await page.getByTestId("agents-duplicate").click();
    await expect(page).toHaveURL(/\/agents\/new\?duplicateFrom=\d+$/);
    await expect(page.getByRole("heading", { name: /duplicate agent/i })).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue(`Macro Agent ${timestamp} Copy`);
    await page.getByLabel("Key").fill(duplicateAgentKey);
    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);
    await page.getByTestId("agents-archive").click();
    await expect(page.getByText("Agent archived")).toBeVisible();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.getByTestId(`agents-row-${duplicateAgentKey}`)).toHaveCount(0);
  });
});
