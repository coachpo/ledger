import type { ComponentType, ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

type InlineStatePanelProps = {
  children?: ReactNode;
  className?: string;
  description?: ReactNode;
  icon?: ReactNode;
  testId?: string;
  title?: ReactNode;
  tone?: "neutral" | "warning" | "danger";
};

async function loadInlineStatePanel() {
  const modulePath = "./inline-state-panel";
  const module = await import(modulePath);
  return module.InlineStatePanel as ComponentType<InlineStatePanelProps>;
}

describe("InlineStatePanel", () => {
  it("renders dashed inline panel chrome with icon, copy, children, and custom class names", async () => {
    const InlineStatePanel = await loadInlineStatePanel();

    render(
      <InlineStatePanel
        className="custom-panel"
        description="Shows the latest connection sync state."
        icon={<span data-testid="panel-icon">!</span>}
        testId="inline-state-panel"
        title="Sync status"
      >
        <button type="button">Retry</button>
      </InlineStatePanel>,
    );

    const panel = screen.getByTestId("inline-state-panel");
    expect(panel).toHaveClass("border-dashed", "custom-panel");
    expect(screen.getByRole("alert")).toHaveAttribute("data-tone", "neutral");
    expect(screen.getByText("Sync status")).toBeVisible();
    expect(screen.getByText("Shows the latest connection sync state.")).toBeVisible();
    expect(screen.getByTestId("panel-icon")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  it("supports description-only danger copy without a title", async () => {
    const InlineStatePanel = await loadInlineStatePanel();

    render(
      <InlineStatePanel
        description="Leave this unwired to skip the source entirely."
        tone="danger"
      />,
    );

    expect(screen.getByRole("alert")).toHaveAttribute("data-tone", "danger");
    expect(screen.getByText("Leave this unwired to skip the source entirely.")).toBeVisible();
  });
});
