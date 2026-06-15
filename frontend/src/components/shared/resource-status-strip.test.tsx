import type { ComponentType } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResourceStatusStrip } from "./resource-status-strip";

async function loadResourceStatusBadge() {
  const modulePath = "./resource-status-strip";
  const module = await import(modulePath);
  return module.ResourceStatusBadge as ComponentType<{
    label: string;
    tone?: "neutral" | "success" | "warning" | "danger" | "muted";
  }>;
}

describe("ResourceStatusStrip", () => {
  it("renders status items with deterministic tone badges", () => {
    render(
      <ResourceStatusStrip
        density="toolbar"
        items={[
          { label: "Ready", tone: "success", value: "3 checks" },
          { description: "review", label: "Warning", tone: "warning" },
          { label: "Blocked", tone: "danger", value: "1 issue" },
        ]}
      />,
    );

    expect(screen.getByRole("list")).toHaveClass("px-2", "py-0.5", "text-xs");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Ready").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "success");
    expect(screen.getByText("Warning").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("Blocked").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "danger");
  });

  it("renders numeric zero values without showing empty falsy values", () => {
    render(
      <ResourceStatusStrip
        items={[
          { label: "Tokens", value: 0 },
          { label: "Cost", value: "" },
        ]}
      />,
    );

    expect(screen.getByText("0")).toBeVisible();
    expect(screen.getByText("Cost").closest("[role='listitem']")).toHaveTextContent(/^Cost$/);
  });

  it("renders deterministic empty status copy", () => {
    render(<ResourceStatusStrip emptyLabel="No runtime status" items={[]} />);

    expect(screen.getByText("No runtime status")).toHaveClass("border", "bg-card/70", "text-muted-foreground", "shadow-ui-xs");
  });

  it("exports a reusable status badge helper for shared callers", async () => {
    const ResourceStatusBadge = await loadResourceStatusBadge();

    render(<ResourceStatusBadge label="Queued" tone="warning" />);

    expect(screen.getByText("Queued").closest("[data-slot='badge']")).toHaveAttribute(
      "data-tone",
      "warning",
    );
  });
});
