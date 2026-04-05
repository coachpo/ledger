import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

async function waitForBacktest(
  request: APIRequestContext,
  backtestId: string,
): Promise<{ id: number; name: string; status: string }> {
  const response = await request.get(`${API_BASE}/backtests/${backtestId}`);
  return response.json();
}

async function waitForBacktestIdByName(
  request: APIRequestContext,
  backtestName: string,
): Promise<string> {
  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE}/backtests`);
        if (!response.ok()) {
          return null;
        }
        const backtests = (await response.json()) as Array<{ id: number; name: string }>;
        const match = backtests.find((backtest) => backtest.name === backtestName);
        return match ? String(match.id) : null;
      },
      { timeout: 30_000 },
    )
    .not.toBeNull();

  const response = await request.get(`${API_BASE}/backtests`);
  const backtests = (await response.json()) as Array<{ id: number; name: string }>;
  const match = backtests.find((backtest) => backtest.name === backtestName);
  return String(match!.id);
}

async function expectBacktestDeleted(
  page: Page,
  request: APIRequestContext,
  backtestId: string,
  backtestName: string,
) {
  await expect
    .poll(async () => (await request.get(`${API_BASE}/backtests/${backtestId}`)).status())
    .toBe(404);
  await expect(page.getByText(backtestName)).toHaveCount(0);
}

async function configureBacktestForm(page: Page, backtestName: string) {
  const portfolioName = `E2E Portfolio ${Date.now()}`;
  const portfolioSlug = `e2e_portfolio_${Date.now()}`;

  await expect(page.locator("#backtest-name")).toBeVisible();
  await page.locator("#backtest-name").fill(backtestName);
  await page.getByRole("radio", { name: /create new/i }).click();
  await expect(page.getByRole("radio", { name: /create new/i })).toBeChecked();
  await expect(page.locator("#new-portfolio-name")).toBeVisible();
  await page.locator("#new-portfolio-name").fill(portfolioName);
  await page.locator("#new-portfolio-slug").fill(portfolioSlug);
  await page.locator("#new-portfolio-initial-cash").fill("25000");
  await page.getByLabel(/create default template/i).check();
  await expect(page.getByLabel(/create default template/i)).toBeChecked();
  await page.locator("#frequency").selectOption("MONTHLY");
  await page.locator("#start-date").fill("2024-01-02");
  await page.locator("#end-date").fill("2024-03-29");
  await page.locator("#webhook-url").fill("http://localhost:5678/webhook/test");
  await page.locator("#webhook-timeout").fill("600");
  await page.getByLabel(/s&p 500/i).check();
  await expect(page.getByLabel(/s&p 500/i)).toBeChecked();

  await expect(page.getByText("Select an existing portfolio")).toHaveCount(0);
  await expect(page.getByText("Choose a complete date range")).toHaveCount(0);
  await expect(page.getByText("Enter a client endpoint URL")).toHaveCount(0);
  await expect(page.getByText("Enter a client callback timeout")).toHaveCount(0);
  await expect(page.getByText("Select at least one benchmark")).toHaveCount(0);
}

test.describe("Backtests", () => {
  test("create a backtest, poll until terminal state, and view results", async ({
    page,
    request,
  }) => {
    const backtestName = `E2E Backtest ${Date.now()}`;

    await page.goto("/backtests");
    await page.getByRole("link", { name: /backtests/i }).click();
    await page.getByRole("button", { name: /new backtest/i }).click();
    await page.waitForURL(/\/backtests\/new$/);

    await configureBacktestForm(page, backtestName);
    await expect(page.locator("#backtest-name")).toHaveValue(backtestName);
    await expect(page.getByRole("button", { name: /launch backtest/i })).toBeEnabled();
    await page
      .getByRole("button", { name: /launch backtest/i })
      .evaluate((element) => (element as HTMLButtonElement).click());

    const backtestId = await waitForBacktestIdByName(request, backtestName);
    expect(backtestId).toMatch(/^\d+$/);

    await page.goto(`/backtests/${backtestId}`);
    await expect(page.getByText(/current simulation date|total return/i)).toBeVisible();

    const backtest = await waitForBacktest(request, backtestId);
    expect(backtest.name).toBe(backtestName);
    await expect
      .poll(async () => (await request.get(`${API_BASE}/backtests/${backtestId}`)).json())
      .toMatchObject({ status: "COMPLETED" });

    await page.reload();
    await expect(page.getByText(/total return/i)).toBeVisible();

    await page.getByRole("button", { name: /^delete$/i }).click();
    await page.getByRole("button", { name: /^delete$/i }).last().click();
    await expectBacktestDeleted(page, request, backtestId, backtestName);
  });
});
