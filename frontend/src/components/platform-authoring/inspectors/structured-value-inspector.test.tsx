import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(textContent.indexOf("alpha")).toBeLessThan(
      textContent.indexOf("zebra"),
    );
  });

  it("can preserve object insertion order in the compact tree presentation", () => {
    render(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        label={null}
        preserveObjectKeyOrder
        presentation="tree"
        value={{ zebra: [], alpha: {} }}
      />,
    );

    const inspector = screen.getByTestId("structured-value-inspector");
    const textContent = inspector.textContent ?? "";

    expect(inspector.querySelector("pre")).toBeNull();
    expect(screen.getByText("Empty object")).toBeInTheDocument();
    expect(screen.getByText("Empty array")).toBeInTheDocument();
    expect(textContent.indexOf("zebra")).toBeLessThan(
      textContent.indexOf("alpha"),
    );
  });

  it("renders multiline strings as raw JSON by default with a plain text view", () => {
    render(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        label={null}
        presentation="tree"
        value={{ message: "Line one\nLine two" }}
      />,
    );

    const inspector = screen.getByTestId("structured-value-inspector");
    const rawValue = inspector.querySelector(
      '[data-structured-string-view="raw"]',
    );

    expect(
      screen.getByRole("tablist", { name: "message string view modes" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Raw JSON" })).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(rawValue).toHaveTextContent('"Line one\\nLine two"');
    expect(screen.getByRole("tab", { name: "Plain text" })).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Markdown" }),
    ).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Plain text" }), {
      button: 0,
    });

    const plainValue = inspector.querySelector(
      '[data-structured-string-view="plain-text"]',
    );
    expect(plainValue?.textContent).toBe("Line one\nLine two");
  });

  it("gates markdown preview behind an explicit inspector opt-in", () => {
    const markdownContent = [
      "| Symbol | Rating |",
      "| --- | --- |",
      "| AAPL | Buy |",
      "",
      "![Chart](https://example.com/chart.png)",
      "",
      "[Docs](https://example.com/docs)",
    ].join("\n");
    const { rerender } = render(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        label={null}
        presentation="tree"
        value={{ report: markdownContent }}
      />,
    );

    let inspector = screen.getByTestId("structured-value-inspector");
    expect(
      screen.getByRole("tablist", { name: "report string view modes" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Markdown" }),
    ).not.toBeInTheDocument();
    expect(inspector.querySelector("table")).toBeNull();

    rerender(
      <StructuredValueInspector
        data-testid="structured-value-inspector"
        enableMarkdownStringPreview
        label={null}
        presentation="tree"
        value={{ report: markdownContent }}
      />,
    );

    inspector = screen.getByTestId("structured-value-inspector");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Markdown" }), {
      button: 0,
    });

    expect(
      inspector.querySelector('[data-structured-string-view="markdown"]'),
    ).toBeInTheDocument();
    expect(inspector.querySelector("table")).toBeInTheDocument();
    expect(inspector.querySelector("img")).toBeNull();
    expect(screen.getByText("[Image omitted: Chart]")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute(
      "rel",
      "noreferrer noopener",
    );
  });
});
