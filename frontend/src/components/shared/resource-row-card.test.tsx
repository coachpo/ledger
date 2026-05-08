import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { ResourceRowCard } from "./resource-row-card";

function renderResourceRowCard(element: React.ReactElement) {
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

describe("ResourceRowCard", () => {
  it("renders a non-interactive primary body when primaryAction is omitted", () => {
    renderResourceRowCard(
      <ResourceRowCard
        badges={<span>Draft</span>}
        metadata="Updated today"
        testId="resource-row"
        title="Quarterly Report"
      />,
    );

    const row = screen.getByTestId("resource-row");
    expect(row).toHaveClass("overflow-hidden", "transition-colors", "hover:bg-accent/50");
    expect(within(row).queryByRole("button", { name: /quarterly report/i })).not.toBeInTheDocument();
    expect(within(row).queryByRole("link", { name: /quarterly report/i })).not.toBeInTheDocument();
  });

  it("calls the button primary action handler", () => {
    const onClick = vi.fn();

    renderResourceRowCard(
      <ResourceRowCard
        badges={<span>Draft</span>}
        description={<div data-testid="rich-description">Prepared for review</div>}
        metadata="Updated today"
        primaryAction={{ kind: "button", label: "Open Quarterly Report", onClick, testId: "primary-action" }}
        subtitle="Financial reports"
        title="Quarterly Report"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open Quarterly Report" }));

    const primaryAction = screen.getByTestId("primary-action");
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(primaryAction).toHaveAttribute("type", "button");
    expect(primaryAction).toHaveClass("absolute", "inset-0", "cursor-pointer", "text-left");
    expect(primaryAction.parentElement).toHaveClass("relative", "min-w-0", "flex-1", "text-left");
    expect(primaryAction.querySelector("div")).not.toBeInTheDocument();
    expect(screen.getByTestId("rich-description")).not.toBe(primaryAction);
    expect(primaryAction.contains(screen.getByTestId("rich-description"))).toBe(false);
  });

  it("renders link primary actions with an href", () => {
    renderResourceRowCard(
      <ResourceRowCard
        primaryAction={{ kind: "link", label: "Open Resource", to: "/resources/research", testId: "resource-link" }}
        title="Research Resource"
      />,
    );

    const link = screen.getByRole("link", { name: "Open Resource" });
    expect(link).toHaveAttribute("href", "/resources/research");
    expect(link).toHaveAttribute("data-testid", "resource-link");
  });

  it("keeps sibling actions isolated from the primary button", () => {
    const primaryClick = vi.fn();
    const actionClick = vi.fn();

    renderResourceRowCard(
      <ResourceRowCard
        actions={(
          <button onClick={actionClick} type="button">
            Archive
          </button>
        )}
        primaryAction={{ kind: "button", label: "Open Workflow", onClick: primaryClick }}
        title="Workflow"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Archive" }));

    expect(actionClick).toHaveBeenCalledTimes(1);
    expect(primaryClick).not.toHaveBeenCalled();
  });

  it("applies compact density classes", () => {
    renderResourceRowCard(
      <ResourceRowCard
        actions={<button type="button">More</button>}
        density="compact"
        testId="compact-row"
        title="Compact Row"
      />,
    );

    const content = screen.getByTestId("compact-row").querySelector("[data-slot='card-content']");
    expect(content).toHaveClass("flex", "items-center", "justify-between", "gap-3", "px-4", "py-3");
    expect(screen.getByRole("button", { name: "More" }).parentElement).toHaveClass(
      "flex",
      "shrink-0",
      "items-center",
      "gap-1.5",
    );
  });

  it("applies compactPlus density classes", () => {
    renderResourceRowCard(
      <ResourceRowCard
        actions={<button type="button">Run</button>}
        density="compactPlus"
        testId="compact-plus-row"
        title="Compact Plus Row"
      />,
    );

    const content = screen.getByTestId("compact-plus-row").querySelector("[data-slot='card-content']");
    expect(content).toHaveClass(
      "flex",
      "min-w-0",
      "flex-col",
      "gap-3",
      "p-3",
      "sm:flex-row",
      "sm:items-start",
      "sm:justify-between",
      "sm:p-4",
    );
    expect(screen.getByRole("button", { name: "Run" }).parentElement).toHaveClass(
      "flex",
      "w-full",
      "flex-wrap",
      "gap-2",
      "sm:w-auto",
      "sm:shrink-0",
      "sm:justify-end",
      "[&_button]:cursor-pointer",
    );
  });

  it("preserves row and primary action test id contracts", () => {
    renderResourceRowCard(
      <ResourceRowCard
        description="A long description that should remain inside the primary body."
        metadata="Created by Ledger"
        primaryAction={{ kind: "button", label: "Inspect Resource", onClick: vi.fn(), testId: "inspect-resource" }}
        subtitle="Reusable primitive"
        testId="resource-card"
        title="Shared Resource"
      />,
    );

    expect(screen.getByTestId("resource-card")).toBeInTheDocument();
    const inspectResource = screen.getByTestId("inspect-resource");
    expect(inspectResource).toHaveAccessibleName("Inspect Resource");
    expect(inspectResource.parentElement).toHaveTextContent("Shared Resource");
    expect(screen.getByText("Shared Resource")).toHaveClass(
      "text-sm",
      "font-medium",
      "leading-5",
      "tracking-tight",
      "text-foreground",
    );
    expect(screen.getByText("Reusable primitive")).toHaveClass("text-[11px]", "text-muted-foreground");
    expect(screen.getByText("A long description that should remain inside the primary body.")).toHaveClass(
      "break-words",
      "text-[11px]",
      "text-muted-foreground",
    );
    expect(screen.getByText("Created by Ledger")).toHaveClass("text-[11px]", "text-muted-foreground");
  });
});
