import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const API_BASE = "http://127.0.0.1:8001/api/v1";

function reportRowByText(page: Page, text: string) {
  return page.getByRole("row").filter({ hasText: text });
}

async function expectReportDeleted(
  page: Page,
  request: APIRequestContext,
  slug: string,
  rowText: string,
) {
  await expect
    .poll(async () =>
      (await request.get(`${API_BASE}/reports/${slug}`)).status(),
    )
    .toBe(404);
  await expect(reportRowByText(page, rowText)).toHaveCount(0);
}

async function expectNoDocumentOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
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
    await expectSharedDialogShell(page);
    await expect(page.getByRole("dialog")).toContainText("Runtime inputs");

    await page.getByRole("combobox").click();
    await page.getByRole("option", { name: new RegExp(template.name) }).click();
    await page.getByRole("button", { name: /^generate$/i }).click();

    await page.waitForURL(/\/reports\/[a-z0-9_]+/);

    const generatedSlug = page.url().split("/reports/")[1];
    expect(generatedSlug).toMatch(/^[a-z0-9_]+$/);

    const reportResponse = await request.get(
      `${API_BASE}/reports/${generatedSlug}`,
    );
    expect(reportResponse.ok()).toBeTruthy();
    const report = await reportResponse.json();

    const detailHeader = page.getByTestId("report-detail-header");
    await expect(
      detailHeader.getByText("Immutable report snapshot"),
    ).toBeVisible();
    await expect(detailHeader.getByText("Source")).toBeVisible();
    await expect(detailHeader.getByText(generatedSlug)).toHaveCount(2);

    const detailActions = page.getByTestId("report-detail-actions");
    await expect(
      detailActions.getByRole("button", { name: /download/i }),
    ).toBeVisible();
    await expect(
      detailActions.getByRole("button", { name: /edit/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Report content" }),
    ).toHaveCount(0);
    await expect(
      page.getByText(
        "Only markdown content is editable; report identity, source, and slug remain fixed.",
      ),
    ).toHaveCount(0);
    const contentPane = page.getByTestId("report-content-pane");
    await expect(contentPane).toBeVisible();
    await expect(
      page.getByTestId("report-detail-header").getByRole("heading", { name: report.name }),
    ).toBeVisible();
    await expect(
      contentPane.getByRole("heading", { name: "E2E Report" }),
    ).toBeVisible();
    await expect(page.getByText("Hello world.")).toBeVisible();
    await expect(page.getByText("Item one")).toBeVisible();

    await detailActions.getByRole("button", { name: /edit/i }).click();
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible();
    await textarea.fill("# Edited E2E Report\n\nEdited content.");
    const saveButton = detailActions.getByRole("button", { name: /save/i });
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes("/reports/") &&
          response.request().method() === "PATCH",
      ),
      saveButton.evaluate((button) => (button as HTMLButtonElement).click()),
    ]);

    await expect(page.getByTestId("report-content-pane")).toContainText(
      "Edited content.",
    );

    const downloadButton = page.getByRole("button", { name: /download/i });
    await expect(downloadButton).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      downloadButton.click(),
    ]);
    expect(download.suggestedFilename()).toBe(`${generatedSlug}.md`);

    const downloadResponse = await request.get(
      `${API_BASE}/reports/${generatedSlug}/download`,
    );
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

    const reportRow = reportRowByText(page, report.name).first();
    await expect(reportRow).toBeVisible();

    await reportRow.getByRole("button", { name: /open actions/i }).click();
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
    await expectSharedDialogShell(page);
    await expect(page.getByRole("dialog")).toContainText("Required markdown");

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: `${uploadSlug}.md`,
      mimeType: "text/markdown",
      buffer: Buffer.from("# Uploaded E2E\n\nUpload body."),
    });

    await expect(page.getByLabel("Slug")).toHaveValue(uploadSlug);

    await page.getByLabel("Author (optional)").fill("E2E Author");
    await page
      .getByLabel("Description (optional)")
      .fill("Automated upload test");
    await page.getByLabel("Tags (optional)").fill("e2e, upload");

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

    const reportRow = reportRowByText(page, uploadSlug).first();
    await expect(reportRow).toBeVisible();
    await reportRow.getByRole("button", { name: /open actions/i }).click();
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
    await expect(
      dialog.getByRole("heading", { name: "Generate Report" }),
    ).toBeVisible();
    await expectSharedDialogShell(page);
    await expect(dialog).toContainText("Selection");
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
    const deleteResponse = await request.delete(
      `${API_BASE}/reports/${generatedSlug}`,
    );
    expect(deleteResponse.ok()).toBeTruthy();
  });

  test("covers report list empty and API-error states", async ({ page }) => {
    let reportsMode: "empty" | "error" = "empty";

    await page.route(
      /127\.0\.0\.1:8001\/api\/v1\/reports(?:\?.*)?$/,
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }

        if (reportsMode === "error") {
          await route.fulfill({
            contentType: "application/json",
            json: {
              code: "reports_unavailable",
              message: "Reports API unavailable",
            },
            status: 500,
          });
          return;
        }

        await route.fulfill({ json: [] });
      },
    );
    await page.route(
      /127\.0\.0\.1:8001\/api\/v1\/templates(?:\?.*)?$/,
      async (route) => {
        await route.fulfill({ json: [] });
      },
    );

    await page.goto("/reports");
    await expect(page.getByTestId("route-reports-list")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    await expect(page.getByText(/No reports yet/)).toBeVisible();
    await expectNoDocumentOverflow(page);

    reportsMode = "error";
    await page.reload();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("alert")).toContainText(
      "Reports API unavailable",
    );
    await expect(page.locator("body")).not.toContainText(
      "Unexpected Application Error!",
    );
  });
});
