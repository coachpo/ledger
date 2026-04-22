import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StructuredValueInspector } from "./structured-value-inspector";

describe("StructuredValueInspector", () => {
  it("renders nested objects, arrays, and primitive values without editable controls", () => {
    render(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        label="Preview payload"
        value={{
          status: "complete",
          metadata: {
            attempts: 2,
            success: true,
            notes: null,
            steps: ["fetch", { latencyMs: 12.5, result: "done" }],
          },
        }}
      />,
    );

    const inspector = screen.getByTestId("structured-value-inspector");

    expect(screen.getByText("Preview payload")).toBeInTheDocument();
    expect(screen.getByText("metadata")).toBeInTheDocument();
    expect(screen.getByText("steps")).toBeInTheDocument();
    expect(screen.getByText("[0]")).toBeInTheDocument();
    expect(screen.getByText("[1]")).toBeInTheDocument();
    expect(screen.getByText('"complete"')).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getAllByText("null")).not.toHaveLength(0);
    expect(screen.getByText("12.5")).toBeInTheDocument();
    expect(screen.getByText('"done"')).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(inspector.querySelector("textarea")).toBeNull();
  });

  it("renders empty collections and sorts object keys deterministically", () => {
    render(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        label="Sorted payload"
        value={{ zebra: [], alpha: {} }}
      />,
    );

    const inspector = screen.getByTestId("structured-value-inspector");
    const textContent = inspector.textContent ?? "";

    expect(screen.getByText("Empty object")).toBeInTheDocument();
    expect(screen.getByText("Empty array")).toBeInTheDocument();
    expect(textContent.indexOf("alpha")).toBeLessThan(textContent.indexOf("zebra"));
  });
});
