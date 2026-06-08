import {
  describe,
  expect,
  it,
} from "vitest";

import {
  buildRuntimeInputs,
  createRuntimeInputRow,
  createRuntimeInputRows,
  type RuntimeInputMap,
} from "./runtime-inputs";

describe("runtime-inputs", () => {
  it("creates rows with the requested prefix and seeded values", () => {
    const row = createRuntimeInputRow("template", "ticker", "AAPL");

    expect(row.id).toMatch(/^template-runtime-input-\d+$/);
    expect(row.key).toBe("ticker");
    expect(row.value).toBe("AAPL");
  });

  it("creates row lists from runtime input maps", () => {
    const runtimeInputs = {
      ticker: "MSFT",
      portfolio_slug: "growth",
    } satisfies RuntimeInputMap;

    expect(createRuntimeInputRows("report", runtimeInputs)).toEqual([
      expect.objectContaining({ key: "ticker", value: "MSFT" }),
      expect.objectContaining({ key: "portfolio_slug", value: "growth" }),
    ]);
  });

  it("builds runtime inputs from non-empty trimmed rows", () => {
    const rows = [
      { id: "one", key: " ticker ", value: " MSFT " },
      { id: "two", key: "", value: "ignored" },
      { id: "three", key: "portfolio_slug", value: "   " },
    ];

    expect(buildRuntimeInputs(rows)).toEqual({ ticker: "MSFT" });
  });
});
