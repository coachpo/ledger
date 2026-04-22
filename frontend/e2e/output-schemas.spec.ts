import { expect, test, type Page } from "@playwright/test";

async function expectRawJsonAuthoringAbsent(page: Page) {
  await expect(page.getByRole("tab", { name: /json schema/i })).toHaveCount(0);
  await expect(page.getByTestId("output-schema-json-editor")).toHaveCount(0);
}

async function saveAndWaitForEditRoute(page: Page) {
  await Promise.all([
    page.waitForURL(/\/output-schemas\/\d+\/edit$/),
    page.getByTestId("output-schemas-save").click(),
  ]);
}

test.describe("Output schema routes", () => {
  test("covers list navigation, builder-only authoring, preview rendering, and edit persistence", async ({
    page,
  }) => {
    const draftKey = `draft_schema_${Date.now()}`;

    await page.goto("/output-schemas");
    await expect(page.getByTestId("platform-output-schemas-page")).toBeVisible();
    await page.getByTestId("output-schemas-new").click();
    await expect(page).toHaveURL(/\/output-schemas\/new$/);
    await expect(page.getByRole("tab", { name: /builder/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /preview/i })).toBeVisible();
    await expectRawJsonAuthoringAbsent(page);

    await page.getByLabel("Key").fill(draftKey);
    await page.locator("#output-schema-name").fill(`Draft ${draftKey}`);
    await page.getByTestId("output-schema-add-field").click();
    await page.getByTestId("output-schema-field-name-0").fill("answer");

    await page.getByRole("tab", { name: /preview/i }).click();
    await expect(page.getByTestId("output-schema-preview")).toContainText("answer");

    await saveAndWaitForEditRoute(page);
    await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);
    await expectRawJsonAuthoringAbsent(page);

    await page.getByRole("tab", { name: /builder/i }).click();
    await page.locator("#output-schema-name").fill(`Updated ${draftKey}`);
    await page.getByTestId("output-schema-add-field").click();
    await page.getByTestId("output-schema-field-name-1").fill("rationale");

    await page.getByRole("tab", { name: /preview/i }).click();
    await expect(page.getByTestId("output-schema-preview")).toContainText("answer");
    await expect(page.getByTestId("output-schema-preview")).toContainText("rationale");

    await saveAndWaitForEditRoute(page);
    await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);

    await page.goto("/output-schemas");
    await expect(page.getByTestId(`output-schemas-row-${draftKey}`)).toBeVisible();
    await page.getByTestId(`output-schemas-open-${draftKey}`).click();
    await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);
    await expect(page.locator("#output-schema-name")).toHaveValue(`Updated ${draftKey}`);
    await expectRawJsonAuthoringAbsent(page);

    await page.getByRole("tab", { name: /preview/i }).click();
    await expect(page.getByTestId("output-schema-preview")).toContainText("answer");
    await expect(page.getByTestId("output-schema-preview")).toContainText("rationale");
  });
});
