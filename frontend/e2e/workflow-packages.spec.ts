import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const DETERMINISTIC_MODEL_BASE_URL = "https://signaldeck-deterministic-model.local/v1";

function packageManifest(packageKey: string, modelKey: string, agentName = "Package Analyst") {
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
    "        - signaldeck.market_data.quote_lookup",
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

async function seedModelConnection(request: APIRequestContext, key: string) {
  const list = await request.get(`${PLATFORM_API_BASE}/model-connections`, {
    params: { status: "active" },
  });
  expect(list.ok()).toBeTruthy();
  const existing = (await list.json()).items.find((item: { id: number; key: string }) => item.key === key);
  const payload = {
    key,
    name: `E2E deterministic model ${key}`,
    description: "Deterministic model connection for package-first E2E.",
    connectionKind: "deterministic_smoke",
    baseUrl: DETERMINISTIC_MODEL_BASE_URL,
    modelId: "signaldeck-deterministic-json",
    reasoningEffort: "low",
    apiStyle: "responses",
    timeoutSeconds: 5,
    apiKey: "sk-e2e-deterministic",
  };
  if (existing) {
    const { key: _key, ...updatePayload } = payload;
    const response = await request.patch(`${PLATFORM_API_BASE}/model-connections/${existing.id}`, { data: updatePayload });
    expect(response.ok()).toBeTruthy();
    return;
  }
  const response = await request.post(`${PLATFORM_API_BASE}/model-connections`, { data: payload });
  expect(response.ok()).toBeTruthy();
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

test.describe("Workflow packages", () => {
  test("covers current-package authoring, export, import, launch, and snapshot provenance", async ({ page, request }) => {
    const suffix = Date.now();
    const packageKey = `e2e_package_${suffix}`;
    const modelKey = `e2e_model_${suffix}`;

    await seedModelConnection(request, modelKey);
    const createResponse = await request.post(`${PLATFORM_API_BASE}/workflow-packages`, {
      data: { manifestSource: packageManifest(packageKey, modelKey) },
    });
    expect(createResponse.status()).toBe(201);
    const created = await createResponse.json();

    await openPackageEditor(page, Number(created.id));
    await page.getByRole("tab", { name: "Agents tab" }).click();
    await expect(page.getByTestId("workflow-package-agents-tab")).toBeVisible();

    const editedSource = packageManifest(packageKey, modelKey, "Edited Package Analyst");
    const updateResponse = await request.patch(`${PLATFORM_API_BASE}/workflow-packages/${created.id}`, {
      data: { manifestSource: editedSource },
    });
    expect(updateResponse.ok()).toBeTruthy();

    const preflight = await request.post(`${PLATFORM_API_BASE}/workflow-packages/${created.id}/preflight`, {
      params: { workflowKey: "advisory_flow" },
    });
    expect(preflight.ok()).toBeTruthy();
    expect(await preflight.json()).toMatchObject({ ready: true, workflowKey: "advisory_flow" });

    const exportResponse = await request.get(`${PLATFORM_API_BASE}/workflow-packages/${created.id}/export`);
    expect(exportResponse.ok()).toBeTruthy();
    const exported = await exportResponse.text();
    expect(exported).toContain(`modelConnection: ${modelKey}`);
    for (const forbidden of ["secretPayload", "encrypted", "password", "modelConnectionId", "outputSchemaId"]) {
      expect(exported).not.toContain(forbidden);
    }

    const importedKey = `${packageKey}_imported`;
    const importResponse = await request.post(`${PLATFORM_API_BASE}/workflow-packages/import`, {
      data: { manifestSource: exported.replace(`key: ${packageKey}`, `key: ${importedKey}`) },
    });
    expect(importResponse.ok()).toBeTruthy();
    expect((await importResponse.json()).key).toBe(importedKey);

    await page.goto(`/workflow-packages/${created.id}/run`);
    await expect(page.getByTestId("workflow-package-launch-tab")).toBeVisible();
    const launch = await request.post(`${PLATFORM_API_BASE}/workflow-packages/${created.id}/launches`, {
      data: { workflowKey: "advisory_flow", parameters: { ticker: "AAPL" } },
    });
    expect(launch.status()).toBe(201);
    const launched = await launch.json();
    const runId = Number(launched.id);
    await page.goto(`/runs/${runId}`);
    await expect(page.getByTestId("runs-detail-page")).toBeVisible();

    const detail = await waitForRun(request, runId);
    expect(detail.status).toBe("succeeded");
    expect(detail.targetKind).toBe("workflowPackage");
    expect(detail.finalOutput).toMatchObject({ summary: "deterministic summary" });
    const packageProvenance = detail.packageProvenance as Record<string, unknown>;
    expect(packageProvenance).toMatchObject({
      currentPackage: { available: true, status: "active" },
      launchSnapshot: { parameters: { ticker: "AAPL" }, workflowKey: "advisory_flow" },
      workflowKey: "advisory_flow",
      workflowPackageKey: packageKey,
    });
    expect(packageProvenance.workflowPackageManifestHash).toEqual(expect.any(String));
    expect(packageProvenance.workflowPackageCompiledHash).toEqual(expect.any(String));

    await page.reload();
    await expect(page.getByTestId("runs-detail-status")).toContainText("succeeded", { timeout: 15_000 });
    await expect(page.getByTestId("runs-detail-final-output")).toContainText("deterministic summary");
    await expect(page.getByTestId("runs-detail-target-identity")).toContainText(packageKey);
    await expect(page.getByText(`Captured package id: ${created.id}`)).toBeVisible();
    await expect(page.getByTestId("runs-detail-package-link")).toHaveAttribute("href", `/workflow-packages/${created.id}`);

    await page.getByTestId("runs-detail-rerun").click();
    await expect(page.getByRole("dialog", { name: /run snapshot again/i })).toBeVisible();
    await page.getByTestId("run-rerun-submit").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);

    await page.goto(`/runs/${runId}`);
    await expect(page.getByTestId("runs-step-1-replay-entry")).toBeVisible();
    await page.getByTestId("runs-step-1-replay-entry").getByRole("button", { name: /replay snapshot step/i }).click();
    await expect(page.getByRole("dialog", { name: /snapshot step replay draft/i })).toBeVisible();
    await page.getByTestId("run-step-replay-submit").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
  });
});
