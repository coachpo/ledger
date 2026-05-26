import { expect, test, type Page } from "@playwright/test";

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

type MemoryFixtureRouteState = {
  requests: string[];
};

async function installScopedMemoryFixtures(
  page: Page,
): Promise<MemoryFixtureRouteState> {
  const state: MemoryFixtureRouteState = { requests: [] };
  const memoryItem = {
    content: "Risk memo content with deterministic scoped memory evidence.",
    createdAt: "2026-05-20T10:00:00Z",
    kind: "insight",
    memoryId: "mem-risk-1",
    provenance: {
      agentKey: "analyst",
      agentVersion: 1,
      runId: 41,
      workflowKey: "risk-review",
    },
    revisionId: "rev-risk-1",
    scope: { scopeKey: "41", scopeType: "run" },
    subjectRefs: [{ id: "AAPL", kind: "symbol", label: "Apple" }],
    summary: "Risk review memory",
  };
  const revision = {
    attributes: { confidence: "high" },
    content: memoryItem.content,
    contentHash: "hash-risk-1",
    createdAt: "2026-05-20T10:00:00Z",
    revisionAction: "created",
    revisionId: "rev-risk-1",
    sourceAgentKey: "analyst",
    sourceRunId: 41,
    status: "resolved",
    subjectRefs: memoryItem.subjectRefs,
    summary: memoryItem.summary,
    version: 1,
  };

  await page.route(
    /127\.0\.0\.1:8001\/api\/memory(?:\/.*)?$/,
    async (route) => {
      const request = route.request();
      if (request.method() !== "POST") {
        await route.fallback();
        return;
      }

      state.requests.push(new URL(request.url()).pathname);
      const pathname = new URL(request.url()).pathname;
      if (pathname === "/api/memory") {
        await route.fulfill({
          json: {
            count: 1,
            items: [memoryItem],
            limit: 20,
            offset: 0,
            scope: memoryItem.scope,
            visibility: "explicit-scope",
          },
        });
        return;
      }

      if (pathname.endsWith("/detail")) {
        await route.fulfill({
          json: {
            ...memoryItem,
            attributes: { confidence: "high" },
            revision,
            status: "resolved",
            updatedAt: "2026-05-20T10:05:00Z",
          },
        });
        return;
      }

      if (pathname.endsWith("/revisions")) {
        await route.fulfill({
          json: { count: 1, items: [revision], limit: 20, offset: 0 },
        });
        return;
      }

      if (pathname.endsWith("/events")) {
        await route.fulfill({
          json: {
            count: 1,
            items: [
              {
                budget: { max: 3 },
                createdAt: "2026-05-20T10:06:00Z",
                eventId: 99,
                eventType: "memory.write",
                excerpt: "Risk memo content",
                filters: { kind: "insight" },
                memoryId: "mem-risk-1",
                resultSnapshot: { count: 1 },
                revisionId: "rev-risk-1",
                runId: 41,
                statusSnapshot: { status: "resolved" },
              },
            ],
            limit: 20,
            offset: 0,
          },
        });
        return;
      }

      await route.fulfill({ json: {}, status: 404 });
    },
  );

  return state;
}

test.describe("canonical memory workspace", () => {
  test("memory route renders private-scope access state", async ({ page }) => {
    const panelLayoutWarnings = collectPanelLayoutWarnings(page);
    const fixtures = await installScopedMemoryFixtures(page);

    await page.goto("/memory");

    await expectSingleRouteMain(page, "route-memory-list", "fullHeight");
    await expect(page.getByTestId("memory-list-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Canonical Memory" }),
    ).toBeVisible();
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "concrete private scope",
    );
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "browser-authored JSON",
    );
    await expect(page.getByTestId("memory-contract-notice")).toContainText(
      "finance report history remains in Reports",
    );
    await expect(page.getByTestId("memory-access-required")).toContainText(
      "Access context required",
    );
    await expect(page.getByTestId("memory-split-inspector")).toHaveAttribute(
      "data-inspector-state",
      "closed",
    );
    await expectMemoryInspectorStartsInViewport(page);
    expect(fixtures.requests).toEqual([]);
    await expect(page.getByTestId("nav-memory")).toBeVisible();
    await expectNoDocumentOverflow(page);
    expect(panelLayoutWarnings).toEqual([]);
  });

  test("memory route inspects deterministic scoped fixtures inline", async ({
    page,
  }) => {
    const panelLayoutWarnings = collectPanelLayoutWarnings(page);
    const fixtures = await installScopedMemoryFixtures(page);

    await page.goto("/memory");
    await page.getByRole("textbox", { name: "Package key" }).fill("pkg_alpha");
    await expect(
      page.getByTestId("memory-explicit-scope-required"),
    ).toContainText("Private scope required");
    expect(fixtures.requests).toEqual([]);

    await page.getByRole("textbox", { name: "Run id" }).fill("41");
    await expect(page.getByTestId("memory-row-mem-risk-1")).toBeVisible();
    expect(fixtures.requests).toContain("/api/memory");
    await expect(page.getByLabel("Scoped memory inventory")).toContainText(
      "Risk review memory",
    );
    await expect(page.getByText("run scope 41").first()).toBeVisible();

    await page.getByRole("button", { name: "Open memory" }).click();
    await expect(page.getByTestId("memory-split-inspector")).toHaveAttribute(
      "data-inspector-state",
      "open",
    );
    await expectMemoryInspectorStartsInViewport(page);
    await expect(page.getByRole("tab", { name: "Detail" })).toBeVisible();
    await expect(page.getByTestId("memory-detail-panel")).toContainText(
      "Risk memo content with deterministic scoped memory evidence.",
    );

    await page.getByRole("tab", { name: "Revisions" }).click();
    await expect(page.getByTestId("memory-revisions-panel")).toContainText(
      "v1",
    );
    await page.getByRole("tab", { name: "Events" }).click();
    await expect(page.getByTestId("memory-events-panel")).toContainText(
      "event #99",
    );
    expect(fixtures.requests).toEqual(
      expect.arrayContaining([
        "/api/memory",
        "/api/memory/mem-risk-1/detail",
        "/api/memory/mem-risk-1/revisions",
        "/api/memory/mem-risk-1/events",
      ]),
    );
    await expectNoDocumentOverflow(page);
    expect(panelLayoutWarnings).toEqual([]);
  });
});
