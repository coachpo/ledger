import { expect, test } from "@playwright/test";

test.describe("Output schema routes", () => {
  test("covers list navigation, builder/json sync, preview rendering, and unsupported keyword feedback", async ({
    page,
  }) => {
    const draftKey = `draft_schema_${Date.now()}`;

    await page.goto("/output-schemas");
    await expect(page.getByTestId("platform-output-schemas-page")).toBeVisible();
    await page.getByTestId("output-schemas-new").click();
    await expect(page).toHaveURL(/\/output-schemas\/new$/);
    await page.getByLabel("Key").fill(draftKey);
    await page.getByLabel("Name").fill(`Draft ${draftKey}`);
    await page.getByTestId("output-schema-add-field").click();
    await page.getByTestId("output-schema-field-name-0").fill("answer");

    await page.getByRole("tab", { name: /json schema/i }).click();
    await expect(page.getByTestId("output-schema-json-editor")).toHaveValue(/"answer"/);

    await page.getByRole("tab", { name: /preview/i }).click();
    await expect(page.getByTestId("output-schema-preview")).toContainText('"answer"');

    await page.getByTestId("output-schemas-save").click();
    await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);

    await page.goto("/output-schemas");
    await expect(page.getByTestId(`output-schemas-row-${draftKey}`)).toBeVisible();
    await page.getByTestId(`output-schemas-open-${draftKey}`).click();
    await expect(page).toHaveURL(/\/output-schemas\/\d+\/edit$/);

    await page.getByRole("tab", { name: /json schema/i }).click();
    await page.getByTestId("output-schema-json-editor").fill(
      JSON.stringify(
        {
          type: "object",
          properties: {},
          patternProperties: { "^x": { type: "string" } },
        },
        null,
        2,
      ),
    );

    await expect(page.getByTestId("output-schema-validation-feedback")).toContainText(
      "patternProperties is not supported",
    );
  });
});
