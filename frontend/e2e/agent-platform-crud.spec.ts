import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

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

function cardByHeading(page: Page, heading: RegExp): Locator {
  return page
    .getByRole("heading", { name: heading })
    .locator("xpath=ancestor::*[@data-slot='card'][1]");
}

async function expectLegacyAgentAuthoringAbsent(page: Page) {
  await expect(page.getByLabel("Input Schema JSON")).toHaveCount(0);
  await expect(page.getByLabel("Sample Input JSON")).toHaveCount(0);
  await expect(page.getByLabel("Skills")).toHaveCount(0);
  await expect(page.getByLabel("MCP Servers")).toHaveCount(0);
}

test.describe("Agent platform CRUD flows", () => {
  test("covers schema transparency, duplicate behavior, and the structured agent test panel", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const outputSchema = await createOutputSchema(request, `summary_schema_${timestamp}`);
    const skillKey = `summarize_skill_${timestamp}`;
    const serverKey = `quotes_mcp_${timestamp}`;
    const agentKey = `macro_agent_${timestamp}`;
    const duplicateAgentKey = `macro_agent_copy_${timestamp}`;
    const skill = await createAndActivateSkill(request, skillKey);
    const server = await createAndActivateMcpServer(request, serverKey);

    await page.goto(`/skills/${skill.id}/edit`);
    await expect(page).toHaveURL(new RegExp(`/skills/${skill.id}/edit$`));

    await page.goto(`/mcp-servers/${server.id}/edit`);
    await expect(page).toHaveURL(new RegExp(`/mcp-servers/${server.id}/edit$`));
    await page.getByTestId("mcp-server-test-connection").click();
    await expect(page.getByTestId("mcp-server-connection-feedback")).toBeVisible();

    await page.goto("/agents/new");
    await expect(page.getByTestId("agents-editor")).toBeVisible();
    await expectLegacyAgentAuthoringAbsent(page);
    await expect(page.getByRole("heading", { name: /^Input schema$/i })).toBeVisible();
    await expect(page.getByTestId("agent-input-schema-raw-json")).toBeVisible();
    await expect(page.getByTestId("agent-input-schema-preview")).toBeVisible();
    await expect(page.getByRole("heading", { name: /output schema binding/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /skill bindings/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /mcp server bindings/i })).toBeVisible();

    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page.getByText("Key is required.")).toBeVisible();

    await page.getByLabel("Key").fill(agentKey);
    await page.getByLabel("Name").fill(`Macro Agent ${timestamp}`);
    await page.getByLabel("Model Connection").click();
    await page.getByRole("option").filter({ hasText: / · / }).first().click();
    await page.getByLabel("System Prompt").fill("Summarize macro context clearly.");
    await page.getByLabel("Description").fill("Tracks macro context.");

    await page.getByTestId("output-schema-add-field").click();
    await page.getByTestId("output-schema-field-name-0").fill("ticker");
    await expect(
      cardByHeading(page, /exact raw schema json/i).getByRole("textbox", {
        name: /exact raw schema json/i,
      }),
    ).toHaveValue(/"ticker"/);
    await expect(cardByHeading(page, /sample input companion/i)).toContainText("ticker");

    const outputSchemaCard = cardByHeading(page, /output schema binding/i);
    await outputSchemaCard.getByRole("combobox").first().click();
    await page.getByText(`Schema ${outputSchema.key}`, { exact: true }).click();

    const skillBindingsCard = cardByHeading(page, /skill bindings/i);
    await skillBindingsCard.getByRole("button", { name: /add skill binding/i }).click();
    await skillBindingsCard.getByRole("combobox").first().click();
    await page.getByText(`Skill ${skillKey}`, { exact: true }).click();
    await expect(skillBindingsCard.getByText(skillKey, { exact: true })).toBeVisible();

    const mcpBindingsCard = cardByHeading(page, /mcp server bindings/i);
    await mcpBindingsCard.getByRole("button", { name: /add mcp server binding/i }).click();
    await mcpBindingsCard.getByRole("combobox").first().click();
    await page.getByLabel("Suggestions").getByText(`MCP ${serverKey}`, { exact: true }).click();
    await expect(mcpBindingsCard.getByText(serverKey, { exact: true })).toBeVisible();

    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);
    await expectLegacyAgentAuthoringAbsent(page);

    await page.getByRole("tab", { name: /test panel/i }).click();
    await expect(page.getByLabel("Sample Input JSON")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /^Sample input$/i })).toBeVisible();
    await expect(page.getByTestId("agent-test-panel-sample-input-raw-json")).toBeVisible();
    await expect(page.getByLabel("Exact raw sample-input JSON")).toHaveValue(/"ticker": "AAPL"/);
    await page.getByTestId("agent-test-panel-sample-input-form").getByRole("textbox").fill("MSFT");
    await expect(page.getByLabel("Exact raw sample-input JSON")).toHaveValue(/"ticker": "MSFT"/);
    await page.getByTestId("agent-test-panel-run").click();
    await expect(page.getByTestId("agent-test-panel-result")).toBeVisible();
    await expect(page.getByTestId("agent-test-panel-result-raw-json")).toBeVisible();
    await expect(page.getByTestId("agent-test-panel-result")).toContainText("MSFT");
    await expect(page.getByTestId("agent-test-panel-result")).toContainText(agentKey);
    await expect(page.getByLabel("Exact raw result JSON")).toHaveValue(/"sampleInput"/);
    await expect(page.getByLabel("Exact raw result JSON")).toHaveValue(/"ticker": "MSFT"/);
    await expect(page.getByLabel("Exact raw result JSON")).toHaveValue(new RegExp(agentKey));

    await page.getByTestId("agents-duplicate").click();
    await expect(page).toHaveURL(/\/agents\/new\?duplicateFrom=\d+$/);
    await expect(page.getByRole("heading", { name: /duplicate agent/i })).toBeVisible();
    await expectLegacyAgentAuthoringAbsent(page);
    await expect(page.getByRole("textbox", { name: /^Name$/i })).toHaveValue(`Macro Agent ${timestamp} Copy`);
    await page.getByRole("textbox", { name: /^Key$/i }).fill(duplicateAgentKey);
    await page.getByRole("button", { name: /save agent/i }).click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);

    await page.getByTestId("agents-archive").click();
    await expect(page.getByText("Agent archived")).toBeVisible();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.getByTestId(`agents-row-${duplicateAgentKey}`)).toBeVisible();
    await expect(page.getByTestId(`agents-archive-${duplicateAgentKey}`)).toHaveCount(0);
  });
});
