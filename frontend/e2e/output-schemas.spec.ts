import { expect, test, type APIRequestContext } from "@playwright/test";

const PLATFORM_API = "http://127.0.0.1:8001/api";

type OutputSchemaRead = {
  id: number;
  key: string;
};

async function createOutputSchema(request: APIRequestContext, key: string): Promise<OutputSchemaRead> {
  const response = await request.post(`${PLATFORM_API}/output-schemas`, {
    data: {
      key,
      name: `Schema ${key}`,
      kind: "standalone",
      builder: {
        kind: "object",
        allowAdditionalProperties: false,
        fields: [{ name: "summary", required: true, schema: { kind: "string" } }],
      },
      jsonSchema: {
        type: "object",
        properties: { summary: { type: "string" } },
        required: ["summary"],
        additionalProperties: false,
      },
    },
  });

  expect(response.ok()).toBeTruthy();
  return (await response.json()) as OutputSchemaRead;
}

test.describe("Output schema routes", () => {
  test("covers list navigation, builder/json sync, preview rendering, and unsupported keyword feedback", async ({
    page,
    request,
  }) => {
    const seededKey = `seeded_schema_${Date.now()}`;
    const seededSchema = await createOutputSchema(request, seededKey);
    const draftKey = `draft_schema_${Date.now()}`;

    await page.goto("/output-schemas");
    await expect(page.getByTestId("platform-output-schemas-page")).toBeVisible();
    await expect(page.getByTestId(`output-schemas-row-${seededKey}`)).toBeVisible();

    await page.getByTestId(`output-schemas-open-${seededKey}`).click();
    await expect(page).toHaveURL(new RegExp(`/output-schemas/${seededSchema.id}/edit$`));
    await expect(page.getByTestId("output-schemas-editor")).toBeVisible();

    await page.goto("/output-schemas/new");
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
