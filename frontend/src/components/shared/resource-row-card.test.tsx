import type { ReactElement } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { EvidenceCluster } from "./evidence-cluster";
import { ProvenanceBadge } from "./provenance-badge";
import { EntityListCard, ResourceRowCard } from "./resource-row-card";
import { ResourceStatusStrip } from "./resource-status-strip";

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
    expect(row).toHaveClass(
      "overflow-hidden",
      "transition-[background-color,border-color,box-shadow]",
      "hover:bg-accent/35",
      "shadow-ui-xs",
    );
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
        description="Compact plus description"
        metadata="Compact plus metadata"
        subtitle="Compact plus subtitle"
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
    expect(screen.getByText("Compact plus subtitle")).toHaveClass("text-xs", "text-muted-foreground");
    expect(screen.getByText("Compact plus description")).toHaveClass("text-sm", "text-muted-foreground");
    expect(screen.getByText("Compact plus metadata")).toHaveClass("text-xs", "text-muted-foreground");
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

  it("renders facts and evidence chip slots inside the shared body without wrapping the primary link", () => {
    renderResourceRowCard(
      <ResourceRowCard
        density="compactPlus"
        evidenceChips={
          <div className="flex flex-wrap gap-1.5">
            <span>Responses</span>
            <span>Passed</span>
          </div>
        }
        factsGrid={
          <dl className="grid gap-1 sm:grid-cols-2">
            <div>
              <dt>Stable key</dt>
              <dd>primary_model</dd>
            </div>
            <div>
              <dt>Timeout</dt>
              <dd>90s</dd>
            </div>
          </dl>
        }
        primaryAction={{ kind: "link", label: "Open Model Connection", to: "/model-connections/9/edit" }}
        testId="model-connection-row"
        title="Primary Compatible"
      />,
    );

    const primaryLink = screen.getByRole("link", {
      name: "Open Model Connection",
    });
    const stableKey = screen.getByText("Stable key");
    const responsesChip = screen.getByText("Responses");

    expect(screen.getByTestId("model-connection-row")).toBeInTheDocument();
    expect(stableKey).toBeInTheDocument();
    expect(screen.getByText("primary_model")).toBeInTheDocument();
    expect(screen.getByText("Timeout")).toBeInTheDocument();
    expect(screen.getByText("90s")).toBeInTheDocument();
    expect(responsesChip).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(primaryLink).not.toContainElement(stableKey);
    expect(primaryLink).not.toContainElement(responsesChip);
  });

  it("renders shared status, provenance, evidence, and footer slots without wrapping actions", () => {
    renderResourceRowCard(
      <ResourceRowCard
        actions={<button type="button">Archive</button>}
        evidence={<EvidenceCluster items={[{ label: "Trace", value: "trace-123" }]} layout="inline" />}
        footer="Footer metadata"
        provenance={<ProvenanceBadge detail="snapshot" label="Imported" />}
        primaryAction={{ kind: "link", label: "Open Evidence", to: "/resources/evidence" }}
        statusStrip={<ResourceStatusStrip items={[{ label: "Ready", tone: "success" }]} />}
        title="Evidence Resource"
      />,
    );

    const primaryLink = screen.getByRole("link", { name: "Open Evidence" });
    const archiveButton = screen.getByRole("button", { name: "Archive" });

    expect(screen.getByText("Ready").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "success");
    expect(screen.getByLabelText("Imported: snapshot")).toBeInTheDocument();
    expect(screen.getByText("Trace")).toBeInTheDocument();
    expect(screen.getByText("Footer metadata")).toHaveClass("text-[11px]", "text-muted-foreground");
    expect(primaryLink).not.toContainElement(archiveButton);
    expect(archiveButton.closest("a")).toBeNull();
  });
});
