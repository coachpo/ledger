import { expect, test, type Page } from "@playwright/test";

type WorkflowCreatePayload = {
  description?: string;
  inputSchema: {
    properties: Record<string, unknown>;
    required?: string[];
    type: "object";
  };
  key: string;
  name: string;
  outputSpec: {
    kind: "slot";
    slot: string;
    stepIndex: number;
  };
  steps: Array<{
    agents: Array<{
      agentKey: string;
      agentVersion: number | null;
      optional: boolean;
      slot: string;
      wiring: Record<string, unknown>;
    }>;
    index: number;
  }>;
};

function runInputForm(page: Page) {
  return page
    .getByRole("tabpanel", { name: "Review" })
    .getByText(
      "Enter the run payload through the shared schema-driven form instead of authoring JSON.",
      { exact: true },
    )
    .locator("xpath=ancestor::*[@data-slot='card'][1]");
}

async function expectLegacyWorkflowJsonAuthoringAbsent(page: Page) {
  await expect(page.getByLabel("Input Schema JSON")).toHaveCount(0);
  await expect(page.getByLabel("Run Input JSON")).toHaveCount(0);
  await expect(page.getByTestId("workflow-review-payload")).toHaveCount(0);
}

test("workflow wizard uses structured authoring and opens the runs monitor", async ({ page }) => {
  const agents = [
    {
      id: 1,
      budgetUsd: "0.50000000",
      createdAt: "2026-04-20T10:00:00Z",
      description: "Researches a ticker.",
      inputSchema: {
        properties: { ticker: { type: "string" } },
        required: ["ticker"],
        type: "object",
      },
      key: "research_agent",
      maxToolRounds: 3,
      mcpServers: [],
      model: "openai:gpt-5.4-mini",
      name: "Research Agent",
      outputSchema: {
        id: 11,
        jsonSchema: {
          additionalProperties: false,
          properties: { summary: { type: "string" } },
          required: ["summary"],
          type: "object",
        },
        key: "decision_schema",
        version: 1,
      },
      skills: [],
      status: "published",
      streaming: true,
      systemPrompt: "Research clearly.",
      temperature: 0,
      updatedAt: "2026-04-20T10:00:00Z",
      version: 3,
    },
    {
      id: 2,
      budgetUsd: "0.75000000",
      createdAt: "2026-04-20T10:00:00Z",
      description: "Consumes prior analysis.",
      inputSchema: {
        properties: {
          analysis: {
            properties: { summary: { type: "string" } },
            required: ["summary"],
            type: "object",
          },
        },
        required: ["analysis"],
        type: "object",
      },
      key: "consumer_agent",
      maxToolRounds: 3,
      mcpServers: [],
      model: "openai:gpt-5.4-mini",
      name: "Consumer Agent",
      outputSchema: {
        id: 11,
        jsonSchema: {
          additionalProperties: false,
          properties: { summary: { type: "string" } },
          required: ["summary"],
          type: "object",
        },
        key: "decision_schema",
        version: 1,
      },
      skills: [],
      status: "published",
      streaming: true,
      systemPrompt: "Consume clearly.",
      temperature: 0,
      updatedAt: "2026-04-20T10:00:00Z",
      version: 2,
    },
  ];

  let createdWorkflowPayload: WorkflowCreatePayload | null = null;

  const workflow = {
    aggregateBudgetUsd: "1.25000000",
    createdAt: "2026-04-20T10:00:00Z",
    description: "Runs research then produces a decision.",
    id: 501,
    inputSchema: {
      properties: { ticker: { type: "string" } },
      required: ["ticker"],
      type: "object",
    },
    key: "market_review",
    name: "Market Review",
    outputSpec: {
      agentId: 2,
      agentKey: "consumer_agent",
      agentVersion: 2,
      kind: "slot",
      outputSchemaId: 11,
      outputSchemaVersion: 1,
      slot: "decision",
      stepIndex: 2,
    },
    status: "published",
    steps: [
      {
        agents: [
          {
            agentId: 1,
            agentKey: "research_agent",
            agentVersion: 3,
            budgetUsd: "0.50000000",
            optional: false,
            outputSchemaId: 11,
            outputSchemaVersion: 1,
            slot: "analysis",
            wiring: { ticker: { from: "input", path: "ticker" } },
          },
        ],
        index: 1,
      },
      {
        agents: [
          {
            agentId: 2,
            agentKey: "consumer_agent",
            agentVersion: 2,
            budgetUsd: "0.75000000",
            optional: false,
            outputSchemaId: 11,
            outputSchemaVersion: 1,
            slot: "decision",
            wiring: { analysis: { from: "step", slot: "analysis", stepIndex: 1 } },
          },
        ],
        index: 2,
      },
    ],
    updatedAt: "2026-04-20T10:00:00Z",
    version: 1,
  };

  const runCreated = {
    createdAt: "2026-04-20T10:00:02Z",
    id: 901,
    status: "running",
    traceId: "trace-901",
    workflowId: 501,
    workflowKey: "market_review",
    workflowVersion: 1,
  };

  const runDetail = {
    createdAt: "2026-04-20T10:00:02Z",
    error: null,
    finalOutput: { summary: "decision" },
    finishedAt: "2026-04-20T10:00:05Z",
    id: 901,
    input: { ticker: "AAPL" },
    perStepOutputs: {
      "1": [
        {
          agentId: 1,
          agentKey: "research_agent",
          agentVersion: 3,
          costUsd: "0.02000000",
          durationMs: 8,
          error: null,
          output: { summary: "analysis" },
          outputSchemaId: 11,
          outputSchemaVersion: 1,
          resolvedInput: { ticker: "AAPL" },
          slot: "analysis",
          status: "succeeded",
          tokens: 21,
          traceSpanId: "span-1",
        },
      ],
      "2": [
        {
          agentId: 2,
          agentKey: "consumer_agent",
          agentVersion: 2,
          costUsd: "0.03000000",
          durationMs: 12,
          error: null,
          output: { summary: "decision" },
          outputSchemaId: 11,
          outputSchemaVersion: 1,
          resolvedInput: { analysis: { summary: "analysis" } },
          slot: "decision",
          status: "succeeded",
          tokens: 30,
          traceSpanId: "span-2",
        },
      ],
    },
    startedAt: "2026-04-20T10:00:02Z",
    status: "succeeded",
    totalCostUsd: "0.05000000",
    totalTokens: 51,
    traceId: "trace-901",
    updatedAt: "2026-04-20T10:00:05Z",
    workflowId: 501,
    workflowKey: "market_review",
    workflowVersion: 1,
  };

  await page.route("**/api/agents**", async (route) => {
    await route.fulfill({ body: JSON.stringify({ items: agents }), contentType: "application/json" });
  });

  await page.route("**/api/workflows?*", async (route) => {
    await route.fulfill({ body: JSON.stringify({ items: [workflow] }), contentType: "application/json" });
  });

  await page.route("**/api/workflows/501*", async (route) => {
    await route.fulfill({ body: JSON.stringify(workflow), contentType: "application/json" });
  });

  await page.route("**/api/workflows", async (route) => {
    if (route.request().method() === "POST") {
      createdWorkflowPayload = route.request().postDataJSON() as WorkflowCreatePayload;
      await route.fulfill({ body: JSON.stringify(workflow), contentType: "application/json" });
      return;
    }

    await route.continue();
  });

  await page.route("**/api/workflows/501/runs?*", async (route) => {
    await route.fulfill({ body: JSON.stringify(runCreated), contentType: "application/json", status: 201 });
  });

  await page.route("**/api/runs/901", async (route) => {
    await route.fulfill({ body: JSON.stringify(runDetail), contentType: "application/json" });
  });

  await page.route("**/api/runs?*", async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        items: [
          {
            finishedAt: runDetail.finishedAt,
            id: runDetail.id,
            startedAt: runDetail.startedAt,
            status: runDetail.status,
            totalCostUsd: runDetail.totalCostUsd,
            totalTokens: runDetail.totalTokens,
            traceId: runDetail.traceId,
            workflowId: runDetail.workflowId,
            workflowKey: runDetail.workflowKey,
            workflowVersion: runDetail.workflowVersion,
          },
        ],
      }),
      contentType: "application/json",
    });
  });

  await page.goto("/workflows/new");
  await expect(page.getByTestId("workflows-editor")).toBeVisible();
  await expect(page.getByRole("heading", { name: /workflow input schema/i })).toBeVisible();
  await expectLegacyWorkflowJsonAuthoringAbsent(page);

  await page.getByLabel("Workflow Key").fill("market_review");
  await page.getByLabel("Workflow Name").fill("Market Review");
  await page.getByTestId("output-schema-field-name-0").fill("ticker");
  await page.getByTestId("workflow-wizard-next").click();

  await page.getByLabel("Step 1 Agent 1 agent").click();
  await page.getByText("Research Agent (research_agent@3)").click();
  await page.getByLabel("Step 1 Agent 1 slot").fill("analysis");
  await page.getByLabel("ticker source").click();
  await page.getByText("Workflow input", { exact: true }).click();

  await page.getByRole("button", { name: /add step/i }).click();
  await page.getByLabel("Step 2 Agent 1 agent").click();
  await page.getByText("Consumer Agent (consumer_agent@2)", { exact: true }).click();
  await page.getByLabel("Step 2 Agent 1 slot").fill("decision");
  await page.getByLabel("analysis source").click();
  await page.getByText("Previous step slot", { exact: true }).click();
  await page.getByRole("combobox", { name: "analysis slot" }).click();
  await page.getByRole("option", { name: "analysis" }).click();

  await page.getByTestId("workflow-wizard-next").click();
  await page.getByLabel("Output step").click();
  await page.getByRole("option", { name: "Step 2" }).click();
  await page.getByLabel("Output slot").click();
  await page.getByRole("option", { name: "decision" }).click();

  await page.getByTestId("workflow-wizard-next").click();
  await expectLegacyWorkflowJsonAuthoringAbsent(page);
  await expect(page.getByTestId("workflow-review-summary")).toBeVisible();
  await expect(page.getByTestId("workflow-review-summary")).toContainText("market_review");
  await expect(page.getByTestId("workflow-review-summary")).toContainText("ticker");
  await expect(page.getByTestId("workflow-review-summary")).toContainText("decision");
  await expect(runInputForm(page)).toContainText(
    "Enter the run payload through the shared schema-driven form instead of authoring JSON.",
  );
  await expect(runInputForm(page)).toContainText("ticker");
  await expect(runInputForm(page).getByRole("textbox")).toHaveCount(1);
  await runInputForm(page).getByRole("textbox").fill("AAPL");

  await page.getByTestId("workflow-save").click();
  await expect(page).toHaveURL(/\/workflows\/501\/edit$/);
  await expectLegacyWorkflowJsonAuthoringAbsent(page);
  await expect(page.getByTestId("workflow-review-summary")).toContainText("market_review");

  expect(createdWorkflowPayload).not.toBeNull();
  expect(createdWorkflowPayload).not.toHaveProperty("inputSchemaText");
  expect(createdWorkflowPayload).toMatchObject({
    inputSchema: {
      properties: { ticker: { type: "string" } },
      required: ["ticker"],
      type: "object",
    },
    key: "market_review",
    name: "Market Review",
    outputSpec: {
      kind: "slot",
      slot: "decision",
      stepIndex: 2,
    },
    steps: [
      {
        agents: [
          {
            agentKey: "research_agent",
            agentVersion: null,
            optional: false,
            slot: "analysis",
            wiring: { ticker: { from: "input", path: "ticker" } },
          },
        ],
        index: 1,
      },
      {
        agents: [
          {
            agentKey: "consumer_agent",
            agentVersion: null,
            optional: false,
            slot: "decision",
            wiring: { analysis: { from: "step", slot: "analysis", stepIndex: 1 } },
          },
        ],
        index: 2,
      },
    ],
  });

  await page.getByTestId("workflow-run-now").click();
  await expect(page).toHaveURL(/\/runs\/901$/);
  await expect(page.getByTestId("runs-detail-page")).toBeVisible();
  await expect(page.getByTestId("runs-detail-final-output")).toContainText("decision");
  await expect(page.getByTestId("runs-trace-linkage")).toContainText("trace-901");

  await page.goto("/runs");
  await expect(page.getByTestId("runs-row-901")).toContainText("market_review");
});
