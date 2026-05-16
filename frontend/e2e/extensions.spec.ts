import { expect, test, type Page } from "@playwright/test";

const FINANCE_EXTENSION_KEY = "signaldeck.finance";
const FINANCE_EXTENSION_SEGMENT = "signaldeck-finance";

const financeTools = [
  {
    key: "signaldeck.reports.lookup",
    displayName: "Report Lookup",
    description: "Read persisted SignalDeck reports.",
    module: "app.extensions.signaldeck_finance.tool_specs",
  },
];

function financeExtension(enabled: boolean) {
  return {
    key: FINANCE_EXTENSION_KEY,
    label: "Finance Workspace",
    enabled,
  };
}

async function installExtensionLifecycleMocks(page: Page) {
  let enabled = true;

  await page.route(
    /\/api\/extensions(?:\/signaldeck\.finance)?(?:\?.*)?$/,
    async (route) => {
      const request = route.request();
      if (request.method() === "GET") {
        await route.fulfill({
          json: { items: [financeExtension(enabled)] },
        });
        return;
      }
      if (request.method() === "PATCH") {
        const payload = request.postDataJSON() as { enabled: boolean };
        enabled = payload.enabled;
        await route.fulfill({ json: financeExtension(enabled) });
        return;
      }
      await route.fallback();
    },
  );

  await page.route(/\/api\/tools(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: enabled ? financeTools : [] } });
  });

  await page.route(
    /\/api\/v1\/(reports|templates)(?:\?.*)?$/,
    async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: [] });
        return;
      }
      await route.fallback();
    },
  );

  await page.route(/\/api\/model-connections(?:\?.*)?$/, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    await route.fallback();
  });
}

async function openCapabilityToolPicker(page: Page) {
  await page.goto("/workflow-packages/new");
  await expect(page.getByTestId("workflow-package-editor-shell")).toBeVisible();
  await page.getByRole("tab", { name: "Capability Profiles tab" }).click();
  await page.getByRole("button", { name: "Add Profile" }).click();
  return page.getByTestId("capability-tool-command");
}

test.describe("Extension lifecycle browser matrix", () => {
  test("hides disabled finance UI and restores nav, routes, and authoring tools", async ({
    page,
  }) => {
    await installExtensionLifecycleMocks(page);

    await page.goto("/");
    await expect(page.getByTestId("nav-dashboard")).toBeVisible();
    await expect(page.getByTestId("nav-reports")).toBeVisible();

    await page.goto("/extensions");
    const row = page.getByTestId(`extension-row-${FINANCE_EXTENSION_SEGMENT}`);
    await expect(row).toContainText("Toggle whether this bundled extension is available in the app.");
    await expect(row).toContainText("Enabled");
    await page
      .getByTestId(`extension-toggle-${FINANCE_EXTENSION_SEGMENT}`)
      .click();
    await expect(row).toContainText("Disabled");

    await expect(page.getByTestId("nav-dashboard")).toHaveCount(0);
    await expect(page.getByTestId("nav-portfolios")).toHaveCount(0);
    await expect(page.getByTestId("nav-templates")).toHaveCount(0);
    await expect(page.getByTestId("nav-reports")).toHaveCount(0);
    await expect(page.getByTestId("nav-workflow-packages")).toBeVisible();

    await page.goto("/reports");
    await expect(page.getByTestId("extension-disabled-state")).toContainText(
      "Finance Workspace disabled",
    );
    await expect(page.getByTestId("extension-disabled-state")).toContainText(
      "This workspace is unavailable while its bundled extension is disabled.",
    );
    const disabledToolPicker = await openCapabilityToolPicker(page);
    await expect(disabledToolPicker).not.toContainText("Report Lookup");

    await page.goto("/extensions");
    await page
      .getByTestId(`extension-toggle-${FINANCE_EXTENSION_SEGMENT}`)
      .click();
    await expect(row).toContainText("Toggle whether this bundled extension is available in the app.");
    await expect(row).toContainText("Enabled");

    await expect(page.getByTestId("nav-dashboard")).toBeVisible();
    await expect(page.getByTestId("nav-portfolios")).toBeVisible();
    await expect(page.getByTestId("nav-templates")).toBeVisible();
    await expect(page.getByTestId("nav-reports")).toBeVisible();

    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.getByTestId("extension-disabled-state")).toHaveCount(0);

    const restoredToolPicker = await openCapabilityToolPicker(page);
    await expect(restoredToolPicker).toContainText("Report Lookup");
  });
});
