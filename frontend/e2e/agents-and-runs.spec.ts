import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { buildRunCreated, buildRunDetail, buildRunInvocation, buildRunStep } from "./run-detail-fixtures";

const PLATFORM_API = "http://127.0.0.1:8001/api";

type ModelConnectionRead = {
  id: number;
  key: string;
};

type OutputSchemaRead = {
  id: number;
  key: string;
  version: number;
};

type CapabilityRead = {
  id: number;
  key: string;
  version: number;
};

type McpServerRead = {
  id: number;
  key: string;
  version: number;
};

async function createModelConnection(request: APIRequestContext, key: string): Promise<ModelConnectionRead> {
  const response = await request.post(`${PLATFORM_API}/model-connections`, {
    data: {
      apiKey: "sk-playwright-agent-yaml",
      baseUrl: "https://api.openai.com/v1",
      description: "Playwright-only agent YAML model connection.",
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

async function createPublishedOutputSchema(request: APIRequestContext, key: string): Promise<OutputSchemaRead> {
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

async function createPublishedCapability(
  request: APIRequestContext,
  key: string,
): Promise<CapabilityRead> {
  const createResponse = await request.post(`${PLATFORM_API}/capabilities`, {
    data: {
      description: "Summarizes deterministic E2E inputs.",
      key,
      name: `Capability ${key}`,
      toolGrants: [{ tool: "ledger.market_data.quote_lookup" }],
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const draft = (await createResponse.json()) as CapabilityRead;
  const activateResponse = await request.post(`${PLATFORM_API}/capabilities/${draft.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as CapabilityRead;
}

async function createPublishedMcpServer(request: APIRequestContext, key: string): Promise<McpServerRead> {
  const createResponse = await request.post(`${PLATFORM_API}/mcp-servers`, {
    data: {
      args: ["--version"],
      command: "python3",
      description: "Serves deterministic E2E MCP data.",
      enabled: true,
      key,
      name: `MCP ${key}`,
      transport: "stdio",
    },
  });

  expect(createResponse.ok()).toBeTruthy();
  const draft = (await createResponse.json()) as McpServerRead;
  const activateResponse = await request.post(`${PLATFORM_API}/mcp-servers/${draft.id}/activate`);
  expect(activateResponse.ok()).toBeTruthy();
  return (await activateResponse.json()) as McpServerRead;
}

function agentManifest(options: {
  description: string;
  key: string;
  mcpServerRef: string;
  modelConnectionKey: string;
  name: string;
  outputSchemaRef: string;
  capabilityRef: string;
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
  capabilities:
    - ${options.capabilityRef}
  mcpServers:
    - ${options.mcpServerRef}
  budgetUsd: "0.25"
`;
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
  await expect(page.getByLabel("Input Schema JSON")).toHaveCount(0);
  await expect(page.getByLabel("Sample Input JSON")).toHaveCount(0);
  await expect(page.getByTestId("agent-input-schema-raw-json")).toHaveCount(0);
  await expect(page.getByTestId("output-schema-add-field")).toHaveCount(0);
}

test.describe("Agent YAML editor", () => {
  test("creates, reloads, versions, diagnoses invalid refs, and launches saved runs", async ({
    page,
    request,
  }) => {
    const timestamp = Date.now();
    const modelConnection = await createModelConnection(request, `agent_yaml_model_${timestamp}`);
    const outputSchema = await createPublishedOutputSchema(request, `agent_yaml_schema_${timestamp}`);
    const capability = await createPublishedCapability(request, `agent_yaml_capability_${timestamp}`);
    const mcpServer = await createPublishedMcpServer(request, `agent_yaml_mcp_${timestamp}`);
    const agentKey = `agent_yaml_${timestamp}`;
    const initialManifest = agentManifest({
      description: "Created from Playwright YAML.",
      key: agentKey,
      mcpServerRef: `${mcpServer.key}@${mcpServer.version}`,
      modelConnectionKey: modelConnection.key,
      name: `Agent YAML ${timestamp}`,
      outputSchemaRef: `${outputSchema.key}@${outputSchema.version}`,
      capabilityRef: `${capability.key}@${capability.version}`,
      systemPrompt: "Summarize the requested ticker.",
    });
    const editedManifest = agentManifest({
      description: "Updated from Playwright YAML.",
      key: agentKey,
      mcpServerRef: `${mcpServer.key}@${mcpServer.version}`,
      modelConnectionKey: modelConnection.key,
      name: `Agent YAML ${timestamp}`,
      outputSchemaRef: `${outputSchema.key}@${outputSchema.version}`,
      capabilityRef: `${capability.key}@${capability.version}`,
      systemPrompt: "Summarize the requested ticker with one actionable note.",
    });
    let runPayload: Record<string, unknown> | null = null;
    let runRequestUrl = "";

    await page.route("**/api/agents/*/runs?*", async (route) => {
      runPayload = route.request().postDataJSON() as Record<string, unknown>;
      runRequestUrl = route.request().url();
      const agentId = Number(route.request().url().match(/\/agents\/(\d+)\/runs/)?.[1] ?? 0);
      await route.fulfill({
        body: JSON.stringify({
          ...buildRunCreated({
            createdAt: "2026-04-29T12:00:00Z",
            id: 9901,
            targetId: agentId,
            targetKey: agentKey,
            targetKind: "agent",
            targetVersion: 2,
            traceId: "trace-agent-yaml-9901",
          }),
        }),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/9901", async (route) => {
      const ticker = String(runPayload?.ticker ?? "AAPL");
      await route.fulfill({
        body: JSON.stringify(
          buildRunDetail({
            createdAt: "2026-04-29T12:00:00Z",
            finalOutput: { summary: `Agent summary for ${ticker}` },
            finishedAt: "2026-04-29T12:00:04Z",
            id: 9901,
            input: runPayload ?? {},
            startedAt: "2026-04-29T12:00:01Z",
            steps: [
              buildRunStep({
                id: 990101,
                invocations: [
                  buildRunInvocation({
                    agentKey,
                    agentVersion: 2,
                    id: 9901001,
                    output: { summary: `Agent summary for ${ticker}` },
                    resolvedInput: runPayload ?? {},
                    runId: 9901,
                    runStepId: 990101,
                    slot: "result",
                    traceSpanId: "span-agent-yaml-1",
                  }),
                ],
                runId: 9901,
              }),
            ],
            targetId: 1,
            targetKey: agentKey,
            targetKind: "agent",
            targetVersion: 2,
            traceId: "trace-agent-yaml-9901",
          }),
        ),
        contentType: "application/json",
      });
    });

    await page.goto("/agents/new");
    await expectYamlOnlyAgentEditor(page);
    await expect(page.getByTestId("agent-run-unavailable")).toBeVisible();
    await page.getByTestId("agent-yaml-editor").fill(initialManifest);
    await expect(page.getByTestId("agent-dirty-indicator")).toContainText("Unsaved changes");

    await page.getByTestId("agents-validate-manifest").click();
    await expect(page.getByTestId("agent-backend-validation-status")).toContainText("Backend validation passed");
    await expect(page.getByTestId("agent-validation-feedback")).toContainText("No diagnostics yet.");
    await expect(page.getByTestId("agent-compiled-preview").locator("textarea")).toHaveValue(/agent_yaml_/);
    await expect(page.getByTestId("agent-run-input-preview").locator("textarea")).toHaveValue(/"ticker"/);

    await Promise.all([page.waitForURL(/\/agents\/\d+\/edit$/), page.getByTestId("agents-save").click()]);
    await expect(page.getByTestId("agent-dirty-indicator")).toContainText("Saved baseline");
    const agentEditUrl = page.url();
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(initialManifest);

    await page.goto("/agents");
    await expect(page.getByTestId(`agents-row-${agentKey}`)).toContainText("Created from Playwright YAML.");
    await page.getByTestId(`agents-open-${agentKey}`).click();
    await expect(page).toHaveURL(/\/agents\/\d+\/edit$/);
    await expectYamlOnlyAgentEditor(page);
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(initialManifest);

    await page.getByTestId("agent-yaml-editor").fill(editedManifest);
    await expect(page.getByTestId("agent-run-unsaved-blocked")).toContainText("Save required before run");
    await page.getByTestId("agents-save").click();
    await expect(page.getByText("Agent manifest saved")).toBeVisible();
    await expect(page.getByTestId("agent-dirty-indicator")).toContainText("Saved baseline");
    await expect(page.getByTestId("agent-command-bar")).toContainText("v2");
    await page.reload();
    await expect(page.getByTestId("agent-yaml-editor")).toHaveValue(editedManifest);

    const invalidManifest = editedManifest.replace(`${outputSchema.key}@${outputSchema.version}`, `missing_${outputSchema.key}@9`);
    await page.getByTestId("agent-yaml-editor").fill(invalidManifest);
    await page.getByTestId("agents-validate-manifest").click();
    await expect(page.getByTestId("agent-backend-validation-status")).toContainText("Backend validation found errors");
    const backendDiagnostic = page
      .getByTestId("agent-validation-feedback")
      .getByRole("button")
      .filter({ hasText: `missing_${outputSchema.key}` })
      .first();
    await expect(backendDiagnostic).toBeVisible();
    await backendDiagnostic.click();
    await expect(page.getByTestId("agent-yaml-editor")).toBeFocused();

    await page.getByTestId("agent-yaml-editor").fill(editedManifest);
    await expect(page.getByTestId("agent-dirty-indicator")).toContainText("Saved baseline");
    await expect(page.getByTestId("agent-run-panel-launch")).toContainText("Launch saved version v2");
    await expect(page.getByTestId("agent-run-panel-input-raw-json").locator("textarea")).toHaveValue(/"ticker": "example"/);
    await page.getByTestId("agent-run-panel-input-form").getByRole("textbox").fill("MSFT");
    await expect(page.getByTestId("agent-run-panel-input-raw-json").locator("textarea")).toHaveValue(/"ticker": "MSFT"/);
    await page.getByTestId("agent-run-panel-launch").click();

    await expect(page).toHaveURL(/\/runs\/9901$/);
    expect(runPayload).toEqual({ ticker: "MSFT" });
    expect(runRequestUrl).toMatch(/version=2/);
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-final-output")).toContainText("Agent summary for MSFT");
    expect(agentEditUrl).toMatch(/\/agents\/\d+\/edit$/);
  });
});
