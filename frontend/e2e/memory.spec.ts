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
const RETIRED_WORKFLOW_LOOKUP_COPY =
  "Workflow-visible memory in a matching scope may appear in future workflow lookup; workflow-hidden memory remains visible here for operators but is excluded from runtime lookup.";

function packageManifest(
  packageKey: string,
  modelKey: string,
  agentKey: string,
  workflowKey: string,
) {
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

  const response = await request.post(
    `${PLATFORM_API_BASE}/model-connections`,
    {
      data: payload,
    },
  );
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
  const createResponse = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages`,
    {
      data: {
        manifestSource: packageManifest(
          packageKey,
          modelKey,
          agentKey,
          workflowKey,
        ),
      },
    },
  );
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
    summary: string;
    visibleToWorkflow?: boolean;
    workflowKey: string;
  },
) {
  const response = await request.post(
    `${PLATFORM_API_BASE}/memory/admin/entries`,
    {
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
        visibleToWorkflow: options.visibleToWorkflow,
        subjectRefs: [
          {
            id: options.packageKey,
            kind: "package",
            label: options.packageKey,
          },
        ],
        summary: options.summary,
      },
    },
  );
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

async function chooseSelectOption(
  page: Page,
  owner: Locator,
  label: string,
  option: string,
) {
  const combobox = owner.getByRole("combobox", { name: label });
  await combobox.click();
  await page.getByRole("option", { name: option }).click();
  await expect(combobox).toContainText(option);
}

async function expectNoRetiredLifecycleLabels(owner: Locator) {
  await expect(owner.getByText(/\b(pending|approved|archived)\b/i)).toHaveCount(
    0,
  );
  await expect(
    owner.getByText(/\b(initial status|new status|update status)\b/i),
  ).toHaveCount(0);
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
  await expect(
    page.getByTestId(["memory", "access", "required"].join("-")),
  ).toHaveCount(0);
  await expect(
    page.getByTestId(["memory", "explicit", "scope", "required"].join("-")),
  ).toHaveCount(0);
}

async function expectNoMemoryBulkDeleteControls(owner: Locator) {
  await expect(owner.getByRole("checkbox")).toHaveCount(0);
  await expect(
    owner.getByRole("button", { name: /delete selected/i }),
  ).toHaveCount(0);
  await expect(owner.getByRole("button", { name: /bulk delete/i })).toHaveCount(
    0,
  );
  await expect(
    owner.getByText(/\b(delete selected|bulk delete|selected memories)\b/i),
  ).toHaveCount(0);
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
    const memoryRequests: string[] = [];

    page.on("request", (browserRequest) => {
      const url = new URL(browserRequest.url());
      if (
        url.hostname === "127.0.0.1" &&
        url.port === "8001" &&
        url.pathname.startsWith("/api/memory")
      ) {
        memoryRequests.push(
          `${browserRequest.method()} ${url.pathname}${url.search}`,
        );
      }
    });

    const alphaRun = await seedRun(
      request,
      alphaPackageKey,
      alphaWorkflowKey,
      alphaAgentKey,
    );
    const betaRun = await seedRun(
      request,
      betaPackageKey,
      betaWorkflowKey,
      betaAgentKey,
    );
    const betaMemory = await createAdminMemory(request, {
      agentKey: betaAgentKey,
      content: "Beta cross-package operator memory remains hidden by request.",
      kind: "decision",
      packageKey: betaPackageKey,
      runId: betaRun.runId,
      summary: "Beta hidden admin memory",
      visibleToWorkflow: false,
      workflowKey: betaWorkflowKey,
    });

    await page.setViewportSize({ width: 1280, height: 760 });
    await page.goto("/memory");

    await expectSingleRouteMain(page, "route-memory-list", "scroll", "wide");
    await expect(page.getByTestId("memory-list-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
    await expect(page.getByTestId("memory-admin-notice")).toContainText(
      "trusted local operator console",
    );
    await expect(page.getByTestId("memory-admin-notice")).not.toContainText(
      "Mixed package rows are intentional",
    );
    await expect(
      page.getByTestId("workspace-page-shell-context").getByRole("button", {
        name: "Create memory",
      }),
    ).toBeVisible();
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toContainText("Beta hidden admin memory");
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toContainText("Workflow hidden");
    await expectNoRetiredLifecycleLabels(page.getByTestId("memory-list-page"));
    await expectNoRetiredMemoryGates(page);
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.startsWith("GET /api/memory/admin/entries"),
      ),
    ).toBe(true);
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.startsWith("POST /api/memory"),
      ),
    ).toBe(false);

    const filters = page.getByTestId("memory-admin-filter-controls");
    await filters.getByLabel("Package key").fill(betaPackageKey);
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toBeVisible();
    await expect(
      page.getByText("No memory entries match these filters"),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(filters.getByLabel("Package key")).toHaveValue("");
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toBeVisible();
    await chooseSelectOption(
      page,
      filters,
      "Workflow visibility",
      "Workflow visible",
    );
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toHaveCount(0);
    await chooseSelectOption(
      page,
      filters,
      "Workflow visibility",
      "Workflow hidden",
    );
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toBeVisible();
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.includes("visibleToWorkflow=true"),
      ),
    ).toBe(true);
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.includes("visibleToWorkflow=false"),
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(
      filters.getByRole("combobox", { name: "Workflow visibility" }),
    ).toContainText("All");

    await page.getByRole("button", { name: "Create memory" }).click();
    const createDialog = page.getByRole("dialog");
    await expect(createDialog).not.toContainText("Create operator memory");
    await expect(createDialog).not.toContainText(
      "Approved memory in a matching scope",
    );
    await expect(createDialog).toContainText("workflow visibility");
    await expect(
      createDialog.getByRole("combobox", {
        name: "Initial workflow visibility",
      }),
    ).toContainText("Workflow visible");
    await expectNoRetiredLifecycleLabels(createDialog);
    await createDialog
      .getByLabel("Summary")
      .fill("Alpha workflow-visible operator memory");
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
      .fill(
        "Alpha workflow-visible memory created from the admin browser flow.",
      );
    await createDialog.getByRole("button", { name: "Create memory" }).click();

    await expect(page).toHaveURL(/\/memory\/[^/?]+$/);
    const createdUrlParts = page.url().split("/");
    const createdMemoryId = createdUrlParts[createdUrlParts.length - 1];
    expect(createdMemoryId).toBeTruthy();
    await expectSingleRouteMain(page, "route-memory-detail", "scroll", "wide");
    await expect(page.getByTestId("memory-detail-page")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Alpha workflow-visible operator memory",
      }),
    ).toBeVisible();
    const detailHeader = page.getByTestId("workspace-page-shell-context");
    const initialDetailPanel = page.getByTestId("memory-detail-panel");
    await expect(initialDetailPanel).toContainText(
      "Alpha workflow-visible memory created from the admin browser flow.",
    );
    await expect(detailHeader).not.toContainText(createdMemoryId);
    await expect(detailHeader).not.toContainText(`Package ${alphaPackageKey}`);
    await expect(initialDetailPanel).toContainText("Memory");
    await expect(initialDetailPanel).toContainText(createdMemoryId);
    await expect(initialDetailPanel).toContainText("Workflow visible");
    await expect(initialDetailPanel).toContainText(`Package ${alphaPackageKey}`);
    await expect(page.getByTestId("memory-detail-page")).not.toContainText(
      RETIRED_WORKFLOW_LOOKUP_COPY,
    );
    await expectNoRetiredLifecycleLabels(
      page.getByTestId("memory-detail-page"),
    );
    await expect(initialDetailPanel).toContainText(
      `operator · local-instance-operator@1 · ${alphaWorkflowKey} · run #${alphaRun.runId}`,
    );
    await expect(
      page
        .getByTestId("memory-detail-page")
        .getByRole("link", { name: "Memory Admin" }),
    ).toHaveAttribute("href", "/memory");

    await page.getByRole("button", { name: "Revise" }).click();
    const revisionDialog = page.getByRole("dialog");
    await expect(revisionDialog).not.toContainText(RETIRED_WORKFLOW_LOOKUP_COPY);
    await revisionDialog
      .getByLabel("Revision summary")
      .fill("Alpha revised operator memory");
    await revisionDialog
      .getByLabel("Revision content")
      .fill("Alpha revised memory body with history evidence.");
    await revisionDialog
      .getByRole("button", { name: "Create revision" })
      .click();
    await expect(revisionDialog).toHaveCount(0);
    await page.getByRole("tab", { name: "Revisions" }).click();
    await expect(page.getByTestId("memory-revisions-panel")).toContainText(
      "v2",
    );
    await expect(page.getByTestId("memory-revisions-panel")).toContainText(
      "Alpha revised operator memory",
    );

    await page.getByRole("tab", { name: "Audit events" }).click();
    await expect(page.getByTestId("memory-events-panel")).toContainText(
      "operator_created",
    );
    await expect(page.getByTestId("memory-events-panel")).toContainText(
      "operator_revised",
    );

    await page.getByRole("tab", { name: "Detail" }).click();
    const detailPanel = page.getByTestId("memory-detail-panel");
    await chooseSelectOption(
      page,
      detailPanel,
      "New workflow visibility",
      "Workflow hidden",
    );
    await detailPanel
      .getByLabel("Visibility summary")
      .fill("No longer current for runtime lookup");
    await detailPanel
      .getByRole("button", { name: "Update workflow visibility" })
      .click();
    await expect(detailPanel).toContainText("Workflow hidden");
    await expectNoRetiredLifecycleLabels(
      page.getByTestId("memory-detail-page"),
    );
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.includes(
          `/memory/admin/entries/${createdMemoryId}/workflow-visibility`,
        ),
      ),
    ).toBe(true);
    expect(
      memoryRequests.some((requestLine) => requestLine.includes("/status")),
    ).toBe(false);
    await expectNoDocumentOverflow(page);

    await page
      .getByTestId("memory-detail-page")
      .getByRole("link", { name: "Memory Admin" })
      .click();
    await expect(page).toHaveURL(/\/memory$/);
    await expectSingleRouteMain(page, "route-memory-list", "scroll", "wide");
    await expect(
      page.getByTestId(`memory-row-${createdMemoryId}`),
    ).toContainText("Workflow hidden");
    await expect(
      page.getByTestId(`memory-row-${createdMemoryId}`),
    ).toBeVisible();
    await expect(
      page.getByTestId(`memory-row-${betaMemory.memoryId}`),
    ).toBeVisible();
    const refreshedFilters = page.getByTestId("memory-admin-filter-controls");
    await refreshedFilters
      .getByLabel("Search canonical memory")
      .fill("history evidence");
    await expect(
      page.getByTestId(`memory-row-${createdMemoryId}`),
    ).toBeVisible();
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(
      refreshedFilters.getByLabel("Search canonical memory"),
    ).toHaveValue("");

    const deleteConfirmationCopy =
      "This permanently removes this memory entry and its revisions. Existing run evidence keeps snapshot memory ids, but the memory entry will no longer appear in admin search or runtime lookup.";
    const createdRow = page.getByTestId(`memory-row-${createdMemoryId}`);
    await expectNoMemoryBulkDeleteControls(page.getByTestId("memory-list-page"));
    await createdRow.getByRole("button", { name: "Delete memory" }).click();
    const listDeleteDialog = page.getByRole("alertdialog", {
      name: "Delete memory",
    });
    await expect(listDeleteDialog).toContainText(deleteConfirmationCopy);
    await listDeleteDialog.getByRole("button", { name: "Cancel" }).click();
    await expect(listDeleteDialog).toHaveCount(0);
    await expect(createdRow).toBeVisible();

    await createdRow.getByRole("link", { name: "Open detail" }).click();
    await expect(page).toHaveURL(new RegExp(`/memory/${createdMemoryId}$`));
    await expectSingleRouteMain(page, "route-memory-detail", "scroll", "wide");
    await expectNoMemoryBulkDeleteControls(page.getByTestId("memory-detail-page"));
    await page
      .getByTestId("memory-detail-page")
      .getByRole("button", { name: "Delete memory" })
      .click();
    const detailDeleteDialog = page.getByRole("alertdialog", {
      name: "Delete memory",
    });
    await expect(detailDeleteDialog).toContainText(deleteConfirmationCopy);
    await detailDeleteDialog
      .getByRole("button", { name: "Delete memory" })
      .click();
    await expect(page).toHaveURL(/\/memory$/);
    await expect(page.getByText("Memory deleted")).toBeVisible();
    await expect(page.getByTestId(`memory-row-${createdMemoryId}`)).toHaveCount(
      0,
    );
    expect(
      memoryRequests.some(
        (requestLine) =>
          requestLine ===
          `DELETE /api/memory/admin/entries/${createdMemoryId}`,
      ),
    ).toBe(true);

    const postDeleteFilters = page.getByTestId("memory-admin-filter-controls");
    await postDeleteFilters.getByLabel("Package key").fill(alphaPackageKey);
    await expect(page.getByTestId(`memory-row-${createdMemoryId}`)).toHaveCount(
      0,
    );
    await expect(
      page.getByText("No memory entries match these filters"),
    ).toBeVisible();
    await page.getByRole("button", { name: "Reset filters" }).click();

    await page.goto(`/memory/${createdMemoryId}`);
    await expectSingleRouteMain(page, "route-memory-detail", "scroll", "wide");
    await expect(page.getByTestId("memory-detail-error")).toBeVisible();
    await expect(page.getByTestId("memory-detail-error")).toContainText(
      "Unable to load memory detail",
    );
    await page.getByRole("link", { name: "Back to Memory Admin" }).click();
    await expect(page).toHaveURL(/\/memory$/);

    await expectNoRetiredLifecycleLabels(page.getByTestId("memory-list-page"));
    await expectNoRetiredMemoryGates(page);
    await expectNoMemoryBulkDeleteControls(page.getByTestId("memory-list-page"));
    await expect(page.getByTestId("nav-memory")).toContainText("Memory Admin");
    await expectNoDocumentOverflow(page);
  });
});
