import { test, expect } from "@playwright/test";

test.describe("Portfolio CRUD", () => {
  test("create a portfolio", async ({ page }) => {
    const timestamp = Date.now();
    const portfolioName = `Test Portfolio ${timestamp}`;
    const portfolioSlug = `test_portfolio_${timestamp}`;

    await page.goto("/portfolios");

    await page.getByRole("button", { name: /create|new|add/i }).click();
    await expect(page.getByRole("heading", { name: "Create Portfolio" })).toBeVisible();

    await page.getByLabel("Name").fill(portfolioName);
    await page.getByLabel("Slug").fill(portfolioSlug);
    await page.getByLabel("Base Currency").fill("USD");
    await page.getByRole("button", { name: /create|save|submit/i }).click();

    await expect(page).toHaveURL(/\/portfolios\/[^/]+$/);
    await expect(page.getByRole("heading", { name: portfolioName })).toBeVisible({ timeout: 5000 });
  });

  test("portfolio list renders", async ({ page }) => {
    await page.goto("/portfolios");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });

  test("add position loads a suggested name and still allows manual fallback", async ({ page, request }) => {
    const portfolioName = `E2E Position Lookup ${Date.now()}`;
    const portfolioSlug = `e2e_position_lookup_${Date.now()}`;
    const createResponse = await request.post("http://127.0.0.1:8001/api/v1/portfolios", {
      data: {
        name: portfolioName,
        slug: portfolioSlug,
        description: "Playwright Add Position lookup coverage",
        baseCurrency: "USD",
      },
    });

    expect(createResponse.ok()).toBeTruthy();
    const portfolio = await createResponse.json();

    await page.goto(`/portfolios/${portfolio.id}`);
    await expect(page.getByRole("heading", { name: portfolioName })).toBeVisible();

    await page.getByRole("button", { name: "Add Position" }).click();
    await page.getByLabel("Symbol").fill("AAPL");
    await expect(page.getByLabel("Name")).toHaveValue("Apple Inc.");
    await expect(page.getByText("Suggested name loaded. You can edit it before saving.")).toBeVisible();

    await page.getByLabel("Name").fill("Apple E2E Override");
    await page.getByLabel("Quantity").fill("10");
    await page.getByLabel("Average Cost").fill("185.50");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Apple E2E Override")).toBeVisible();

    await page.getByRole("button", { name: "Add Position" }).click();
    await page.getByLabel("Symbol").fill("ZZZZZZZZ");
    await expect(page.getByText("No company name found. You can enter one manually.")).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("");

    await page.getByLabel("Name").fill("Manual Fallback Name");
    await page.getByLabel("Quantity").fill("1");
    await page.getByLabel("Average Cost").fill("1.00");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Manual Fallback Name")).toBeVisible();
  });
});
