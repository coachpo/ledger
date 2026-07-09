import {
  expect,
  test,
  type APIRequestContext,
  type Page,
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
      analysisTag:
        type: string
    required: [asOfDate, scheduledLocalTime, scheduledDateTime, analysisTag]
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
          analysisTag:
            type: string
        required: [asOfDate, scheduledLocalTime, scheduledDateTime, analysisTag]
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
          analysisTag:
            type: string
        required: [asOfDate, scheduledLocalTime, scheduledDateTime, analysisTag]
      flow:
        kind: step
        id: scheduled_analysis
        slot: summary
        uses: scheduled_agent
        with:
          asOfDate: \${{ inputs.asOfDate }}
          scheduledLocalTime: \${{ inputs.scheduledLocalTime }}
          scheduledDateTime: \${{ inputs.scheduledDateTime }}
          analysisTag: \${{ inputs.analysisTag }}
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
  const suffix = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
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

async function createScheduleViaApi(
  request: APIRequestContext,
  workflowPackageId: number,
  name: string,
  status: "enabled" | "paused" = "enabled",
) {
  const response = await request.post(`${PLATFORM_API_BASE}/schedules`, {
    data: {
      packageId: workflowPackageId,
      workflowKey: "scheduled_flow",
      name,
      description: "E2E list coverage schedule.",
      status,
      timezone: "America/New_York",
      recurrence: { type: "daily", atLocalTime: "09:30" },
      inputTemplate: {
        analysisTag: name,
        asOfDate: "{{fire.scheduledLocalDate}}",
        scheduledDateTime: "{{fire.scheduledLocalDateTime}}",
        scheduledLocalTime: "{{fire.scheduledLocalTime}}",
      },
      templateVars: {},
    },
  });
  const responseText = await response.text();
  expect(response.status(), responseText).toBe(201);
  return JSON.parse(responseText) as {
    id: number;
    latestRunId: number | null;
    name: string;
  };
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

async function createScheduledTask(
  page: Page,
  workflowPackageId: number,
  scheduleName: string,
) {
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

  const packageSelect = page.getByTestId("schedule-package-select");
  await packageSelect.click();
  await page.getByRole("option", { name: new RegExp(`#${workflowPackageId}$`) }).click();
  const workflowSelect = page.getByTestId("schedule-workflow-select");
  await expect(workflowSelect).toBeEnabled();
  await workflowSelect.click();
  await page.getByRole("option", { name: "Scheduled Flow" }).click();
  await expect(workflowSelect).toContainText("Scheduled Flow");
  await page.getByTestId("schedule-name").fill(scheduleName);
  const timezoneSelect = page.getByTestId("schedule-timezone-select");
  await timezoneSelect.click();
  await page.getByRole("option", { name: "America/New_York" }).click();
  await page.getByLabel("Daily local time").fill("09:30");
  await page.getByTestId("schedule-preview-scheduled-for").fill("2026-06-08T13:30");
  await page.getByLabel("Description").fill("Timezone-sensitive E2E schedule.");
  await page.getByTestId("schedule-input-template-json").fill(
    JSON.stringify(
      {
        asOfDate: "{{fire.scheduledLocalDate}}",
        analysisTag: "daily_research",
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
  await expect(preview).toContainText("2026-06-08");
  await expect(preview).toContainText("09:30");
  await expect(preview).toContainText("America/New_York");
  await expect(preview).toContainText("scheduledLocalTime");

  await page.getByTestId("schedule-save").click();
  await expect(page).toHaveURL(/\/scheduled-tasks\/\d+$/);
  const scheduleId = Number(page.url().match(/\/scheduled-tasks\/(\d+)$/)?.[1]);
  expect(Number.isInteger(scheduleId)).toBeTruthy();
  await expect(page.getByTestId("scheduled-task-detail-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: scheduleName })).toBeVisible();
  return scheduleId;
}

async function runScheduleNowAndWait(
  page: Page,
  request: APIRequestContext,
  scheduleId: number,
) {
  await page.getByTestId("schedule-run-now").click();
  await expect(page).toHaveURL(/\/runs\/\d+$/);
  const runId = Number(page.url().match(/\/runs\/(\d+)$/)?.[1]);
  expect(Number.isInteger(runId)).toBeTruthy();
  await expect(page.getByTestId("runs-detail-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: new RegExp(`Run #${runId}`) })).toBeVisible();
  const runDetail = await waitForRun(request, runId);
  expect(runDetail.status).toBe("succeeded");
  await waitForScheduleLatestRun(request, scheduleId, runId);
  return runId;
}

test.describe("scheduled tasks", () => {
  test.use({ timezoneId: "UTC" });

  test("scheduled tasks list filters, row actions, selection, and bulk delete", async ({
    page,
    request,
  }) => {
    const workflowPackage = await seedScheduledPackage(request);
    const activeSchedule = await createScheduleViaApi(
      request,
      workflowPackage.id,
      `E2E list active ${workflowPackage.id}`,
    );
    const pausedSchedule = await createScheduleViaApi(
      request,
      workflowPackage.id,
      `E2E list paused ${workflowPackage.id}`,
      "paused",
    );

    await page.goto("/scheduled-tasks");
    await expect(page.getByTestId("scheduled-tasks-list-page")).toBeVisible();
    await page.getByTestId("scheduled-tasks-filter-package").click();
    await page.getByRole("option", { name: workflowPackage.name }).click();
    await expect(page.getByTestId(`scheduled-task-row-${activeSchedule.id}`)).toBeVisible();
    await expect(page.getByTestId(`scheduled-task-row-${pausedSchedule.id}`)).toBeVisible();
    await page.getByTestId("scheduled-tasks-filter-workflow").click();
    await page.getByRole("option", { name: "Scheduled Flow" }).click();

    const activeRow = page.getByTestId(`scheduled-task-row-${activeSchedule.id}`);
    const pausedRow = page.getByTestId(`scheduled-task-row-${pausedSchedule.id}`);
    await expect(activeRow).toContainText(activeSchedule.name);
    await expect(pausedRow).toContainText(pausedSchedule.name);

    const [runNowResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/schedules/${activeSchedule.id}/run-now`) &&
          response.request().method() === "POST",
      ),
      activeRow
        .getByRole("button", { name: `Run schedule ${activeSchedule.name} now` })
        .click(),
    ]);
    expect(runNowResponse.ok()).toBeTruthy();

    const [pauseResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/schedules/${activeSchedule.id}`) &&
          response.request().method() === "PATCH",
      ),
      activeRow
        .getByRole("button", { name: `Pause schedule ${activeSchedule.name}` })
        .click(),
    ]);
    expect(pauseResponse.ok()).toBeTruthy();
    await expect(
      activeRow.getByRole("button", { name: `Resume schedule ${activeSchedule.name}` }),
    ).toBeVisible();

    const [resumePausedResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/schedules/${pausedSchedule.id}`) &&
          response.request().method() === "PATCH",
      ),
      pausedRow
        .getByRole("button", { name: `Resume schedule ${pausedSchedule.name}` })
        .click(),
    ]);
    expect(resumePausedResponse.ok()).toBeTruthy();
    await expect(
      pausedRow.getByRole("button", { name: `Pause schedule ${pausedSchedule.name}` }),
    ).toBeVisible();

    await pausedRow
      .getByRole("checkbox", { name: `Select scheduled task ${pausedSchedule.name}` })
      .click();
    await expect(page.getByTestId("scheduled-tasks-bulk-actions")).toContainText(
      "1 of 2 scheduled tasks selected",
    );
    await page.getByRole("button", { name: "Delete selected" }).click();
    const deleteDialog = page.getByRole("alertdialog");
    await expect(deleteDialog).toContainText("Delete selected scheduled tasks");
    await deleteDialog.getByRole("button", { name: "Delete selected" }).click();
    await expect
      .poll(async () => {
        const response = await request.get(
          `${PLATFORM_API_BASE}/schedules/${pausedSchedule.id}`,
        );
        return response.status();
      })
      .toBe(404);
  });

  test("scheduled tasks create, preview, pause, run now, history, and latest run link", async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000);

    const workflowPackage = await seedScheduledPackage(request);
    const scheduleName = `E2E scheduled tasks ${workflowPackage.id}`;

    const scheduleId = await createScheduledTask(
      page,
      workflowPackage.id,
      scheduleName,
    );
    await expect(page.getByTestId("scheduled-task-detail-status-enabled")).toBeVisible();
    await expect(page.getByTestId("scheduled-task-detail-next-run-summary")).toContainText(
      "America/New_York",
    );
    await page.getByRole("tab", { name: "Inputs" }).click();
    const inputTemplate = page.getByLabel("Scheduled input template JSON");
    await expect(inputTemplate).toBeVisible();
    await inputTemplate.fill("[]");
    await expect(
      page.getByTestId("scheduled-input-json-validation-feedback"),
    ).toContainText("Scheduled input template JSON must be a valid object.");
    await expect(page.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    await inputTemplate.fill(
      JSON.stringify({ analysisTag: "{{inputs.ticker}}" }, null, 2),
    );
    await expect(
      page.getByTestId("scheduled-input-json-validation-feedback"),
    ).toContainText("Unsupported placeholder");
    await expect(
      page.getByTestId("scheduled-input-json-validation-feedback"),
    ).toContainText("inputs.ticker");
    await expect(page.getByRole("button", { name: "Preview next run" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Save inputs" })).toBeDisabled();
    await inputTemplate.fill(
      JSON.stringify({ extra: "{{fire.scheduledLocalDate}}" }, null, 2),
    );
    await page.getByRole("button", { name: "Preview next run" }).click();
    await expect(page.getByTestId("schedule-input-preview")).toContainText("Not ready");
    await expect(
      page.getByTestId("scheduled-input-preview-validation-feedback"),
    ).toContainText("asOfDate");

    const [rejectedSavePreviewResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes("/api/schedules/preview") &&
          response.request().method() === "POST",
      ),
      page.getByRole("button", { name: "Save inputs" }).click(),
    ]);
    expect(rejectedSavePreviewResponse.ok()).toBeTruthy();
    await expect(page.getByTestId("schedule-input-preview")).toContainText("Not ready");
    const savedPreviewAfterRejectedSave = await request.post(
      `${PLATFORM_API_BASE}/schedules/${scheduleId}/preview`,
    );
    expect(savedPreviewAfterRejectedSave.ok()).toBeTruthy();
    expect((await savedPreviewAfterRejectedSave.json()).renderedParameters).toMatchObject({
      analysisTag: "daily_research",
    });

    await inputTemplate.fill(
      JSON.stringify(
        {
          analysisTag: "detail_preview",
          asOfDate: "{{fire.scheduledLocalDate}}",
          scheduledDateTime: "{{fire.scheduledLocalDateTime}}",
          scheduledLocalTime: "{{fire.scheduledLocalTime}}",
        },
        null,
        2,
      ),
    );
    await page.getByRole("button", { name: "Preview next run" }).click();
    const inputPreview = page.getByTestId("schedule-input-preview");
    await expect(inputPreview).toContainText("Ready");
    await expect(inputPreview).toContainText("detail_preview");
    const [saveResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/schedules/${scheduleId}`) &&
          response.request().method() === "PATCH",
      ),
      page.getByRole("button", { name: "Save inputs" }).click(),
    ]);
    expect(saveResponse.ok()).toBeTruthy();

    const pauseResponse = await request.patch(
      `${PLATFORM_API_BASE}/schedules/${scheduleId}`,
      { data: { status: "paused" } },
    );
    expect(pauseResponse.ok()).toBeTruthy();
    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-status-paused")).toBeVisible();
    await expect(page.getByTestId("scheduled-task-detail-health-summary")).toContainText("Schedule paused");
    const enableResponse = await request.patch(
      `${PLATFORM_API_BASE}/schedules/${scheduleId}`,
      { data: { status: "enabled" } },
    );
    expect(enableResponse.ok()).toBeTruthy();
    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-status-enabled")).toBeVisible();

    const runId = await runScheduleNowAndWait(page, request, scheduleId);
    const runResponse = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
    const runDetail = await runResponse.json();
    expect(runDetail.input).toMatchObject({
      analysisTag: "detail_preview",
    });

    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-page")).toBeVisible();
    await page.getByRole("tab", { name: "Runs" }).click();
    const history = page.getByTestId("scheduled-task-detail-tab-runs");
    await expect(history).toBeVisible();
    await expect(history).toContainText("Manual fire");
    await expect(history).toContainText(`Open run #${runId}`);
    const latestRunLink = history.getByRole("link", {
      name: `Open run #${runId}`,
    });
    await expect(latestRunLink).toHaveAttribute("href", `/runs/${runId}`);
    await latestRunLink.click();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: new RegExp(`Run #${runId}`) }),
    ).toContainText("succeeded", { timeout: 15_000 });
  });

  test("scheduled tasks hard delete removes schedule detail and preserves linked run detail", async ({
    page,
    request,
  }) => {
    const workflowPackage = await seedScheduledPackage(request);
    const scheduleName = `E2E scheduled tasks delete ${workflowPackage.id}`;
    const scheduleId = await createScheduledTask(
      page,
      workflowPackage.id,
      scheduleName,
    );

    const runId = await runScheduleNowAndWait(page, request, scheduleId);

    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-page")).toBeVisible();

    const header = page.getByTestId("scheduled-task-detail-header");
    await header.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await expect(page.getByRole("alertdialog")).toContainText(
      "Delete scheduled task",
    );
    await page.getByRole("button", { name: "Delete scheduled task" }).click();

    await expect(page).toHaveURL(/\/scheduled-tasks$/);
    await expect(page.getByTestId("scheduled-tasks-list-page")).toBeVisible();

    await expect
      .poll(async () => {
        const response = await request.get(
          `${PLATFORM_API_BASE}/schedules/${scheduleId}`,
        );
        return response.status();
      })
      .toBe(404);
    const runResponse = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
    expect(runResponse.status()).toBe(200);

    await page.goto(`/scheduled-tasks/${scheduleId}`);
    await expect(page.getByTestId("scheduled-task-detail-not-found")).toBeVisible();
    await expect(page.getByText("Scheduled task not found")).toBeVisible();

    await page.goto(`/runs/${runId}`);
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: new RegExp(`Run #${runId}`) }),
    ).toBeVisible();
  });
});
