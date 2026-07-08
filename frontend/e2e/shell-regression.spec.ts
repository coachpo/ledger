import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const PLATFORM_API_BASE = "http://127.0.0.1:8001/api";
const API_BASE = "http://127.0.0.1:8001/api/v1";
const FAKE_PROVIDER_BASE_URL =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? "http://127.0.0.1:18081/v1";

const viewports = [
  { height: 900, label: "desktop-wide", width: 1440 },
  { height: 800, label: "desktop", width: 1280 },
  { height: 768, label: "tablet", width: 1024 },
  { height: 844, label: "mobile", width: 375 },
] as const;

type RouteArchetype =
  | "dashboard"
  | "inventory"
  | "editor"
  | "detail"
  | "console"
  | "systemState";

type ShellRoute = {
  archetype: RouteArchetype;
  pageTestId: string;
  routeTestId: string;
  shellMode: "scroll" | "fullHeight";
  url: string;
  widthMode: "wide" | "full" | "compact" | "readable";
};
function packageManifest(packageKey: string, modelKey: string) {
  return [
    "apiVersion: signaldeck.workflowPackage/v1",
    "kind: WorkflowPackage",
    "metadata:",
    `  key: ${packageKey}`,
    `  name: Shell Regression ${packageKey}`,
    "  description: Responsive shell regression fixture.",
    "spec:",
    "  inputs:",
    "    type: object",
    "    properties:",
    "      ticker:",
    "        type: string",
    "    required: [ticker]",
    "  outputSchemas:",
    "    - key: shell_output",
    "      name: Shell Output",
    "      jsonSchema:",
    "        type: object",
    "        properties:",
    "          summary:",
    "            type: string",
    "        required: [summary]",
    "  agents:",
    "    - key: shell_agent",
    `      modelConnection: ${modelKey}`,
    "      name: Shell Agent",
    "      systemPrompt: Return deterministic JSON.",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      outputSchema: shell_output",
    "  workflows:",
    "    - key: shell_flow",
    "      name: Shell Flow",
    "      inputSchema:",
    "        type: object",
    "        properties:",
    "          ticker:",
    "            type: string",
    "        required: [ticker]",
    "      flow:",
    "        kind: step",
    "        id: shell_analysis",
    "        slot: summary",
    "        uses: shell_agent",
    "        with:",
    "          ticker: ${{ inputs.ticker }}",
    "      output:",
    "        from: ${{ nodes.shell_analysis.outputs.summary }}",
    "",
  ].join("\n");
}
async function seedModelConnection(request: APIRequestContext, key: string) {
  const response = await request.post(
    `${PLATFORM_API_BASE}/model-connections`,
    {
      data: {
        apiKey: "sk-e2e-shell-regression-fake-provider",
        baseUrl: FAKE_PROVIDER_BASE_URL,
        description: "Responsive shell regression fake provider connection.",
        key,
        modelId: "fake-strict-schema",
        name: `Shell Regression Model ${key}`,
        protocolProfile: "openai_responses",
        reasoningEffort: "low",
        timeoutSeconds: 5,
      },
    },
  );

  const text = await response.text();
  expect(response.status(), text).toBe(201);
  return JSON.parse(text) as { id: number; key: string };
}

async function seedWorkflowPackage(
  request: APIRequestContext,
  packageKey: string,
  modelKey: string,
) {
  const response = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages`,
    {
      data: { manifestSource: packageManifest(packageKey, modelKey) },
    },
  );

  const text = await response.text();
  expect(response.status(), text).toBe(201);
  return JSON.parse(text) as { id: number; key: string };
}

async function seedTemplate(request: APIRequestContext) {
  const response = await request.post(`${API_BASE}/templates`, {
    data: {
      content: "# Shell template\n\nTicker: {{inputs.ticker}}",
      name: `Shell Regression Template ${Date.now()}`,
    },
  });

  const text = await response.text();
  expect(response.ok(), text).toBeTruthy();
  return JSON.parse(text) as { id: number };
}

async function seedReport(request: APIRequestContext) {
  const slug = `shell_regression_${Date.now()}`;
  const response = await request.post(`${API_BASE}/reports`, {
    data: {
      content: "# Shell Regression Report\n\nReadable detail content.",
      metadata: {
        author: "E2E",
        description: "Shell regression",
        tags: ["shell"],
      },
      name: "Shell Regression Report",
      slug,
    },
  });

  const text = await response.text();
  expect(response.status(), text).toBe(201);
  return JSON.parse(text) as { slug: string };
}

async function launchCompletedRun(
  request: APIRequestContext,
  packageId: number,
) {
  const launch = await request.post(
    `${PLATFORM_API_BASE}/workflow-packages/${packageId}/launches`,
    { data: { parameters: { ticker: "AAPL" }, workflowKey: "shell_flow" } },
  );
  const launchText = await launch.text();
  expect(launch.status(), launchText).toBe(201);
  const runId = Number(JSON.parse(launchText).id);

  await expect
    .poll(
      async () => {
        const detail = await request.get(`${PLATFORM_API_BASE}/runs/${runId}`);
        expect(detail.ok()).toBeTruthy();
        return (await detail.json()).status;
      },
      { timeout: 15_000 },
    )
    .toBe("succeeded");

  return runId;
}
async function expectNoDocumentOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
}

async function expectRouteShell(page: Page, route: ShellRoute) {
  const main = page.getByRole("main");
  await expect(main).toHaveCount(1);
  await expect(main).toHaveAttribute("data-testid", route.routeTestId);
  await expect(main).toHaveAttribute("data-route-shell-mode", route.shellMode);
  await expect(main).toHaveAttribute("data-route-width-mode", route.widthMode);
  await expect(page.getByTestId(route.pageTestId)).toBeVisible({
    timeout: 15_000,
  });
}

async function expectInspectorContract(
  page: Page,
  route: ShellRoute,
  width: number,
) {
  if (route.routeTestId === "route-run-detail") {
    if (width < 768) {
      await expect(page.getByTestId("runs-inspection-workspace")).toHaveAttribute(
        "data-run-mode",
        "outputs",
      );
      await expect(page.getByTestId("runs-inspection-workspace")).toBeVisible();
      await expect(page.getByTestId("runs-detail-tabs")).toBeVisible();
      return;
    }

    await expect(page.getByTestId("runs-inspection-workspace")).toHaveAttribute(
      "data-run-mode",
      "outputs",
    );
    await expect(page.getByTestId("runs-detail-tabs")).toBeVisible();
    await expect(page.getByTestId("runs-detail-tab-panel-output")).toBeVisible();
    return;
  }

  await expect(page.getByTestId("runs-inspection-split-layout")).toHaveCount(0);
  await expect(page.getByTestId("runs-inspection-sheet-layout")).toHaveCount(0);
}

async function expectNoConsoleErrors(page: Page, consoleErrors: string[]) {
  await expect(page.locator("body")).not.toContainText(
    "Unexpected Application Error!",
  );
  await expect(page.locator("body")).not.toContainText("Vite Error");
  expect(consoleErrors).toEqual([]);
}

test.describe("Unified shell responsive regression matrix", () => {
  test("locks route archetypes, width modes, inspectors, and overflow", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const suffix = Date.now();
    const model = await seedModelConnection(request, `shell_model_${suffix}`);
    const workflowPackage = await seedWorkflowPackage(
      request,
      `shell_pkg_${suffix}`,
      model.key,
    );
    const runId = await launchCompletedRun(request, workflowPackage.id);
    const template = await seedTemplate(request);
    const report = await seedReport(request);
    const consoleErrors: string[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });

    const routes: ShellRoute[] = [
      {
        archetype: "dashboard",
        pageTestId: "dashboard-page",
        routeTestId: "route-dashboard",
        shellMode: "scroll",
        url: "/",
        widthMode: "wide",
      },
      {
        archetype: "inventory",
        pageTestId: "workflow-packages-list-page",
        routeTestId: "route-workflow-packages-list",
        shellMode: "scroll",
        url: "/workflow-packages",
        widthMode: "wide",
      },
      {
        archetype: "editor",
        pageTestId: "workflow-package-import-page",
        routeTestId: "route-workflow-package-import",
        shellMode: "fullHeight",
        url: "/workflow-packages/import",
        widthMode: "full",
      },
      {
        archetype: "editor",
        pageTestId: "workflow-package-editor-shell",
        routeTestId: "route-workflow-package-detail",
        shellMode: "fullHeight",
        url: `/workflow-packages/${workflowPackage.id}`,
        widthMode: "full",
      },
      {
        archetype: "console",
        pageTestId: "workflow-package-launch-page",
        routeTestId: "route-workflow-package-launch",
        shellMode: "fullHeight",
        url: `/workflow-packages/${workflowPackage.id}/run`,
        widthMode: "full",
      },
      {
        archetype: "editor",
        pageTestId: "model-connections-editor",
        routeTestId: "route-model-connection-edit",
        shellMode: "fullHeight",
        url: `/model-connections/${model.id}/edit`,
        widthMode: "full",
      },
      {
        archetype: "inventory",
        pageTestId: "runs-list-page",
        routeTestId: "route-runs-list",
        shellMode: "scroll",
        url: "/runs",
        widthMode: "wide",
      },
      {
        archetype: "console",
        pageTestId: "runs-detail-page",
        routeTestId: "route-run-detail",
        shellMode: "fullHeight",
        url: `/runs/${runId}`,
        widthMode: "full",
      },
      {
        archetype: "editor",
        pageTestId: "template-editor-shell",
        routeTestId: "route-template-edit",
        shellMode: "fullHeight",
        url: `/templates/${template.id}/edit`,
        widthMode: "full",
      },
      {
        archetype: "detail",
        pageTestId: "report-detail-header",
        routeTestId: "route-report-detail",
        shellMode: "scroll",
        url: `/reports/${report.slug}`,
        widthMode: "wide",
      },
    ];

    expect(new Set(routes.map((route) => route.archetype))).toEqual(
      new Set([
        "dashboard",
        "inventory",
        "editor",
        "detail",
        "console",
      ]),
    );

    for (const viewport of viewports) {
      await page.setViewportSize({
        height: viewport.height,
        width: viewport.width,
      });

      for (const route of routes) {
        consoleErrors.length = 0;
        await page.goto(route.url);
        await page.evaluate(() => window.scrollTo(0, 0));
        await expectRouteShell(page, route);
        await expectInspectorContract(page, route, viewport.width);
        await expectNoDocumentOverflow(page);
        await expectNoConsoleErrors(page, consoleErrors);
      }
    }
  });
});
