import { expect, test, type Page } from "@playwright/test";

async function expectSingleRouteMain(
  page: Page,
  testId: string,
  shellMode: string,
  widthMode = "wide",
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

test.describe("workflow memory review workspace", () => {
  test("renders review-only proposal, audit, and quarantine surfaces", async ({
    page,
  }) => {
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

    await page.setViewportSize({ width: 1280, height: 760 });
    await page.goto("/memory");

    await expectSingleRouteMain(page, "route-memory-list", "scroll", "wide");
    await expect(page.getByTestId("memory-list-page")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Workflow Memory Review" }),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: "Proposals" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Audit events" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Quarantine" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Proposal status" })).toBeVisible();
    await expect(page.getByTestId("nav-memory")).toContainText("Memory Review");

    await page.getByRole("tab", { name: "Audit events" }).click();
    await expect(page.getByText(/No audit events|Proposal Approved/)).toBeVisible();
    await page.getByRole("tab", { name: "Quarantine" }).click();
    await expect(page.getByText(/No quarantined memory|Unresolved|Resolved/)).toBeVisible();

    expect(
      memoryRequests.some((requestLine) =>
        requestLine.startsWith("GET /api/memory/proposals"),
      ),
    ).toBe(true);
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.startsWith("GET /api/memory/audit-events"),
      ),
    ).toBe(true);
    expect(
      memoryRequests.some((requestLine) =>
        requestLine.startsWith("GET /api/memory/quarantine"),
      ),
    ).toBe(true);
    await expectNoDocumentOverflow(page);
  });
});
