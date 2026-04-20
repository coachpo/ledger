import { expect, test, type APIRequestContext } from "@playwright/test";

const PLATFORM_API = "http://127.0.0.1:8001/api";

type OutputSchemaRead = {
  id: number;
  key: string;
  version: number;
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

    await page.goto("/skills/new");
    await page.getByRole("button", { name: /save skill/i }).click();
    await expect(page.getByText("At least one tool definition is required.")).toBeVisible();

    await page.getByLabel("Key").fill(skillKey);
    await page.getByLabel("Name").fill(`Summarize Skill ${timestamp}`);
    await page.getByLabel("Description").fill("Condenses responses.");
    await page.getByLabel("Tool Definitions").fill("ledger.market_data.quote_lookup");
    await page.getByRole("button", { name: /save skill/i }).click();
    await expect(page).toHaveURL(/\/skills\/\d+\/edit$/);
    await page.getByTestId("skills-activate").click();
    await expect(page.getByText("Skill activated")).toBeVisible();
    await page.goto("/skills");
    await expect(page.getByTestId(`skills-row-${skillKey}`)).toContainText(/published/i);

    await page.goto("/mcp-servers/new");
    await page.getByRole("button", { name: /save mcp server/i }).click();
    await expect(page.getByText("Key is required.")).toBeVisible();

    await page.getByLabel("Key").fill(serverKey);
    await page.getByLabel("Name").fill(`Quotes MCP ${timestamp}`);
    await page.getByLabel("Description").fill("Serves external quote lookups.");
    await page.getByLabel("Command").fill(`definitely_missing_mcp_binary_${timestamp}`);
    await page.getByRole("button", { name: /save mcp server/i }).click();
    await expect(page).toHaveURL(/\/mcp-servers\/\d+\/edit$/);
    await page.getByTestId("mcp-server-test-connection").click();
    await expect(page.getByTestId("mcp-server-connection-feedback")).toBeVisible();
    await page.getByTestId("mcp-server-activate").click();
    await expect(page.getByText("MCP server activated")).toBeVisible();
    await page.goto("/mcp-servers");
    await expect(page.getByTestId(`mcp-servers-row-${serverKey}`)).toContainText(/published/i);

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
