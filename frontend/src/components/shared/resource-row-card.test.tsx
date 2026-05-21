import type { ReactElement } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { EntityListCard, ResourceRowCard } from "./resource-row-card";

function renderResourceRowCard(element: ReactElement) {
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

  it("renders link primary actions as focusable title links", () => {
    renderResourceRowCard(
      <ResourceRowCard
        primaryAction={{ kind: "link", label: "Open Resource", to: "/resources/research", testId: "resource-link" }}
        title="Research Resource"
      />,
    );

    const link = screen.getByRole("link", { name: "Open Resource" });
    expect(link).toHaveAttribute("href", "/resources/research");
    expect(link).toHaveAttribute("data-testid", "resource-link");
    expect(link).toHaveTextContent("Research Resource");
    expect(link).toHaveClass("rounded-sm", "hover:underline", "focus-visible:ring-2");
    expect(link).not.toHaveClass("absolute", "inset-0", "cursor-pointer", "text-left");
    expect(screen.queryByRole("button", { name: "Open Resource" })).not.toBeInTheDocument();
  });

  it("keeps sibling action buttons isolated from the primary link", () => {
    const actionClick = vi.fn();

    renderResourceRowCard(
      <ResourceRowCard
        actions={(
          <button onClick={actionClick} type="button">
            Archive
          </button>
        )}
        primaryAction={{ kind: "link", label: "Open Workflow", to: "/workflow-packages/7" }}
        title="Workflow"
      />,
    );

    const primaryLink = screen.getByRole("link", { name: "Open Workflow" });
    const archiveButton = screen.getByRole("button", { name: "Archive" });

    fireEvent.click(archiveButton);

    expect(actionClick).toHaveBeenCalledTimes(1);
    expect(primaryLink).toHaveAttribute("href", "/workflow-packages/7");
    expect(primaryLink).not.toContainElement(archiveButton);
    expect(archiveButton.closest("a")).toBeNull();
  });

  it("keeps nested body controls outside the primary title link", () => {
    const metadataClick = vi.fn();

    renderResourceRowCard(
      <EntityListCard
        metadata={(
          <div>
            <a href="/workflow-packages/7">Package link</a>
            <button onClick={metadataClick} type="button">
              Inspect metadata
            </button>
          </div>
        )}
        primaryAction={{ kind: "link", label: "Open Run", to: "/runs/12", testId: "run-primary" }}
        title="Workflow"
      />,
    );

    const primaryLink = screen.getByTestId("run-primary");
    const metadataLink = screen.getByRole("link", { name: "Package link" });
    const metadataButton = screen.getByRole("button", { name: "Inspect metadata" });

    fireEvent.click(metadataButton);

    expect(primaryLink).toHaveAttribute("href", "/runs/12");
    expect(primaryLink).not.toContainElement(metadataLink);
    expect(primaryLink).not.toContainElement(metadataButton);
    expect(metadataLink).toHaveAttribute("href", "/workflow-packages/7");
    expect(metadataClick).toHaveBeenCalledTimes(1);
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
        metadata="Created by SignalDeck"
        primaryAction={{ kind: "link", label: "Inspect Resource", to: "/resources/shared", testId: "inspect-resource" }}
        subtitle="Reusable primitive"
        testId="resource-card"
        title="Shared Resource"
      />,
    );

    expect(screen.getByTestId("resource-card")).toBeInTheDocument();
    const inspectResource = screen.getByTestId("inspect-resource");
    expect(inspectResource).toHaveAccessibleName("Inspect Resource");
    expect(inspectResource).toHaveAttribute("href", "/resources/shared");
    expect(inspectResource.parentElement).toHaveClass(
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
    expect(screen.getByText("Created by SignalDeck")).toHaveClass("text-[11px]", "text-muted-foreground");
  });
});
