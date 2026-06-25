import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { parse } from "yaml";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";

function packageManifest(
  packageKey: string,
  modelKey: string,
  agentName = "Package Analyst",
) {
  return [
    "apiVersion: signaldeck.workflowPackage/v1",
    "kind: WorkflowPackage",
    "metadata:",
    `  key: ${packageKey}`,
    `  name: E2E Package ${packageKey}`,
    "  description: Package-first E2E fixture.",
    "spec:",
    "  inputs:",
    "    type: object",
    "    properties:",
    "      ticker:",
    "        type: string",
    "    required: [ticker]",
    "  capabilityProfiles:",
    "    - key: quote_tools",
    "      name: Quote Tools",
    "      toolKeys:",
    "        - signaldeck.finance.market_data.quote_lookup",
    "  outputSchemas:",
    "    - key: advisory_output",
    "      name: Advisory Output",
    "      jsonSchema:",
    "        type: object",
    "        properties:",
    "          summary:",
    "            type: string",
    "        required: [summary]",
    "  agents:",
    "    - key: package_analyst",
    `      name: ${agentName}`,
    `      modelConnection: ${modelKey}`,
    "      systemPrompt: Return deterministic JSON.",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      outputSchema: advisory_output",
    "      capabilityProfiles: [quote_tools]",
    "  workflows:",
    "    - key: advisory_flow",
    "      name: Advisory Flow",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      flow:",
    "        kind: step",
    "        id: package_analysis",
    "        slot: decision",
    "        uses: package_analyst",
    "        with:",
    "          ticker: ${{ inputs.ticker }}",
    "      output:",
    "        from: ${{ nodes.package_analysis.outputs.decision }}",
    "",
  ].join("\n");
}

function runtimeProfilePackageManifest(packageKey: string, modelKey: string) {
  return packageManifest(packageKey, modelKey)
    .replace(
      "  capabilityProfiles:\n    - key: quote_tools\n      name: Quote Tools\n      toolKeys:\n        - signaldeck.finance.market_data.quote_lookup\n",
      "  capabilityProfiles: []\n",
    )
    .replace(
      "      capabilityProfiles: [quote_tools]",
      "      capabilityProfiles: []",
    );
}

function wideOutputPackageManifest(
  packageKey: string,
  modelKey: string,
  wideFieldKey: string,
) {
  return [
    "apiVersion: signaldeck.workflowPackage/v1",
    "kind: WorkflowPackage",
    "metadata:",
    `  key: ${packageKey}`,
    `  name: E2E Wide Output Package ${packageKey}`,
    "spec:",
    "  inputs:",
    "    type: object",
    "    properties: {}",
    "  outputSchemas:",
    "    - key: wide_output",
    "      name: Wide Output",
    "      jsonSchema:",
    "        type: object",
    "        properties:",
    `          ? ${wideFieldKey}`,
    "          :",
    "            type: string",
    "        required:",
    `          - ${wideFieldKey}`,
    "  agents:",
    "    - key: wide_analyst",
    "      name: Wide Analyst",
    `      modelConnection: ${modelKey}`,
    "      systemPrompt: Return deterministic JSON.",
    "      inputSchema:",
    "        type: object",
    "        properties: {}",
    "      outputSchema: wide_output",
    "  workflows:",
    "    - key: wide_flow",
    "      name: Wide Flow",
    "      inputSchema:",
    "        type: object",
    "        properties: {}",
    "      flow:",
    "        kind: step",
    "        id: wide_analysis",
    "        slot: evidence",
    "        uses: wide_analyst",
    "        with: {}",
    "      output:",
    "        from: ${{ nodes.wide_analysis.outputs.evidence }}",
    "",
  ].join("\n");
}

async function seedModelConnection(request: APIRequestContext, key: string) {
  return seedModelConnectionPayload(request, {
    key,
    name: `E2E fake provider model ${key}`,
    description: "Fake provider model connection for package-first E2E.",
    baseUrl: FAKE_PROVIDER_BASE_URL,
    modelId: "fake-strict-schema",
    reasoningEffort: "low",
    protocolProfile: "openai_responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-fake-provider",
    capabilities: {
      nativeToolCalls: capability("supported", "Native tool calls are supported."),
      strictJsonSchemaOutput: capability("supported", "Strict schema output is supported."),
    },
  });
}

async function seedModelConnectionPayload(
  request: APIRequestContext,
  payload: Record<string, unknown> & { key: string },
) {
  const {
    capabilities,
    outputStrategyPolicy: _outputStrategyPolicy,
    parallelToolCallsPolicy: _parallelToolCallsPolicy,
    reasoningPolicy: _reasoningPolicy,
    streamingPolicy: _streamingPolicy,
    ...connectionPayload
  } = payload;
  const capabilityKeys =
    capabilities && typeof capabilities === "object" && !Array.isArray(capabilities)
      ? Object.keys(capabilities)
      : [];

  const list = await request.get(`${PLATFORM_API_BASE}/model-connections`, {
    params: { status: "active" },
  });
  expect(list.ok()).toBeTruthy();
  const existing = (await list.json()).items.find(
    (item: { id: number; key: string }) => item.key === payload.key,
  );
  let connectionId: number;
  if (existing) {
    const { key: _key, ...updatePayload } = connectionPayload;
    const response = await request.patch(
      `${PLATFORM_API_BASE}/model-connections/${existing.id}`,
      { data: updatePayload },
    );
    expect(response.ok()).toBeTruthy();
    connectionId = existing.id;
  } else {
    const response = await request.post(
      `${PLATFORM_API_BASE}/model-connections`,
      { data: connectionPayload },
    );
    expect(response.ok()).toBeTruthy();
    connectionId = Number((await response.json()).id);
  }

  if (capabilityKeys.length > 0) {
    const probe = await request.post(
      `${PLATFORM_API_BASE}/model-connections/${connectionId}/capability-probe`,
      { data: { capabilityKeys, refresh: true } },
    );
    expect(probe.ok()).toBeTruthy();
  }
  return connectionId;
}

function capability(status: string, detail: string) {
  return { detail, status };
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

async function openPackageEditor(page: Page, packageId: number) {
  await page.goto(`/workflow-packages/${packageId}`);
  await expect(page.getByTestId("workflow-package-editor-shell")).toBeVisible();
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

function workflowOptionNameFromKey(workflowKey: string) {
  return workflowKey
    .split("_")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

async function selectLaunchWorkflow(page: Page, workflowKey: string) {
  const workflowSelector = page.getByRole("combobox", { name: "Workflow" });
  const workflowName = workflowOptionNameFromKey(workflowKey);
  await workflowSelector.click();
  await page.getByRole("option", { name: workflowName }).click();
  await expect(workflowSelector).toContainText(workflowName);
}

async function launchPackageFromDedicatedPage(
  page: Page,
  packageId: number,
  workflowKey: string,
  parameters: Record<string, unknown>,
) {
  await page.goto(`/workflow-packages/${packageId}/run`);
  await expect(page.getByTestId("workflow-package-launch-page")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Launch Workflow Package" }),
  ).toBeVisible();
  await expect(
    page.getByTestId("workflow-package-launch-identity"),
  ).toBeVisible();
  await expect(
    page.getByTestId("workflow-package-preflight-status"),
  ).toBeVisible();
  await expect(page.getByText("Launch readiness")).toBeVisible();
  await expect(page.getByTestId("workflow-package-launch-tab")).toBeVisible();

  const launchButton = page.getByRole("button", { name: "Launch Run" });
  const runtimeInputsPreview = page.getByLabel("Runtime inputs JSON");
  await expect(runtimeInputsPreview).toBeVisible();
  await selectLaunchWorkflow(page, workflowKey);
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByTestId("workflow-package-preflight-status")).toContainText(
    "Preflight ready",
  );
  for (const [fieldName, value] of Object.entries(parameters)) {
    await page.getByRole("textbox", { name: fieldName }).fill(String(value));
  }
  await expect(runtimeInputsPreview).toHaveValue(JSON.stringify(parameters, null, 2));
  await expect(launchButton).toBeEnabled();
  await launchButton.click();

  await expect(page).toHaveURL(/\/runs\/\d+$/, { timeout: 15_000 });
  await expect(page.getByTestId("runs-detail-page")).toBeVisible();

  const runId = Number(new URL(page.url()).pathname.split("/").pop());
  expect(Number.isFinite(runId)).toBeTruthy();
  return runId;
}

test.describe("Workflow packages", () => {
  test("scheduler worker from backend launcher drains queued workflow package runs", async ({
    request,
  }) => {
    const suffix = Date.now();
    const packageKey = `e2e_scheduler_worker_${suffix}`;
    const modelKey = `e2e_scheduler_model_${suffix}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: { manifestSource: packageManifest(packageKey, modelKey) },
      },
    );
    expect(createResponse.status()).toBe(201);
    const created = await createResponse.json();

    const launch = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
      {
        data: { workflowKey: "advisory_flow", parameters: { ticker: "MSFT" } },
      },
    );
    expect(launch.status()).toBe(201);
    const launched = await launch.json();
    const detail = await waitForRun(request, Number(launched.id));

    expect(detail.status).toBe("succeeded");
    expect(detail.finalOutput).toMatchObject({
      summary: "fake strict schema",
    });
  });

  test("shows inventory readiness and provenance actions", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const packageKey = `e2e_inventory_${suffix}`;
    const modelKey = `e2e_inventory_model_${suffix}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: { manifestSource: packageManifest(packageKey, modelKey) },
      },
    );
    expect(createResponse.status()).toBe(201);
    const created = await createResponse.json();

    await page.goto("/workflow-packages");
    await expect(page.getByTestId("workflow-packages-list-page")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Import workflow package manifest" }),
    ).toHaveAttribute("href", "/workflow-packages/import");
    await expect(
      page.getByRole("link", { name: "Create new workflow package" }),
    ).toHaveAttribute("href", "/workflow-packages/new");
    await page.getByLabel("Search workflow packages").fill(packageKey);

    const packageRow = page.getByTestId(`workflow-packages-row-${packageKey}`);
    await expect(packageRow).toBeVisible();
    await expect(packageRow).toContainText(`E2E Package ${packageKey}`);
    await expect(packageRow).toContainText("Ready for preflight");
    await expect(packageRow.getByRole("cell").nth(4)).toContainText(/^[a-f0-9]{12}$/);
    await expect(packageRow.getByRole("cell").nth(5)).toContainText(/^[a-f0-9]{12}$/);
    const expectedCreatedDate = new Intl.DateTimeFormat("en-US", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(String(created.createdAt)));
    await expect(packageRow).toContainText(expectedCreatedDate);
    await expect(
      packageRow.getByRole("link", {
        name: `Open package E2E Package ${packageKey}`,
      }),
    ).toHaveAttribute("href", `/workflow-packages/${created.id}`);
    await expect(
      packageRow.getByRole("link", {
        name: `Launch package E2E Package ${packageKey}`,
      }),
    ).toHaveAttribute("href", `/workflow-packages/${created.id}/run`);
  });

  test("launches workflow package from dedicated run page", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const packageKey = `e2e_launch_page_${suffix}`;
    const modelKey = `e2e_launch_model_${suffix}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: { manifestSource: packageManifest(packageKey, modelKey) },
      },
    );
    expect(createResponse.status()).toBe(201);
    const created = await createResponse.json();

    const runId = await launchPackageFromDedicatedPage(
      page,
      Number(created.id),
      "advisory_flow",
      { ticker: "AAPL" },
    );
    const detail = await waitForRun(request, runId);

    expect(detail.status).toBe("succeeded");
    expect(detail.targetKind).toBe("workflowPackage");
    expect(detail.finalOutput).toMatchObject({
      summary: "fake strict schema",
    });
    expect(detail.packageProvenance).toMatchObject({
      launchSnapshot: {
        parameters: { ticker: "AAPL" },
        workflowKey: "advisory_flow",
      },
      workflowPackageKey: packageKey,
    });
    await expect(page.getByTestId("runs-detail-summary-line")).toContainText(
      "succeeded",
      { timeout: 15_000 },
    );
  });

  test("covers current-package authoring, export, import, launch, and snapshot provenance", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const packageKey = `e2e_package_${suffix}`;
    const modelKey = `e2e_model_${suffix}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: { manifestSource: packageManifest(packageKey, modelKey) },
      },
    );
    expect(createResponse.status()).toBe(201);
    const created = await createResponse.json();

    await openPackageEditor(page, Number(created.id));
    await page.getByRole("tab", { name: "Agents tab" }).click();
    await expect(page.getByTestId("workflow-package-agents-tab")).toBeVisible();

    const editedSource = packageManifest(
      packageKey,
      modelKey,
      "Edited Package Analyst",
    );
    const updateResponse = await request.patch(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}`,
      {
        data: { manifestSource: editedSource },
      },
    );
    expect(updateResponse.ok()).toBeTruthy();

    const preflight = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}/preflight`,
      {
        data: { workflowKey: "advisory_flow", parameters: { ticker: "AAPL" } },
      },
    );
    expect(preflight.ok()).toBeTruthy();
    expect(await preflight.json()).toMatchObject({
      ready: true,
      workflowKey: "advisory_flow",
    });

    const exportResponse = await request.get(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}/export`,
    );
    expect(exportResponse.ok()).toBeTruthy();
    const exported = await exportResponse.text();
    const exportedManifest = parse(exported) as {
      metadata: { key: string };
      spec: { agents: Array<Record<string, unknown>> };
    };
    const exportedAgent = exportedManifest.spec.agents[0];
    expect(exportedManifest.metadata.key).toBe(packageKey);
    expect(Object.keys(exportedManifest.spec).sort()).toEqual([
      "agents",
      "capabilityProfiles",
      "inputs",
      "mcpServers",
      "outputSchemas",
      "workflows",
    ]);
    expect(Object.keys(exportedAgent).sort()).toEqual([
      "capabilityProfiles",
      "description",
      "inputSchema",
      "key",
      "mcpServers",
      "modelConnection",
      "name",
      "outputSchema",
      "systemPrompt",
    ]);
    expect(exportedAgent.modelConnection).toBe(modelKey);

    const importedKey = `${packageKey}_imported`;
    const importResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/import`,
      {
        data: {
          manifestSource: exported.replace(
            `key: ${packageKey}`,
            `key: ${importedKey}`,
          ),
        },
      },
    );
    expect(importResponse.ok()).toBeTruthy();
    expect((await importResponse.json()).key).toBe(importedKey);

    const runId = await launchPackageFromDedicatedPage(
      page,
      Number(created.id),
      "advisory_flow",
      { ticker: "AAPL" },
    );

    const detail = await waitForRun(request, runId);
    expect(detail.status).toBe("succeeded");
    expect(detail.targetKind).toBe("workflowPackage");
    expect(detail.finalOutput).toMatchObject({
      summary: "fake strict schema",
    });
    const packageProvenance = detail.packageProvenance as Record<
      string,
      unknown
    >;
    expect(packageProvenance).toMatchObject({
      currentPackage: { available: true },
      launchSnapshot: {
        parameters: { ticker: "AAPL" },
        workflowKey: "advisory_flow",
      },
      workflowKey: "advisory_flow",
      workflowPackageKey: packageKey,
    });
    expect(packageProvenance.workflowPackageManifestHash).toEqual(
      expect.any(String),
    );
    expect(packageProvenance.workflowPackageCompiledHash).toEqual(
      expect.any(String),
    );

    const runSteps = detail.steps as Array<{
      index: number;
      invocations: Array<{
        id: number;
        persistedAt: string | null;
        slot: string;
        status: string;
      }>;
    }>;
    const forkTarget = runSteps
      .flatMap((step) =>
        step.invocations.map((invocation) => ({
          invocation,
          stepIndex: step.index,
        })),
      )
      .find(
        ({ invocation }) =>
          invocation.status === "succeeded" && invocation.persistedAt,
      );
    if (!forkTarget) {
      throw new Error(
        `Run ${runId} did not expose a persisted agent invocation to fork.`,
      );
    }
    const forkInvocationId = forkTarget.invocation.id;
    const forkStepIndex = forkTarget.stepIndex;

    await page.reload();
    await expect(page.getByTestId("runs-detail-summary-line")).toContainText(
      "succeeded",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("runs-detail-final-output")).toContainText(
      "fake strict schema",
    );
    await expect(
      page.getByRole("heading", { name: new RegExp(`Run #${runId}`) }),
    ).toContainText(packageKey);
    await expect(
      page.getByRole("link", { name: "Open current package" }),
    ).toHaveAttribute("href", `/workflow-packages/${created.id}`);

    await page.getByTestId("runs-detail-rerun").click();
    const rerunDialog = page.getByRole("dialog", {
      name: /run snapshot again/i,
    });
    await expect(rerunDialog).toBeVisible();
    await expectSharedDialogShell(page);
    await expect(rerunDialog).toContainText("Source run");
    await expect(rerunDialog).toContainText("Readiness");
    await page.getByTestId("run-rerun-submit").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);

    await page.goto(`/runs/${runId}?inspect=invocation:${forkInvocationId}`);
    const forkAction = page.getByTestId(
      `runs-invocation-${forkInvocationId}-fork-entry`,
    );
    await expect(forkAction).toContainText("Fork from this invocation");
    await forkAction.evaluate((node) => {
      node.dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    });
    const forkDialog = page.getByRole("dialog", {
      name: /fork from .+ invocation/i,
    });
    await expect(forkDialog).toBeVisible();
    await expect(
      forkDialog.getByText(`Resume at Step ${forkStepIndex}`),
    ).toBeVisible();
    await expect(
      forkDialog.getByText(`Invocation #${forkInvocationId}`),
    ).toBeVisible();
    await expect(
      forkDialog.getByText(/edits only the selected agent invocation input/i),
    ).toBeVisible();
    await expect(page.getByLabel("Target invocation input JSON")).toHaveValue(
      JSON.stringify({ ticker: "AAPL" }, null, 2),
    );
    await page.getByTestId("run-fork-submit").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
  });

  test("covers fake provider capability blockers and runtime profiles", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const noToolsModelKey = `e2e_fake_tools_disabled_${suffix}`;
    const jsonModelKey = `e2e_fake_json_object_${suffix}`;
    const strictModelKey = `e2e_fake_strict_${suffix}`;
    const noUsageModelKey = `e2e_fake_missing_usage_${suffix}`;
    const reasoningModelKey = `e2e_fake_reasoning_disabled_${suffix}`;

    await seedModelConnectionPayload(request, {
      key: noToolsModelKey,
      name: "E2E fake provider tools disabled",
      description: "Fake provider with native tool calls disabled.",
      baseUrl: FAKE_PROVIDER_BASE_URL,
      modelId: "fake-tools-disabled",
      reasoningEffort: null,
      protocolProfile: "openai_responses",
      capabilities: {
        nativeToolCalls: capability(
          "unsupported",
          "Fake provider rejects tools.",
        ),
        strictJsonSchemaOutput: capability(
          "unsupported",
          "Strict schema is unavailable.",
        ),
        jsonObjectOutput: capability(
          "supported",
          "JSON object mode is available.",
        ),
      },
      outputStrategyPolicy: "allow_json_object_validation",
      parallelToolCallsPolicy: "serialize",
      reasoningPolicy: "forbid",
      streamingPolicy: "forbid",
      timeoutSeconds: 5,
      apiKey: "sk-e2e-fake-tools-disabled",
    });
    const blockedPackage = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: packageManifest(
            `e2e_fake_blocked_${suffix}`,
            noToolsModelKey,
          ),
        },
      },
    );
    expect(blockedPackage.status()).toBe(201);
    const blocked = await blockedPackage.json();

    await page.goto(`/workflow-packages/${blocked.id}/run`);
    await expect(
      page.getByTestId("workflow-package-launch-page"),
    ).toBeVisible();
    await selectLaunchWorkflow(page, "advisory_flow");
    await expect(page.getByTestId("workflow-package-launch-blockers")).toContainText(
      "Blocking diagnostics",
    );
    await expect(page.getByTestId("workflow-package-launch-blockers")).toContainText(
      "This workflow requires native tool calls",
    );

    await seedModelConnectionPayload(request, {
      key: strictModelKey,
      name: "E2E fake provider strict schema",
      description: "Fake provider with strict schema support.",
      baseUrl: FAKE_PROVIDER_BASE_URL,
      modelId: "fake-strict-schema",
      reasoningEffort: null,
      protocolProfile: "openai_responses",
      capabilities: {
        strictJsonSchemaOutput: capability(
          "supported",
          "Strict schema is supported.",
        ),
        jsonObjectOutput: capability(
          "supported",
          "JSON object mode is supported.",
        ),
        nativeToolCalls: capability(
          "unsupported",
          "No tools required by this package.",
        ),
      },
      outputStrategyPolicy: "require_strict_schema",
      parallelToolCallsPolicy: "serialize",
      reasoningPolicy: "forbid",
      streamingPolicy: "forbid",
      timeoutSeconds: 5,
      apiKey: "sk-e2e-fake-strict",
    });
    const strictPackage = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: runtimeProfilePackageManifest(
            `e2e_fake_strict_${suffix}`,
            strictModelKey,
          ),
        },
      },
    );
    expect(strictPackage.status()).toBe(201);
    const strictCreated = await strictPackage.json();
    const strictRunId = await launchPackageFromDedicatedPage(
      page,
      Number(strictCreated.id),
      "advisory_flow",
      { ticker: "MSFT" },
    );
    const strictDetail = await waitForRun(request, strictRunId);
    expect(strictDetail.status).toBe("succeeded");
    expect(JSON.stringify(strictDetail)).toContain("strictJsonSchema");

    await seedModelConnectionPayload(request, {
      key: jsonModelKey,
      name: "E2E fake provider JSON object only",
      description: "Fake provider with JSON object mode but no strict schema.",
      baseUrl: FAKE_PROVIDER_BASE_URL,
      modelId: "fake-json-object-only",
      reasoningEffort: null,
      protocolProfile: "openai_responses",
      capabilities: {
        strictJsonSchemaOutput: capability(
          "unsupported",
          "Strict schema is rejected.",
        ),
        jsonObjectOutput: capability(
          "supported",
          "JSON object mode is supported.",
        ),
        nativeToolCalls: capability(
          "unsupported",
          "No tools required by this package.",
        ),
      },
      outputStrategyPolicy: "allow_json_object_validation",
      parallelToolCallsPolicy: "serialize",
      reasoningPolicy: "forbid",
      streamingPolicy: "forbid",
      timeoutSeconds: 5,
      apiKey: "sk-e2e-fake-json-object",
    });
    const jsonPackage = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: runtimeProfilePackageManifest(
            `e2e_fake_json_${suffix}`,
            jsonModelKey,
          ),
        },
      },
    );
    expect(jsonPackage.status()).toBe(201);
    const jsonCreated = await jsonPackage.json();
    const jsonRunId = await launchPackageFromDedicatedPage(
      page,
      Number(jsonCreated.id),
      "advisory_flow",
      { ticker: "AAPL" },
    );
    const jsonDetail = await waitForRun(request, jsonRunId);
    expect(jsonDetail.status).toBe("succeeded");
    expect(JSON.stringify(jsonDetail)).toContain("jsonObjectWithValidation");

    await seedModelConnectionPayload(request, {
      key: noUsageModelKey,
      name: "E2E fake provider missing usage",
      description: "Fake provider omits usage metadata.",
      baseUrl: FAKE_PROVIDER_BASE_URL,
      modelId: "fake-missing-usage",
      reasoningEffort: null,
      protocolProfile: "openai_responses",
      capabilities: {
        strictJsonSchemaOutput: capability(
          "supported",
          "Strict schema is supported.",
        ),
        usageReporting: capability("unsupported", "Usage metadata is omitted."),
      },
      outputStrategyPolicy: "require_strict_schema",
      parallelToolCallsPolicy: "serialize",
      reasoningPolicy: "forbid",
      streamingPolicy: "forbid",
      timeoutSeconds: 5,
      apiKey: "sk-e2e-fake-missing-usage",
    });
    const usagePackage = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: runtimeProfilePackageManifest(
            `e2e_fake_usage_${suffix}`,
            noUsageModelKey,
          ),
        },
      },
    );
    expect(usagePackage.status()).toBe(201);
    const usageCreated = await usagePackage.json();
    const usageRunId = await launchPackageFromDedicatedPage(
      page,
      Number(usageCreated.id),
      "advisory_flow",
      { ticker: "NVDA" },
    );
    const usageDetail = await waitForRun(request, usageRunId);
    expect(usageDetail.status).toBe("succeeded");
    expect(usageDetail.executedTokens).toBe(0);

    await seedModelConnectionPayload(request, {
      key: reasoningModelKey,
      name: "E2E fake provider reasoning disabled",
      description: "Fake provider rejects reasoning fields.",
      baseUrl: FAKE_PROVIDER_BASE_URL,
      modelId: "fake-reasoning-disabled",
      reasoningEffort: "high",
      protocolProfile: "openai_responses",
      capabilities: {
        reasoningHints: capability(
          "unsupported",
          "Reasoning hints are rejected.",
        ),
        strictJsonSchemaOutput: capability(
          "supported",
          "Strict schema is supported.",
        ),
      },
      outputStrategyPolicy: "require_strict_schema",
      parallelToolCallsPolicy: "serialize",
      reasoningPolicy: "allow",
      streamingPolicy: "forbid",
      timeoutSeconds: 5,
      apiKey: "sk-e2e-fake-reasoning",
    });
    const reasoningPackage = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: runtimeProfilePackageManifest(
            `e2e_fake_reasoning_${suffix}`,
            reasoningModelKey,
          ),
        },
      },
    );
    expect(reasoningPackage.status()).toBe(201);
    const reasoningCreated = await reasoningPackage.json();
    const reasoningLaunch = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/${reasoningCreated.id}/launches`,
      {
        data: { workflowKey: "advisory_flow", parameters: { ticker: "AAPL" } },
      },
    );
    expect(reasoningLaunch.status()).toBe(201);
    const reasoningRun = await waitForRun(
      request,
      Number((await reasoningLaunch.json()).id),
    );
    expect(reasoningRun.status).toBe("failed");
    expect(JSON.stringify(reasoningRun)).toContain(
      "model_reasoning_unsupported",
    );

    await page.goto(`/runs/${usageRunId}`);
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();
    await page.getByTestId("runs-detail-tab-trigger-runtime").click();
    await expect(page.getByTestId("runs-runtime-profile")).toContainText(
      "Runtime profile",
    );
    await expect(page.getByTestId("runs-runtime-profile")).toContainText(
      "Usage reporting",
    );
    await expect(page.getByTestId("runs-runtime-profile")).toContainText(
      "Unsupported",
    );
    await expect(
      page.getByRole("heading", { name: "Selected strategies" }),
    ).toBeVisible();
    await expect(page.getByText(/sk-e2e-fake/i)).toHaveCount(0);
  });

  test("keeps run detail evidence workspace horizontally contained on mobile", async ({
    page,
    request,
  }) => {
    const suffix = Date.now();
    const packageKey = `e2e_wide_output_${suffix}`;
    const modelKey = `e2e_wide_model_${suffix}`;
    const wideFieldKey = `wide_${"x".repeat(100)}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages`,
      {
        data: {
          manifestSource: wideOutputPackageManifest(
            packageKey,
            modelKey,
            wideFieldKey,
          ),
        },
      },
    );
    const created = await createResponse.json();
    expect(createResponse.status(), JSON.stringify(created)).toBe(201);

    const launch = await request.post(
      `${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`,
      {
        data: { workflowKey: "wide_flow", parameters: {} },
      },
    );
    const launchedText = await launch.text();
    expect(launch.status(), launchedText).toBe(201);
    const runId = Number(JSON.parse(launchedText).id);
    const detail = await waitForRun(request, runId);
    expect(detail.status).toBe("succeeded");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/runs/${runId}`);
    await expect(page.getByTestId("route-run-detail")).toHaveAttribute(
      "data-route-shell-mode",
      "fullHeight",
    );
    await expect(page.getByTestId("runs-detail-summary-line")).toContainText(
      "succeeded",
      { timeout: 15_000 },
    );
    await expect(page.getByRole("heading", { name: "Final output" })).toBeVisible();

    const layoutMetrics = await page.evaluate(() => {
      const workspace = document.querySelector<HTMLElement>(
        '[data-testid="runs-inspection-workspace"]',
      );
      if (!workspace) {
        throw new Error("Run inspection workspace was not found");
      }
      return {
        pageScrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        workspaceWidth: workspace.getBoundingClientRect().width,
      };
    });

    expect(layoutMetrics.pageScrollWidth).toBeLessThanOrEqual(
      layoutMetrics.viewportWidth + 20,
    );
    expect(layoutMetrics.workspaceWidth).toBeLessThanOrEqual(
      layoutMetrics.viewportWidth,
    );
  });
});
