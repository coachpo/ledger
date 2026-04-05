import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

function reportCardByText(page: Page, text: string) {
  return page.locator("[data-slot='card']").filter({ hasText: text });
}

async function expectReportDeleted(
  page: Page,
  request: APIRequestContext,
  slug: string,
  cardText: string,
) {
  await expect
    .poll(async () => (await request.get(`${API_BASE}/reports/${slug}`)).status())
    .toBe(404);
  await expect(reportCardByText(page, cardText)).toHaveCount(0);
}

test.describe("Reports", () => {
  test("navigate to reports page from sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Reports" })).toBeVisible();
    await page.getByRole("link", { name: "Reports" }).click();
    await expect(page).toHaveURL(/\/reports/);
  });

  test("generate report from template, view, edit, download, delete", async ({
    page,
    request,
  }) => {
    const templateResponse = await request.post(`${API_BASE}/templates`, {
      data: {
        name: `E2E Report Template ${Date.now()}`,
        content: "# E2E Report\n\nHello world.\n\n- Item one\n- Item two",
      },
    });
    expect(templateResponse.ok()).toBeTruthy();
    const template = await templateResponse.json();

    await page.goto("/reports");
    await page.getByRole("button", { name: /generate report/i }).click();
    await expect(
      page.getByRole("heading", { name: "Generate Report" }),
    ).toBeVisible();

    await page.getByRole("combobox").click();
    await page
      .getByRole("option", { name: new RegExp(template.name) })
      .click();
    await page.getByRole("button", { name: /^generate$/i }).click();

    await page.waitForURL(/\/reports\/[a-z0-9_]+/);

    const generatedSlug = page.url().split("/reports/")[1];
    expect(generatedSlug).toMatch(/^[a-z0-9_]+$/);

    const reportResponse = await request.get(`${API_BASE}/reports/${generatedSlug}`);
    expect(reportResponse.ok()).toBeTruthy();
    const report = await reportResponse.json();

    await expect(
      page.getByRole("heading", { name: "E2E Report" }),
    ).toBeVisible();
    await expect(page.getByText("Hello world.")).toBeVisible();
    await expect(page.getByText("Item one")).toBeVisible();

    await page.getByRole("button", { name: /edit/i }).click();
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible();
    await textarea.fill("# Edited E2E Report\n\nEdited content.");
    await page.getByRole("button", { name: /save/i }).click();
    await expect(page.getByText("Report updated")).toBeVisible();

    await expect(
      page.getByRole("heading", { name: "Edited E2E Report" }),
    ).toBeVisible();
    await expect(page.getByText("Edited content.")).toBeVisible();

    const downloadLink = page.getByRole("link", { name: /download/i });
    await expect(downloadLink).toBeVisible();
    const href = await downloadLink.getAttribute("href");
    expect(href).toContain("/reports/");
    expect(href).toContain("/download");

    const downloadResponse = await request.get(href!);
    expect(downloadResponse.ok()).toBeTruthy();
    expect(downloadResponse.headers()["content-type"]).toContain(
      "text/markdown",
    );
    expect(downloadResponse.headers()["content-disposition"]).toContain(
      "attachment",
    );
    const body = await downloadResponse.text();
    expect(body).toContain("Edited content.");

    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    const reportCard = reportCardByText(page, report.name).first();
    await expect(reportCard).toBeVisible();

    await reportCard.getByRole("button", { name: /open actions/i }).click();
    await page.getByRole("menuitem", { name: /delete/i }).click();
    await page.getByRole("button", { name: /^delete$/i }).click();
    await expectReportDeleted(page, request, generatedSlug, report.name);
  });

  test("upload markdown report with metadata", async ({ page, request }) => {
    const uploadSlug = `e2e_upload_test_${Date.now()}`;

    await page.goto("/reports");
    await page.getByRole("button", { name: /upload report/i }).click();
    await expect(
      page.getByRole("heading", { name: "Upload Report" }),
    ).toBeVisible();

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: `${uploadSlug}.md`,
      mimeType: "text/markdown",
      buffer: Buffer.from("# Uploaded E2E\n\nUpload body."),
    });

    await expect(page.locator("#slug")).toHaveValue(uploadSlug);

    await page.locator("#author").fill("E2E Author");
    await page.locator("#description").fill("Automated upload test");
    await page.locator("#tags").fill("e2e, upload");

    await page.getByRole("button", { name: /^upload$/i }).click();
    await page.waitForURL(new RegExp(`/reports/${uploadSlug}$`));

    await expect(page.getByRole("heading", { name: uploadSlug })).toBeVisible();

    await expect(
      page.getByRole("heading", { name: "Uploaded E2E" }),
    ).toBeVisible();
    await expect(page.getByText("Upload body.")).toBeVisible();
    await expect(
      page.locator('[data-slot="badge"]').filter({ hasText: /^Uploaded$/ }),
    ).toBeVisible();

    await page.goto("/reports");
    await page.waitForLoadState("networkidle");

    const reportCard = reportCardByText(page, uploadSlug).first();
    await expect(reportCard).toBeVisible();
    await reportCard.getByRole("button", { name: /open actions/i }).click();
    await page.getByRole("menuitem", { name: /delete/i }).click();
    await page.getByRole("button", { name: /^delete$/i }).click();
    await expectReportDeleted(page, request, uploadSlug, uploadSlug);
  });

  test("generate report from template editor", async ({ page, request }) => {
    const templateResponse = await request.post(`${API_BASE}/templates`, {
      data: {
        name: `E2E Editor Report ${Date.now()}`,
        content: "# Editor Report\n\nTicker: {{inputs.ticker}}",
      },
    });
    expect(templateResponse.ok()).toBeTruthy();
    const template = await templateResponse.json();

    await page.goto(`/templates/${template.id}/edit`);
    await page.waitForLoadState("networkidle");

    const generateBtn = page.getByRole("button", {
      name: /generate report/i,
    });
    await expect(generateBtn).toBeEnabled({ timeout: 5000 });
    await generateBtn.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Generate Report" })).toBeVisible();
    await dialog.getByRole("button", { name: /add input/i }).click();
    await dialog.getByPlaceholder("ticker").fill("ticker");
    await dialog.getByPlaceholder("AAPL").fill("AAPL");
    await dialog.getByRole("button", { name: /^generate$/i }).click();
    await expect(
      page.getByText(/generated/i).or(page.getByText(/failed to generate/i)),
    ).toBeVisible({
      timeout: 15000,
    });

    await page.getByRole("button", { name: "View" }).click();
    await expect(page).toHaveURL(/\/reports\/[a-z0-9_]+/);
    await expect(page.getByText("Ticker: AAPL")).toBeVisible();

    const generatedSlug = page.url().split("/reports/")[1];
    const deleteResponse = await request.delete(`${API_BASE}/reports/${generatedSlug}`);
    expect(deleteResponse.ok()).toBeTruthy();
  });
});
