import { once } from "node:events";
import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";

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

async function seedModelConnection(
  request: APIRequestContext,
  key: string,
  overrides?: {
    baseUrl?: string;
    modelId?: string;
    timeoutSeconds?: number;
  },
) {
  const payload = {
    key,
    name: `E2E runs fake provider model ${key}`,
    description: "Fake provider model connection for runs monitor E2E.",
    baseUrl: overrides?.baseUrl ?? FAKE_PROVIDER_BASE_URL,
    modelId: overrides?.modelId ?? "fake-strict-schema",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: overrides?.timeoutSeconds ?? 5,
    apiKey: "sk-e2e-runs-fake-provider",
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

async function startHangingProvider() {
  let releaseResponse: (() => void) | null = null;
  const responseReleased = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  let firstRequestSeen: (() => void) | null = null;
  const firstRequest = new Promise<void>((resolve) => {
    firstRequestSeen = resolve;
  });
  const sockets = new Set<import("node:net").Socket>();
  const server = createServer(
    async (_request: IncomingMessage, _response: ServerResponse) => {
      firstRequestSeen?.();
      firstRequestSeen = null;
      await responseReleased;
    },
  );

  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });

  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Failed to start hanging provider.");
  }

  return {
    baseUrl: `http://127.0.0.1:${address.port}/v1`,
    waitForFirstRequest: () => firstRequest,
    async close() {
      releaseResponse?.();
      for (const socket of sockets) {
        socket.destroy();
      }
      server.close();
      await once(server, "close");
    },
  };
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

  const modelConnectionId = await seedModelConnection(request, modelKey);
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

  return { modelConnectionId, runId, targetKey: String(detail.targetKey) };
}

async function seedQueuedRun(request: APIRequestContext) {
  const suffix = Date.now();
  const packageKey = `e2e_runs_cancel_${suffix}`;
  const modelKey = `e2e_runs_cancel_model_${suffix}`;

  const hangingProvider = await startHangingProvider();
  await seedModelConnection(request, modelKey, {
    baseUrl: hangingProvider.baseUrl,
    timeoutSeconds: 30,
  });
  const createResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages`,
    {
      data: {
        manifestSource: packageManifest(packageKey, modelKey),
      },
    },
  );
  expect(createResponse.status()).toBe(201);
  const created = await createResponse.json();

  const firstLaunchResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
    { data: { workflowKey: "monitor_flow", parameters: { ticker: "MSFT" } } },
  );
  expect(firstLaunchResponse.status()).toBe(201);
  const firstRunId = Number((await firstLaunchResponse.json()).id);

  await hangingProvider.waitForFirstRequest();
  await expect
    .poll(
      async () => {
        const response = await request.get(`${PLATFORM_API_BASE}/runs/${firstRunId}`);
        expect(response.ok()).toBeTruthy();
        return (await response.json()).status;
      },
      { timeout: 15_000 },
    )
    .toBe("running");

  const secondLaunchResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
    { data: { workflowKey: "monitor_flow", parameters: { ticker: "AAPL" } } },
  );
  expect(secondLaunchResponse.status()).toBe(201);
  const queuedRunId = Number((await secondLaunchResponse.json()).id);

  await expect
    .poll(
      async () => {
        const response = await request.get(`${PLATFORM_API_BASE}/runs/${queuedRunId}`);
        expect(response.ok()).toBeTruthy();
        return (await response.json()).status;
      },
      { timeout: 15_000 },
    )
    .toBe("queued");

  const queuedDetailResponse = await request.get(`${PLATFORM_API_BASE}/runs/${queuedRunId}`);
  expect(queuedDetailResponse.ok()).toBeTruthy();
  const queuedDetail = await queuedDetailResponse.json();

  return {
    cleanup: async () => {
      await hangingProvider.close();
    },
    runId: queuedRunId,
    targetKey: String(queuedDetail.targetKey),
  };
}

test.describe("Runs inventory monitor", () => {
  test("shows labeled run monitor fields and opens a seeded run", async ({
    page,
    request,
  }) => {
    const { modelConnectionId, runId, targetKey } = await seedCompletedRun(request);

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/runs");
    await expect(page.getByTestId("runs-list-page")).toBeVisible();
    await expect(page.getByLabel("Package key")).toBeVisible();
    await expect(page.getByLabel("Workflow key")).toBeVisible();
    await expect(page.getByLabel("Run status")).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();

    await page.getByLabel("Package key").fill(targetKey);
    await expect(page.getByText("Failed to load runs")).toHaveCount(0);
    await expect(page.getByRole("table")).toContainText(targetKey);

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
    await expect(page.getByTestId("runs-inspection-workspace")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: new RegExp(`Run #${runId}`) }),
    ).toContainText(targetKey);

    const tabs = page.getByTestId("runs-detail-tabs");
    const expectedTabs = [
      ["output", "Output"],
      ["execution", "Execution"],
      ["overview", "Overview"],
      ["input", "Input"],
      ["runtime", "Runtime"],
      ["usage", "Usage"],
    ] as const;
    const tabList = tabs.getByRole("tablist", { name: /run detail sections/i });
    const triggers = expectedTabs.map(([key]) =>
      tabs.getByTestId(`runs-detail-tab-trigger-${key}`),
    );

    await expect(tabList.getByRole("tab")).toHaveCount(expectedTabs.length);
    await expect(tabList.getByRole("tab")).toHaveText(
      expectedTabs.map(([, label]) => label),
    );
    await expect(triggers[0]).toHaveAttribute("aria-selected", "true");
    await expect(triggers[0]).toHaveAttribute("data-state", "active");
    await expect(page.getByTestId("runs-detail-tab-panel-output")).toBeVisible();
    await expect(page.getByTestId("runs-detail-tab-panel-execution")).toBeHidden();
    await expect(page.getByTestId("runs-detail-tab-panel-input")).toBeHidden();
    await expect(page.getByTestId("runs-detail-tab-panel-runtime")).toBeHidden();
    await expect(page.getByTestId("runs-detail-final-output")).toBeVisible();
    await expect(
      page.getByText("Rendered payload view for the immutable run result."),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Output provenance" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Diagnostics" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Execution steps" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Run input" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Input provenance" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Runtime profile" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Token accounting" })).toHaveCount(0);
    await expect(page.getByTestId("runs-detail-section-metadata")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /^Metadata$/ })).toHaveCount(0);

    await page.getByTestId("runs-detail-tab-trigger-execution").click();
    await expect(page.getByTestId("runs-detail-tab-panel-execution")).toBeVisible();
    await expect(page.getByTestId("runs-detail-tab-panel-output")).toBeHidden();
    await expect(page.getByRole("heading", { name: "Diagnostics" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Execution steps" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Final output" })).toHaveCount(0);

    await page.getByTestId("runs-detail-tab-trigger-input").click();
    await expect(page.getByTestId("runs-detail-tab-panel-input")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Run input" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Input provenance" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Diagnostics" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Final output" })).toHaveCount(0);

    await page.getByTestId("runs-detail-tab-trigger-runtime").click();
    await expect(page.getByTestId("runs-detail-tab-panel-runtime")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Runtime profile" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Selected strategies" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Capability matrix" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Run input" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Final output" })).toHaveCount(0);

    await page.getByTestId("runs-detail-rerun").click();
    const rerunDialog = page.getByRole("dialog", {
      name: /run snapshot again/i,
    });
    await expect(rerunDialog).toBeVisible();
    await expectSharedDialogShell(page);
    await expect(rerunDialog).toContainText("Source run");
    await expect(rerunDialog).toContainText("Readiness");
    const parametersJson = rerunDialog.getByLabel("Root run parameters JSON");
    await expect(parametersJson).toHaveValue(/AAPL/);
    await parametersJson.fill('{"ticker":');
    await expect(rerunDialog).toContainText(
      "Root run parameters JSON must be valid JSON.",
    );
    await expect(rerunDialog.getByTestId("run-rerun-submit")).toBeDisabled();
    await parametersJson.fill('{"ticker":"MSFT"}');
    await expect(rerunDialog.getByTestId("run-rerun-submit")).toBeEnabled();
    const [rerunResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/runs/${runId}/reruns`) &&
          response.request().method() === "POST",
      ),
      rerunDialog.getByTestId("run-rerun-submit").click(),
    ]);
    const rerunResponseText = await rerunResponse.text();
    expect(rerunResponse.status(), rerunResponseText).toBe(201);
    const rerunId = Number(JSON.parse(rerunResponseText).id);
    await expect(page).toHaveURL(new RegExp(`/runs/${rerunId}$`));
    await expect
      .poll(
        async () => {
          const response = await request.get(`${PLATFORM_API_BASE}/runs/${rerunId}`);
          expect(response.ok()).toBeTruthy();
          return (await response.json()).status;
        },
        { timeout: 15_000 },
      )
      .toBe("succeeded");
    const rerunDetailResponse = await request.get(
      `${PLATFORM_API_BASE}/runs/${rerunId}`,
    );
    expect(rerunDetailResponse.ok()).toBeTruthy();
    expect((await rerunDetailResponse.json()).input).toMatchObject({
      ticker: "MSFT",
    });

    const deleteConnection = await request.delete(
      `${PLATFORM_API_BASE}/model-connections/${modelConnectionId}`,
    );
    expect(deleteConnection.status()).toBe(204);
    await page.goto(`/runs/${runId}`);
    await page.getByTestId("runs-detail-rerun").click();
    const blockedRerunDialog = page.getByRole("dialog", {
      name: /run snapshot again/i,
    });
    await expect(blockedRerunDialog).toBeVisible();
    await expect(blockedRerunDialog.getByTestId("run-rerun-readiness")).toContainText(
      "Current snapshot readiness blocked",
    );
    await expect(blockedRerunDialog.getByTestId("run-rerun-submit")).toBeDisabled();
  });

  test("cancels a queued run from the run detail page", async ({
    page,
    request,
  }) => {
    const { cleanup, runId, targetKey } = await seedQueuedRun(request);

    try {
      await page.goto(`/runs/${runId}`);
      await expect(page.getByTestId("runs-detail-page")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: new RegExp(`Run #${runId}`) }),
      ).toContainText(targetKey);
      await expect(page.getByTestId("runs-detail-summary-line")).toContainText(
        "queued",
      );

      await page.getByTestId("runs-detail-cancel").click();

      await expect
        .poll(
          async () => {
            const response = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
            expect(response.ok()).toBeTruthy();
            return (await response.json()).status;
          },
          { timeout: 15_000 },
        )
        .toBe("cancelled");

      await expect(page.getByTestId("runs-detail-summary-line")).toContainText(
        "cancelled",
      );
      await expect(page.getByTestId("runs-detail-cancel")).toHaveCount(0);
    } finally {
      await cleanup();
    }
  });
});
