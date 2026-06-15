import type { ComponentType, ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

type InventoryStatePanelProps = {
  action?: ReactNode;
  description?: ReactNode;
  testId?: string;
  title: ReactNode;
  tone?: "neutral" | "warning" | "danger";
};

async function loadInventoryStatePanel() {
  const modulePath = "./inventory-state-panel";
  const module = await import(modulePath);
  return module.InventoryStatePanel as ComponentType<InventoryStatePanelProps>;
}

describe("InventoryStatePanel", () => {
  it("keeps shared inventory copy inside tokenized state card chrome", async () => {
    const InventoryStatePanel = await loadInventoryStatePanel();

    render(
      <InventoryStatePanel
        description="Reading the latest run monitor state from the backend."
        testId="inventory-state-panel"
        title="Loading runs"
      />,
    );

    const panel = screen.getByTestId("inventory-state-panel");
    expect(panel).toHaveClass("rounded-xl", "border", "shadow-ui-xs");
    expect(panel.querySelector("[role='alert']")).toHaveAttribute("data-tone", "neutral");
    expect(screen.getByText("Loading runs")).toBeVisible();
    expect(screen.getByText("Reading the latest run monitor state from the backend.")).toBeVisible();
  });

  it("keeps danger tone available for route-owned error copy", async () => {
    const InventoryStatePanel = await loadInventoryStatePanel();

    render(
      <InventoryStatePanel
        description="Templates API unavailable"
        title="Failed to load templates"
        tone="danger"
      />,
    );

    expect(screen.getByRole("alert")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByText("Failed to load templates")).toBeVisible();
    expect(screen.getByText("Templates API unavailable")).toBeVisible();
  });

  it("does not clamp long title-only error copy", async () => {
    const InventoryStatePanel = await loadInventoryStatePanel();

    render(
      <InventoryStatePanel
        title="A very long backend error message should remain fully visible when it is the only copy."
        tone="danger"
      />,
    );

    expect(screen.getByRole("alert")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByText(/A very long backend error message/)).toBeVisible();
    expect(screen.getByText(/A very long backend error message/)).toHaveClass(
      "line-clamp-none",
    );
  });
});
