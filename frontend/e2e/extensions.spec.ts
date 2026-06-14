import { expect, test, type Page } from "@playwright/test";

const FINANCE_EXTENSION_KEY = "signaldeck.finance";
const FINANCE_EXTENSION_SEGMENT = "signaldeck-finance";
const DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle";
const DIGITAL_ORACLE_EXTENSION_SEGMENT = "signaldeck-digital-oracle";

const financeTools = [
  {
    key: "signaldeck.finance.reports.lookup",
    displayName: "Report Lookup",
    description: "Read persisted SignalDeck reports.",
    module: "app.extensions.signaldeck_finance.tool_specs",
  },
];

const digitalOracleTools = [
  {
    key: "signaldeck.digital_oracle.prediction_markets.lookup",
    displayName: "Prediction Markets",
    description: "Find prediction-market signals.",
    module: "app.extensions.signaldeck_digital_oracle.tool_specs",
  },
  {
    key: "signaldeck.digital_oracle.sec_filings.lookup",
    displayName: "SEC Filings",
    description: "Find SEC filing summaries.",
    module: "app.extensions.signaldeck_digital_oracle.tool_specs",
  },
  {
    key: "signaldeck.digital_oracle.market_sentiment.lookup",
    displayName: "Market Sentiment",
    description: "Read market sentiment snapshots.",
    module: "app.extensions.signaldeck_digital_oracle.tool_specs",
  },
];

function extensionState(
  key: string,
  label: string,
  enabled: boolean,
) {
  return { enabled, key, label };
}

async function installExtensionLifecycleMocks(page: Page) {
  let financeEnabled = true;
  let digitalOracleEnabled = true;

  const extensions = () => [
    extensionState(FINANCE_EXTENSION_KEY, "Finance Workspace", financeEnabled),
    extensionState(
      DIGITAL_ORACLE_EXTENSION_KEY,
      "Digital Oracle Runtime",
      digitalOracleEnabled,
    ),
  ];

  await page.route(/\/api\/extensions(?:\/([^/?]+))?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({ json: { items: extensions() } });
      return;
    }
    if (request.method() === "PATCH") {
      const pathSegments = new URL(request.url()).pathname.split("/");
      const extensionKey = decodeURIComponent(
        pathSegments[pathSegments.length - 1] ?? "",
      );
      const payload = request.postDataJSON() as { enabled: boolean };
      if (extensionKey === FINANCE_EXTENSION_KEY) {
        financeEnabled = payload.enabled;
        await route.fulfill({ json: extensions()[0] });
        return;
      }
      if (extensionKey === DIGITAL_ORACLE_EXTENSION_KEY) {
        digitalOracleEnabled = payload.enabled;
        await route.fulfill({ json: extensions()[1] });
        return;
      }
    }
    await route.fallback();
  });

  await page.route(/\/api\/tools(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      json: {
        items: [
          ...(financeEnabled ? financeTools : []),
          ...(digitalOracleEnabled ? digitalOracleTools : []),
        ],
      },
    });
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
  test("keeps finance and Digital Oracle lifecycle behavior independent", async ({
    page,
  }) => {
    await installExtensionLifecycleMocks(page);

    await page.goto("/");
    await expect(page.getByTestId("nav-dashboard")).toBeVisible();
    await expect(page.getByTestId("nav-reports")).toBeVisible();
    await expect(page.getByText("Digital Oracle Runtime")).toHaveCount(0);

    await page.goto("/extensions");
    await expect(page.getByTestId("route-extensions")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
    const digitalOracleRow = page.getByTestId(
      `extension-row-${DIGITAL_ORACLE_EXTENSION_SEGMENT}`,
    );
    const financeRow = page.getByTestId(
      `extension-row-${FINANCE_EXTENSION_SEGMENT}`,
    );
    await expect(digitalOracleRow).toContainText("Digital Oracle Runtime");
    await expect(digitalOracleRow).toContainText(DIGITAL_ORACLE_EXTENSION_KEY);
    await expect(digitalOracleRow).toContainText("Enabled");
    await expect(financeRow).toContainText("Finance Workspace");
    await expect(financeRow).toContainText(FINANCE_EXTENSION_KEY);
    await expect(financeRow).toContainText("Enabled");
    await expect(page.getByText(/marketplace/i)).toHaveCount(0);
    await expect(page.getByText(/install/i)).toHaveCount(0);
    await expect(page.getByText(/remove/i)).toHaveCount(0);

    await page
      .getByTestId(`extension-toggle-${DIGITAL_ORACLE_EXTENSION_SEGMENT}`)
      .click();
    await expect(digitalOracleRow).toContainText("Disabled");
    await expect(financeRow).toContainText("Enabled");
    await expect(page.getByTestId("nav-reports")).toBeVisible();

    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.getByTestId("extension-disabled-state")).toHaveCount(0);
    const digitalOracleDisabledToolPicker = await openCapabilityToolPicker(page);
    await expect(digitalOracleDisabledToolPicker).toContainText("Report Lookup");
    await expect(digitalOracleDisabledToolPicker).not.toContainText(
      "Prediction Markets",
    );
    await expect(digitalOracleDisabledToolPicker).not.toContainText(
      "SEC Filings",
    );
    await expect(digitalOracleDisabledToolPicker).not.toContainText(
      "Market Sentiment",
    );

    await page.goto("/extensions");
    await page
      .getByTestId(`extension-toggle-${DIGITAL_ORACLE_EXTENSION_SEGMENT}`)
      .click();
    await expect(digitalOracleRow).toContainText("Enabled");
    await page
      .getByTestId(`extension-toggle-${FINANCE_EXTENSION_SEGMENT}`)
      .click();
    await expect(financeRow).toContainText("Disabled");
    await expect(digitalOracleRow).toContainText("Enabled");

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
      "Finance-owned routes, navigation, and tools are paused while this bundled extension is disabled.",
    );
    await expect(page.getByTestId("extension-disabled-state")).toContainText(
      "Blast radius",
    );
    const financeDisabledToolPicker = await openCapabilityToolPicker(page);
    await expect(financeDisabledToolPicker).not.toContainText("Report Lookup");
    await expect(financeDisabledToolPicker).toContainText("Prediction Markets");
    await expect(financeDisabledToolPicker).toContainText("SEC Filings");
    await expect(financeDisabledToolPicker).toContainText("Market Sentiment");

    await page.goto("/extensions");
    await expect(digitalOracleRow).toContainText("Enabled");
    await expect(financeRow).toContainText("Disabled");
    await page
      .getByTestId(`extension-toggle-${FINANCE_EXTENSION_SEGMENT}`)
      .click();
    await expect(financeRow).toContainText("Enabled");
    await expect(page.getByTestId("nav-dashboard")).toBeVisible();
    await expect(page.getByTestId("nav-portfolios")).toBeVisible();
    await expect(page.getByTestId("nav-templates")).toBeVisible();
    await expect(page.getByTestId("nav-reports")).toBeVisible();
  });
});
