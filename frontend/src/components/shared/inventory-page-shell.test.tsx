import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InventoryPageShell } from "./inventory-page-shell";

function shellRegions() {
  return Array.from(
    screen
      .getByTestId("inventory-shell")
      .querySelectorAll("[data-inventory-shell-region]"),
  ).map((element) => element.getAttribute("data-inventory-shell-region"));
}

describe("InventoryPageShell", () => {
  it("renders context, toolbar, filters, and content in the inventory order", () => {
    render(
      <InventoryPageShell
        filterBar={{ summary: "1 active filter", testId: "inventory-filters" }}
        pageContext={{ title: "Workflow Packages" }}
        testId="inventory-shell"
        toolbar={{ resultSummary: "3 packages shown" }}
      >
        <section data-testid="inventory-results">Package rows</section>
      </InventoryPageShell>,
    );

    expect(shellRegions()).toEqual([
      "context",
      "toolbar",
      "filters",
      "content",
    ]);
    expect(screen.getByText("Workflow Packages")).toBeInTheDocument();
    expect(screen.getByText("3 packages shown")).toBeInTheDocument();
    expect(screen.getByTestId("inventory-filters")).toHaveTextContent(
      "1 active filter",
    );
    expect(screen.getByTestId("inventory-results")).toHaveTextContent(
      "Package rows",
    );
  });

  it("omits the filter region when callers have no active filter bar", () => {
    render(
      <InventoryPageShell
        pageContext={{ title: "Reports" }}
        testId="inventory-shell"
        toolbar={{ resultSummary: "No reports loaded" }}
      >
        <div>Report rows</div>
      </InventoryPageShell>,
    );

    expect(shellRegions()).toEqual(["context", "toolbar", "content"]);
    expect(screen.queryByTestId("inventory-filters")).not.toBeInTheDocument();
  });

  it("omits the toolbar region when callers move summary into compact route context", () => {
    render(
      <InventoryPageShell
        pageContext={{ title: "Extensions" }}
        testId="inventory-shell"
        toolbar={null}
      >
        <div>Extension rows</div>
      </InventoryPageShell>,
    );

    expect(shellRegions()).toEqual(["context", "content"]);
    expect(
      screen.queryByText(/bundled extension returned/i),
    ).not.toBeInTheDocument();
  });

  it("keeps route-owned content after shared controls instead of nesting controls in results", () => {
    render(
      <InventoryPageShell
        pageContext={{
          actions: <button type="button">Create</button>,
          title: "Runs",
        }}
        testId="inventory-shell"
        toolbar={{ resultSummary: "4 runs shown" }}
      >
        <section data-testid="inventory-results">Run rows</section>
      </InventoryPageShell>,
    );

    const shell = screen.getByTestId("inventory-shell");
    const toolbar = shell.querySelector(
      '[data-inventory-shell-region="toolbar"]',
    );
    const content = shell.querySelector(
      '[data-inventory-shell-region="content"]',
    );

    if (!toolbar || !content) {
      throw new Error("Expected inventory toolbar and content regions.");
    }

    expect(shellRegions()).toEqual(["context", "toolbar", "content"]);
    expect(toolbar).not.toContainElement(
      screen.getByTestId("inventory-results"),
    );
    expect(content).toContainElement(screen.getByTestId("inventory-results"));
    expect(
      toolbar.compareDocumentPosition(content) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
