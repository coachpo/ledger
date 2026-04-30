import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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
      apiKey: "sk-playwright-workflow-yaml",
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
output:
  from: \${{ steps.research.outputs.analysis }}
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
    let runPayload: Record<string, unknown> | null = null;

    await page.route("**/api/workflows/*/runs?*", async (route) => {
      runPayload = route.request().postDataJSON() as Record<string, unknown>;
      const workflowId = Number(route.request().url().match(/\/workflows\/(\d+)\/runs/)?.[1] ?? 0);
      await route.fulfill({
        body: JSON.stringify({
          createdAt: "2026-04-29T10:00:00Z",
          id: 8801,
          status: "running",
          targetId: workflowId,
          targetKey: workflowKey,
          targetKind: "workflow",
          targetVersion: 1,
          traceId: "trace-workflow-yaml-8801",
        }),
        contentType: "application/json",
        status: 201,
      });
    });

    await page.route("**/api/runs/8801", async (route) => {
      await route.fulfill({
        body: JSON.stringify({
          createdAt: "2026-04-29T10:00:00Z",
          error: null,
          finalOutput: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
          finishedAt: "2026-04-29T10:00:04Z",
          id: 8801,
          input: runPayload ?? {},
          perStepOutputs: {
            "1": [
              {
                agentId: agent.id,
                agentKey: agent.key,
                agentVersion: agent.version,
                costUsd: "0.01000000",
                durationMs: 5,
                error: null,
                output: { summary: `Workflow summary for ${String(runPayload?.ticker ?? "AAPL")}` },
                outputSchemaId: schema.id,
                outputSchemaVersion: schema.version,
                resolvedInput: runPayload ?? {},
                slot: "analysis",
                status: "succeeded",
                tokens: 18,
                traceSpanId: "span-workflow-yaml-1",
              },
            ],
          },
          startedAt: "2026-04-29T10:00:00Z",
          status: "succeeded",
          targetId: 1,
          targetKey: workflowKey,
          targetKind: "workflow",
          targetVersion: 1,
          totalCostUsd: "0.01000000",
          totalTokens: 18,
          traceId: "trace-workflow-yaml-8801",
          updatedAt: "2026-04-29T10:00:04Z",
        }),
        contentType: "application/json",
      });
    });

    await page.goto("/workflows/new");
    await expectYamlOnlyEditor(page);
    await expect(page.getByTestId("workflow-run-unavailable")).toBeVisible();
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
    const workflowEditUrl = page.url();

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

    await page.goto("/workflows");
    await page.getByTestId(`workflows-run-${workflowKey}`).click();
    await expect(page).toHaveURL(/\/workflows\/\d+\/edit#review$/);
    await expect(page.getByTestId("workflow-yaml-editor")).toHaveValue(editedManifest);
    await expect(page.getByTestId("workflow-run-panel")).toBeVisible();
    await expect(page.getByTestId("workflow-run-input-raw-json").locator("textarea")).toHaveValue(
      /"ticker": "AAPL"/,
    );
    await page.getByTestId("workflow-run-input-form").getByRole("textbox").fill("MSFT");
    await expect(page.getByTestId("workflow-run-input-raw-json").locator("textarea")).toHaveValue(
      /"ticker": "MSFT"/,
    );
    await page.getByTestId("workflow-run-now").click();
    await expect(page).toHaveURL(/\/runs\/8801$/);
    expect(runPayload).toEqual({ ticker: "MSFT" });
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-final-output")).toContainText(
      "Workflow summary for MSFT",
    );
    await expect(page.getByTestId("runs-trace-linkage")).toContainText("trace-workflow-yaml-8801");
    expect(workflowEditUrl).toMatch(/\/workflows\/\d+\/edit$/);
  });
});
