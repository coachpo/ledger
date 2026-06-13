import {
  expect,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";

function packageManifest(packageKey: string, modelKey: string, agentKey: string, workflowKey: string) {
  return [
    "apiVersion: signaldeck.workflowPackage/v1",
    "kind: WorkflowPackage",
    "metadata:",
    `  key: ${packageKey}`,
    `  name: E2E Memory Admin ${packageKey}`,
    "  description: Memory admin E2E fixture.",
    "spec:",
    "  inputs:",
    "    type: object",
    "    properties:",
    "      ticker:",
    "        type: string",
    "    required: [ticker]",
    "  outputSchemas:",
    "    - key: memory_admin_output",
    "      name: Memory Admin Output",
    "      jsonSchema:",
    "        type: object",
    "        properties:",
    "          summary:",
    "            type: string",
    "        required: [summary]",
    "  agents:",
    `    - key: ${agentKey}`,
    `      name: ${agentKey}`,
    `      modelConnection: ${modelKey}`,
    "      systemPrompt: Return deterministic JSON.",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      outputSchema: memory_admin_output",
    "  workflows:",
    `    - key: ${workflowKey}`,
    `      name: ${workflowKey}`,
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      flow:",
    "        kind: step",
    "        id: memory_admin_step",
    "        slot: summary",
    `        uses: ${agentKey}`,
    "        with:",
    "          ticker: ${{ inputs.ticker }}",
    "      output:",
    "        from: ${{ nodes.memory_admin_step.outputs.summary }}",
    "",
  ].join("\n");
}

async function seedModelConnection(request: APIRequestContext, key: string) {
  const payload = {
    key,
    name: `E2E memory fake provider model ${key}`,
    description: "Fake provider model connection for memory admin E2E.",
    baseUrl: FAKE_PROVIDER_BASE_URL,
    modelId: "fake-strict-schema",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-memory-fake-provider",
  };

  const response = await request.post(`${PLATFORM_API_BASE}/model-connections`, {
    data: payload,
  });
  expect(response.status()).toBe(201);
}

async function seedRun(
  request: APIRequestContext,
  packageKey: string,
  workflowKey: string,
  agentKey: string,
) {
  const modelKey = `${packageKey}_model`;
  await seedModelConnection(request, modelKey);
  const createResponse = await request.post(`${PLATFORM_API_BASE}/workflow-packages`, {
    data: { manifestSource: packageManifest(packageKey, modelKey, agentKey, workflowKey) },
  });
  expect(createResponse.status()).toBe(201);
  const workflowPackage = await createResponse.json();

  const launchResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages/${workflowPackage.id}/launches`,
    { data: { workflowKey, parameters: { ticker: "AAPL" } } },
  );
  expect(launchResponse.status()).toBe(201);
  const launch = await launchResponse.json();

  return { packageId: Number(workflowPackage.id), runId: Number(launch.id) };
}

async function createAdminMemory(
  request: APIRequestContext,
  options: {
    agentKey: string;
    content: string;
    kind?: string;
    packageKey: string;
    runId: number;
    status?: "pending" | "resolved" | "expired";
    summary: string;
    workflowKey: string;
  },
) {
  const response = await request.post(`${PLATFORM_API_BASE}/memory/admin/entries`, {
    data: {
      content: options.content,
      kind: options.kind ?? "note",
      provenance: {
        agentKey: options.agentKey,
        agentVersion: 1,
        createdByType: "operator",
        runId: options.runId,
        workflowKey: options.workflowKey,
      },
      scope: { scopeKey: options.packageKey, scopeType: "package" },
      status: options.status ?? "resolved",
      subjectRefs: [{ id: options.packageKey, kind: "package", label: options.packageKey }],
      summary: options.summary,
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function expectSingleRouteMain(
  page: Page,
  testId: string,
  shellMode: string,
  widthMode = "full",
) {
  const main = page.getByRole("main");
  await expect(main).toHaveCount(1);
  await expect(main).toHaveAttribute("data-testid", testId);
  await expect(main).toHaveAttribute("data-route-shell-mode", shellMode);
  await expect(main).toHaveAttribute("data-route-width-mode", widthMode);
}

async function expectNoDocumentOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
}

async function expectMemoryInspectorStartsInViewport(page: Page) {
  const metrics = await page
    .getByTestId("memory-split-inspector")
    .evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return {
        bottom: rect.bottom,
        height: rect.height,
        top: rect.top,
        viewportHeight: window.innerHeight,
      };
    });

  expect(metrics.top).toBeGreaterThanOrEqual(0);
  expect(metrics.top).toBeLessThan(metrics.viewportHeight);
  expect(metrics.bottom).toBeGreaterThan(metrics.top);
  expect(metrics.height).toBeGreaterThan(200);
}

function collectPanelLayoutWarnings(page: Page) {
  const warnings: string[] = [];
  page.on("console", (message) => {
    if (
      message.type() === "warning" &&
      message.text().includes("Invalid layout total size")
    ) {
      warnings.push(message.text());
    }
  });
  return warnings;
}

async function chooseSelectOption(page: Page, owner: Locator, label: string, option: string) {
  const combobox = owner.getByRole("combobox", { name: label });
  await combobox.click();
  await page.getByRole("option", { name: option }).click();
  await expect(combobox).toContainText(option);
}

async function expectNoRetiredMemoryGates(page: Page) {
  const memoryPage = page.getByTestId("memory-list-page");
  const text = await memoryPage.innerText();
  for (const pieces of [
    ["package", "context"],
    ["private", "scope"],
    ["explicit", "scope"],
    ["Access", "context", "required"],
    ["Private", "scope", "required"],
  ]) {
    expect(text).not.toContain(pieces.join(" "));
  }
  await expect(page.getByTestId(["memory", "access", "required"].join("-"))).toHaveCount(0);
  await expect(page.getByTestId(["memory", "explicit", "scope", "required"].join("-"))).toHaveCount(0);
}

test.describe("memory admin workspace", () => {
  test("manages canonical memory through trusted operator admin flows", async ({
    page,
    request,
  }) => {
    const suffix = `${Date.now()}_${test.info().parallelIndex}`;
    const alphaPackageKey = `e2e_memory_alpha_${suffix}`;
    const betaPackageKey = `e2e_memory_beta_${suffix}`;
    const alphaWorkflowKey = `alpha_memory_flow_${suffix}`;
    const betaWorkflowKey = `beta_memory_flow_${suffix}`;
    const alphaAgentKey = `alpha_memory_agent_${suffix}`;
    const betaAgentKey = `beta_memory_agent_${suffix}`;
    const panelLayoutWarnings = collectPanelLayoutWarnings(page);
    const memoryRequests: string[] = [];

    page.on("request", (browserRequest) => {
      const url = new URL(browserRequest.url());
      if (url.hostname === "127.0.0.1" && url.port === "8001" && url.pathname.startsWith("/api/memory")) {
        memoryRequests.push(`${browserRequest.method()} ${url.pathname}`);
      }
    });

    const alphaRun = await seedRun(request, alphaPackageKey, alphaWorkflowKey, alphaAgentKey);
    const betaRun = await seedRun(request, betaPackageKey, betaWorkflowKey, betaAgentKey);
    const betaMemory = await createAdminMemory(request, {
      agentKey: betaAgentKey,
      content: "Beta cross-package operator memory remains visible by default.",
      kind: "decision",
      packageKey: betaPackageKey,
      runId: betaRun.runId,
      status: "pending",
      summary: "Beta admin memory",
      workflowKey: betaWorkflowKey,
    });

    await page.setViewportSize({ width: 1280, height: 760 });
    await page.goto("/memory");

    await expectSingleRouteMain(page, "route-memory-list", "fullHeight");
    await expect(page.getByTestId("memory-list-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
    await expect(page.getByTestId("memory-admin-notice")).toContainText(
      "trusted local operator console",
    );
    await expect(page.getByTestId("memory-admin-notice")).toContainText(
      "Mixed package rows are intentional",
    );
    await expect(page.getByTestId(`memory-row-${betaMemory.memoryId}`)).toContainText(
      "Beta admin memory",
    );
    await expect(page.getByTestId(`memory-row-${betaMemory.memoryId}`)).toContainText(
      "pending",
    );
    await expectNoRetiredMemoryGates(page);
    expect(memoryRequests).toContain("GET /api/memory/admin/entries");
    expect(memoryRequests).not.toContain("POST /api/memory");

    const filters = page.getByTestId("memory-admin-filter-controls");
    await filters.getByLabel("Package key").fill(betaPackageKey);
    await expect(page.getByTestId(`memory-row-${betaMemory.memoryId}`)).toBeVisible();
    await expect(page.getByText("No memory entries match these filters")).toHaveCount(0);
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(filters.getByLabel("Package key")).toHaveValue("");
    await expect(page.getByTestId(`memory-row-${betaMemory.memoryId}`)).toBeVisible();

    await page.getByRole("button", { name: "Create memory" }).click();
    const createDialog = page.getByRole("dialog");
    await expect(createDialog).toContainText("Resolved memory in a matching scope");
    await expect(createDialog.getByRole("combobox", { name: "Initial status" })).toContainText(
      "Resolved",
    );
    await createDialog.getByLabel("Summary").fill("Alpha resolved operator memory");
    await createDialog.getByLabel("Kind", { exact: true }).fill("insight");
    await createDialog.getByLabel("Package key").fill(alphaPackageKey);
    await createDialog.getByLabel("Workflow key").fill(alphaWorkflowKey);
    await createDialog.getByLabel("Agent key").fill(alphaAgentKey);
    await createDialog.getByLabel("Run id").fill(String(alphaRun.runId));
    await createDialog.getByLabel("Scope key").fill(alphaPackageKey);
    await createDialog.getByLabel("Subject kind").fill("symbol");
    await createDialog.getByLabel("Subject id").fill("AAPL");
    await createDialog.getByLabel("Subject label").fill("Apple");
    await createDialog
      .getByLabel("Content")
      .fill("Alpha resolved memory created from the admin browser flow.");
    await createDialog.getByRole("button", { name: "Create memory" }).click();

    await expect(page).toHaveURL(/\/memory\?memoryId=/);
    const createdMemoryId = new URL(page.url()).searchParams.get("memoryId");
    expect(createdMemoryId).toBeTruthy();
    const createdRow = page.getByTestId(`memory-row-${createdMemoryId}`);
    await expect(createdRow).toContainText("Alpha resolved operator memory");
    await expect(createdRow).toContainText("resolved");
    await expect(createdRow).toContainText(`Package ${alphaPackageKey}`);
    await expect(page.getByTestId("memory-split-inspector")).toHaveAttribute(
      "data-inspector-state",
      "open",
    );
    await expectMemoryInspectorStartsInViewport(page);
    await expect(page.getByTestId("memory-detail-panel")).toContainText(
      "Alpha resolved memory created from the admin browser flow.",
    );
    await expect(page.getByTestId("memory-detail-panel")).toContainText(
      `operator · local-instance-operator@1 · ${alphaWorkflowKey} · run #${alphaRun.runId}`,
    );

    await page.getByRole("button", { name: "Revise" }).click();
    const revisionDialog = page.getByRole("dialog");
    await revisionDialog.getByLabel("Revision summary").fill("Alpha revised operator memory");
    await revisionDialog
      .getByLabel("Revision content")
      .fill("Alpha revised memory body with history evidence.");
    await revisionDialog.getByRole("button", { name: "Create revision" }).click();
    await expect(revisionDialog).toHaveCount(0);
    await page.getByRole("tab", { name: "Revisions" }).click();
    await expect(page.getByTestId("memory-revisions-panel")).toContainText("v2");
    await expect(page.getByTestId("memory-revisions-panel")).toContainText(
      "Alpha revised operator memory",
    );

    await page.getByRole("tab", { name: "Audit events" }).click();
    await expect(page.getByTestId("memory-events-panel")).toContainText("operator_created");
    await expect(page.getByTestId("memory-events-panel")).toContainText("operator_revised");

    await page.getByRole("tab", { name: "Detail" }).click();
    const detailPanel = page.getByTestId("memory-detail-panel");
    await chooseSelectOption(page, detailPanel, "New status", "Expired");
    await detailPanel.getByLabel("Status summary").fill("No longer current for runtime lookup");
    await detailPanel.getByRole("button", { name: "Update status" }).click();
    await expect(detailPanel).toContainText("expired");

    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(page.getByTestId(`memory-row-${createdMemoryId}`)).toContainText("expired");
    await expect(page.getByTestId(`memory-row-${createdMemoryId}`)).toBeVisible();
    await expect(page.getByTestId(`memory-row-${betaMemory.memoryId}`)).toBeVisible();
    await filters.getByLabel("Search canonical memory").fill("history evidence");
    await expect(page.getByTestId(`memory-row-${createdMemoryId}`)).toBeVisible();
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(filters.getByLabel("Search canonical memory")).toHaveValue("");

    await expectNoRetiredMemoryGates(page);
    await expect(page.getByTestId("nav-memory")).toContainText("Memory Admin");
    await expectNoDocumentOverflow(page);
    expect(panelLayoutWarnings).toEqual([]);
  });
});
