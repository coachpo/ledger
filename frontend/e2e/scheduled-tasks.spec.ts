import {
  expect,
  test,
  type APIRequestContext,
} from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";

function scheduledPackageManifest(packageKey: string, modelKey: string) {
  return `apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: ${packageKey}
  name: E2E Scheduled Tasks ${packageKey}
  description: Scheduled Tasks E2E fixture.
spec:
  inputs:
    type: object
    properties:
      asOfDate:
        type: string
      scheduledLocalTime:
        type: string
      scheduledDateTime:
        type: string
      portfolioSlug:
        type: string
    required: [asOfDate, scheduledLocalTime, scheduledDateTime, portfolioSlug]
  outputSchemas:
    - key: scheduled_output
      name: Scheduled Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: scheduled_agent
      name: Scheduled Agent
      modelConnection: ${modelKey}
      systemPrompt: Return deterministic JSON.
      inputSchema:
        type: object
        properties:
          asOfDate:
            type: string
          scheduledLocalTime:
            type: string
          scheduledDateTime:
            type: string
          portfolioSlug:
            type: string
        required: [asOfDate, scheduledLocalTime, scheduledDateTime, portfolioSlug]
      outputSchema: scheduled_output
  workflows:
    - key: scheduled_flow
      name: Scheduled Flow
      inputSchema:
        type: object
        properties:
          asOfDate:
            type: string
          scheduledLocalTime:
            type: string
          scheduledDateTime:
            type: string
          portfolioSlug:
            type: string
        required: [asOfDate, scheduledLocalTime, scheduledDateTime, portfolioSlug]
      flow:
        kind: step
        id: scheduled_analysis
        slot: summary
        uses: scheduled_agent
        with:
          asOfDate: \${{ inputs.asOfDate }}
          scheduledLocalTime: \${{ inputs.scheduledLocalTime }}
          scheduledDateTime: \${{ inputs.scheduledDateTime }}
          portfolioSlug: \${{ inputs.portfolioSlug }}
      output:
        from: \${{ nodes.scheduled_analysis.outputs.summary }}
`;
}

async function seedModelConnection(request: APIRequestContext, key: string) {
  const payload = {
    key,
    name: `E2E scheduled fake provider ${key}`,
    description: "Fake provider model connection for Scheduled Tasks E2E.",
    baseUrl: FAKE_PROVIDER_BASE_URL,
    modelId: "fake-strict-schema",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-scheduled-fake-provider",
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
    { data: payload },
  );
  expect(response.ok()).toBeTruthy();
  return Number((await response.json()).id);
}

async function seedScheduledPackage(request: APIRequestContext) {
  const suffix = Date.now();
  const packageKey = `e2e_scheduled_tasks_${suffix}`;
  const modelKey = `e2e_scheduled_model_${suffix}`;
  await seedModelConnection(request, modelKey);
  const response = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages`,
    { data: { manifestSource: scheduledPackageManifest(packageKey, modelKey) } },
  );
  const responseText = await response.text();
  expect(response.status(), responseText).toBe(201);
  return JSON.parse(responseText) as { id: number; key: string; name: string };
}

async function waitForRun(request: APIRequestContext, runId: number) {
  const startedAt = Date.now();
  let latest: Record<string, unknown> | null = null;
  while (Date.now() - startedAt < 15_000) {
    const response = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as Record<string, unknown>;
    latest = body;
    if (!["queued", "running"].includes(String(body.status))) {
      return body;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Run ${runId} did not finish: ${JSON.stringify(latest)}`);
}

async function waitForScheduleLatestRun(
  request: APIRequestContext,
  scheduleId: number,
  runId: number,
) {
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${PLATFORM_API_BASE}/schedules/${scheduleId}`,
        );
        expect(response.ok()).toBeTruthy();
        const schedule = await response.json();
        return schedule.latestRunId;
      },
      { timeout: 15_000 },
    )
    .toBe(runId);
}

test.describe("scheduled tasks", () => {
  test.use({ timezoneId: "UTC" });

  test("scheduled tasks create, preview, pause, run now, history, and latest run link", async ({
    page,
    request,
  }) => {
    const workflowPackage = await seedScheduledPackage(request);
    const scheduleName = `E2E scheduled tasks ${workflowPackage.id}`;

    await page.goto("/scheduled-tasks");
    await expect(page.getByTestId("scheduled-tasks-list-page")).toBeVisible();
    await expect(page.getByTestId("route-scheduled-tasks-list")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    await page.getByRole("link", { name: "Create scheduled task" }).click();
    await expect(page).toHaveURL(/\/scheduled-tasks\/new$/);
    await expect(page.getByTestId("scheduled-task-new-page")).toBeVisible();
    await expect(page.getByTestId("route-scheduled-task-new")).toHaveAttribute(
      "data-route-shell-mode",
      "fullHeight",
    );

    await page.getByTestId("schedule-package-id").fill(String(workflowPackage.id));
    await page.getByTestId("schedule-workflow-key").fill("scheduled_flow");
    await page.getByTestId("schedule-name").fill(scheduleName);
    await page.getByLabel("Timezone").fill("America/New_York");
    await page.getByLabel("Daily local time").fill("09:30");
    await page.getByTestId("schedule-preview-scheduled-for").fill("2026-03-09T13:30");
    await page.getByLabel("Description").fill("Timezone-sensitive E2E schedule.");
    await page.getByTestId("schedule-input-template-json").fill(
      JSON.stringify(
        {
          asOfDate: "{{fire.scheduledLocalDate}}",
          portfolioSlug: "core_portfolio",
          scheduledDateTime: "{{fire.scheduledLocalDateTime}}",
          scheduledLocalTime: "{{fire.scheduledLocalTime}}",
        },
        null,
        2,
      ),
    );

    await page.getByTestId("schedule-input-preview-trigger").click();
    const preview = page.getByTestId("schedule-input-preview");
    await expect(preview).toBeVisible();
    await expect(preview).toContainText("Ready");
    await expect(preview).toContainText("2026-03-09");
    await expect(preview).toContainText("09:30");
    await expect(preview).toContainText("America/New_York");
    await expect(preview).toContainText("scheduledLocalTime");

    await page.getByTestId("schedule-save").click();
    await expect(page).toHaveURL(/\/scheduled-tasks\/\d+$/);
    const scheduleId = Number(page.url().match(/\/scheduled-tasks\/(\d+)$/)?.[1]);
    expect(Number.isInteger(scheduleId)).toBeTruthy();
    await expect(page.getByTestId("scheduled-task-detail-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: scheduleName })).toBeVisible();
    await expect(page.getByTestId("scheduled-task-detail-status-enabled")).toBeVisible();
    await expect(page.getByTestId("scheduled-task-detail-next-fire-summary")).toContainText(
      "America/New_York",
    );

    const actions = page.getByTestId("scheduled-task-detail-actions");
    await actions.getByRole("button", { name: "Pause" }).click();
    await expect(page.getByTestId("scheduled-task-detail-status-paused")).toBeVisible();
    await expect(page.getByTestId("scheduled-task-detail-diagnostics-strip")).toContainText("Schedule paused");
    await actions.getByRole("button", { name: "Resume" }).click();
    await expect(page.getByTestId("scheduled-task-detail-status-enabled")).toBeVisible();

    await page.getByTestId("schedule-run-now").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
    const runId = Number(page.url().match(/\/runs\/(\d+)$/)?.[1]);
    expect(Number.isInteger(runId)).toBeTruthy();
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: new RegExp(`Run #${runId}`) })).toBeVisible();
    const runDetail = await waitForRun(request, runId);
    expect(runDetail.status).toBe("succeeded");
    await waitForScheduleLatestRun(request, scheduleId, runId);

    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-page")).toBeVisible();
    await page
      .getByRole("tablist", { name: "Scheduled task detail sections" })
      .getByRole("tab", { exact: true, name: "History" })
      .click();
    const history = page.getByTestId("scheduled-task-fire-history-panel");
    await expect(history).toBeVisible();
    await expect(history).toContainText("Manual fire");
    await expect(history).toContainText(`Open run #${runId}`);
    await expect(history).toContainText("scheduledDateTime");
    await expect(history).toContainText("scheduledLocalTime");

    await page.goto("/scheduled-tasks");
    await page.getByLabel("Search scheduled tasks").fill(scheduleName);
    const row = page.getByRole("row").filter({ hasText: scheduleName });
    await expect(row).toBeVisible();
    await expect(row).toContainText(`Latest run: #${runId}`);
    const latestRunLink = row.getByTestId("scheduled-task-row-action-open-latest-run");
    await expect(latestRunLink).toHaveAttribute("href", `/runs/${runId}`);
    await latestRunLink.click();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(page.getByTestId("runs-detail-status")).toContainText("succeeded", {
      timeout: 15_000,
    });
  });
});
