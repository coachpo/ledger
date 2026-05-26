import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const DETERMINISTIC_MODEL_BASE_URL =
  "https://signaldeck-deterministic-model.local/v1";

function packageManifest(packageKey: string, modelKey: string) {
  return [
    "apiVersion: signaldeck.workflowPackage/v1",
    "kind: WorkflowPackage",
    "metadata:",
    `  key: ${packageKey}`,
    `  name: E2E Runs Monitor ${packageKey}`,
    "  description: Runs monitor E2E fixture.",
    "spec:",
    "  inputs:",
    "    type: object",
    "    properties:",
    "      ticker:",
    "        type: string",
    "    required: [ticker]",
    "  outputSchemas:",
    "    - key: monitor_output",
    "      name: Monitor Output",
    "      jsonSchema:",
    "        type: object",
    "        properties:",
    "          summary:",
    "            type: string",
    "        required: [summary]",
    "  agents:",
    "    - key: monitor_agent",
    "      name: Monitor Agent",
    `      modelConnection: ${modelKey}`,
    "      systemPrompt: Return deterministic JSON.",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      outputSchema: monitor_output",
    "  workflows:",
    "    - key: monitor_flow",
    "      name: Monitor Flow",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      flow:",
    "        kind: step",
    "        id: monitor_analysis",
    "        slot: summary",
    "        uses: monitor_agent",
    "        with:",
    "          ticker: ${{ inputs.ticker }}",
    "      output:",
    "        from: ${{ nodes.monitor_analysis.outputs.summary }}",
    "",
  ].join("\n");
}

async function seedModelConnection(request: APIRequestContext, key: string) {
  const payload = {
    key,
    name: `E2E runs deterministic model ${key}`,
    description: "Deterministic model connection for runs monitor E2E.",
    connectionKind: "deterministic_smoke",
    baseUrl: DETERMINISTIC_MODEL_BASE_URL,
    modelId: "signaldeck-deterministic-json",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-runs-deterministic",
  };

  const list = await request.get(`${PLATFORM_API_BASE}/model-connections`, {
    params: { status: "active" },
  });
  expect(list.ok()).toBeTruthy();
  const existing = (await list.json()).items.find(
    (item: { id: number; key: string }) => item.key === key,
  );

  if (existing) {
    const { key: _key, ...updatePayload } = payload;
    const response = await request.patch(
      `${PLATFORM_API_BASE}/model-connections/${existing.id}`,
      { data: updatePayload },
    );
    expect(response.ok()).toBeTruthy();
    return existing.id;
  }

  const response = await request.post(
    `${PLATFORM_API_BASE}/model-connections`,
    {
      data: payload,
    },
  );
  expect(response.ok()).toBeTruthy();
  return Number((await response.json()).id);
}

async function expectSharedDialogShell(page: Page) {
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.locator('[data-slot="entity-dialog-constraint-strip"]'),
  ).toBeVisible();
  await expect(
    dialog.locator('[data-slot="entity-dialog-body"]'),
  ).toBeVisible();
  await expect(dialog.locator('[data-slot="dialog-footer"]')).toBeVisible();
  await expect(
    dialog
      .locator('[data-slot="dialog-footer"]')
      .getByRole("button", { name: "Cancel" }),
  ).toBeVisible();
}

async function seedCompletedRun(request: APIRequestContext) {
  const suffix = Date.now();
  const packageKey = `e2e_runs_monitor_${suffix}`;
  const modelKey = `e2e_runs_model_${suffix}`;

  await seedModelConnection(request, modelKey);
  const createResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages`,
    { data: { manifestSource: packageManifest(packageKey, modelKey) } },
  );
  expect(createResponse.status()).toBe(201);
  const created = await createResponse.json();

  const launchResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
    { data: { workflowKey: "monitor_flow", parameters: { ticker: "AAPL" } } },
  );
  expect(launchResponse.status()).toBe(201);
  const launched = await launchResponse.json();
  const runId = Number(launched.id);

  await expect
    .poll(
      async () => {
        const detailResponse = await request.get(
          `${PLATFORM_API_BASE}/runs/${runId}`,
        );
        expect(detailResponse.ok()).toBeTruthy();
        const detail = await detailResponse.json();
        return detail.status;
      },
      { timeout: 15_000 },
    )
    .toBe("succeeded");

  const detailResponse = await request.get(
    `${PLATFORM_API_BASE}/runs/${runId}`,
  );
  expect(detailResponse.ok()).toBeTruthy();
  const detail = await detailResponse.json();

  return { runId, targetKey: String(detail.targetKey) };
}

test.describe("Runs inventory monitor", () => {
  test("shows labeled run monitor fields and opens a seeded run", async ({
    page,
    request,
  }) => {
    const { runId, targetKey } = await seedCompletedRun(request);

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/runs");
    await expect(page.getByTestId("runs-list-page")).toBeVisible();
    await expect(page.getByLabel("Target key")).toBeVisible();
    await expect(page.getByLabel("Target kind")).toBeVisible();
    await expect(page.getByLabel("Run status")).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();

    await page.getByLabel("Target key").fill(targetKey);
    await expect(page.getByTestId("runs-monitor-filter-card")).toContainText(
      `${targetKey} · select target kind to apply`,
    );
    await expect(page.getByText("Failed to load runs")).toHaveCount(0);

    await page.getByLabel("Target kind").click();
    await page.getByRole("option", { name: "workflow package" }).click();
    await expect(page.getByTestId("runs-monitor-filter-card")).toContainText(
      targetKey,
    );

    const row = page.getByTestId(`runs-row-${runId}`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row).toContainText(`Run #${runId}`);
    await expect(row).toContainText(targetKey);
    await expect(page.getByRole("columnheader", { name: "Progress" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Tokens" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Timestamps" })).toBeVisible();
    await expect(row.getByTestId(`runs-row-progress-${runId}`)).toContainText("100%");
    await expect(row.getByTestId(`runs-row-queue-${runId}`)).toContainText("No queue hold");
    await expect(row).toContainText("Queued:");
    await expect(row).toContainText("Started:");
    await expect(row).toContainText("Finished:");
    await expect(row.getByTestId(`runs-row-action-${runId}`)).toHaveAttribute(
      "href",
      `/runs/${runId}`,
    );

    await row.getByTestId(`runs-row-action-${runId}`).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-console-layout",
      "split",
    );
    await expect(
      page.getByTestId("runs-inspection-split-layout"),
    ).toBeVisible();
    await expect(page.getByTestId("runs-tab-console")).toHaveAttribute(
      "data-active-mode",
      "outputs",
    );
    await expect(page.getByTestId("runs-detail-state-summary")).toContainText(
      "Output",
    );
    await expect(page.getByTestId("runs-evidence-viewer")).toContainText(
      "Final output",
    );
    await expect(page.getByTestId("runs-evidence-pane-nav")).toHaveCount(0);

    await page.getByTestId("runs-tab-trigger-execution").click();
    await expect(
      page.getByTestId("runs-execution-outline-frame"),
    ).toBeVisible();

    await page.getByTestId("runs-tab-trigger-runtime").click();
    await expect(page.getByTestId("runs-runtime-profile")).toContainText(
      "Runtime profile",
    );

    await page.getByTestId("runs-tab-trigger-metadata").click();
    await expect(page.getByRole("heading", { name: "Metadata" })).toBeVisible();

    await page.getByTestId("runs-detail-rerun").click();
    const rerunDialog = page.getByRole("dialog", {
      name: /run snapshot again/i,
    });
    await expect(rerunDialog).toBeVisible();
    await expectSharedDialogShell(page);
    await expect(rerunDialog).toContainText("Source run");
    await expect(rerunDialog).toContainText("Readiness");
    await rerunDialog.getByRole("button", { name: "Cancel" }).click();
    await expect(rerunDialog).toBeHidden();

    await page.getByTestId("runs-tab-trigger-inputs").click();
    await expect(page.getByTestId("runs-detail-input")).toBeVisible();
    await expect(page.getByTestId("runs-evidence-pane-nav")).toHaveCount(0);
    await expect(page).toHaveURL(/mode=inputs/);
    await expect(page).not.toHaveURL(/inspect=run/);
    await expect(page).not.toHaveURL(/pane=input/);

    await page
      .getByTestId("runs-detail-input")
      .getByRole("tab", { name: "Raw" })
      .click();
    await expect(page.getByTestId("runs-detail-input-tab-scroll")).toHaveClass(
      /overflow-x-auto/,
    );
    await expect(page.getByTestId("runs-detail-input-raw")).toHaveAttribute(
      "data-wide-payload",
      "scroll",
    );
  });
});
