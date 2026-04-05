import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EquityCurveChart } from "./equity-curve-chart";

describe("EquityCurveChart", () => {
  it("toggles benchmark lines without hiding the portfolio curve", async () => {
    render(
      <EquityCurveChart
        curve={[{ date: "2024-01-02", value: "100000.00" }]}
        benchmarkCurves={{ "^GSPC": [{ date: "2024-01-02", value: "1.0000" }] }}
        selectedBenchmarks={["^GSPC"]}
      />,
    );

    expect(screen.getByLabelText(/portfolio/i)).toBeChecked();
    expect(screen.getByLabelText(/\^GSPC/i)).toBeChecked();
  });

  it("sanitizes benchmark symbols before emitting chart CSS variable names", () => {
    render(
      <EquityCurveChart
        curve={[{ date: "2024-01-02", value: "100000.00" }]}
        benchmarkCurves={{ "^GSPC": [{ date: "2024-01-02", value: "1.0000" }] }}
        selectedBenchmarks={["^GSPC"]}
      />,
    );

    const styleText = document.querySelector("style")?.textContent ?? "";

    expect(styleText).not.toContain("--color-^GSPC");
    expect(styleText).toContain("--color-benchmark__GSPC");
  });
});
