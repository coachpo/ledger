import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PageContextBar } from "./page-context-bar";
import { ResourceStatusStrip } from "./resource-status-strip";

describe("PageContextBar", () => {
  it("renders title, context metadata, status, and isolated actions", () => {
    const onRefresh = vi.fn();

    render(
      <PageContextBar
        actions={<button onClick={onRefresh} type="button">Refresh</button>}
        description="Operational context for this route."
        meta="Updated 2 minutes ago"
        status={<ResourceStatusStrip items={[{ label: "Ready", tone: "success" }]} />}
        title="Runtime Console"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(screen.getByText("Runtime Console")).toBeInTheDocument();
    expect(screen.getByText("Updated 2 minutes ago")).toHaveClass("text-xs", "text-muted-foreground");
    expect(screen.getByText("Ready").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "success");
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("applies compact density header and content classes", () => {
    render(
      <PageContextBar
        density="compact"
        meta="Compact metadata"
        title="Compact Context"
      />,
    );

    expect(screen.getByText("Compact Context").closest("[data-slot='card-header']")).toHaveClass("px-4", "pt-4");
    expect(screen.getByText("Compact metadata").closest("[data-slot='card-content']")).toHaveClass("px-4", "pb-3");
  });

  it("stays visual-only without sticky positioning or shell offsets", () => {
    render(<PageContextBar title="Visual Context" />);

    const card = screen.getByText("Visual Context").closest("[data-slot='card']");

    expect(card).not.toBeNull();
    expect(card?.className).not.toMatch(/\bsticky\b/);
    expect(card?.className).not.toMatch(/\btop-0\b/);
    expect(card?.className).not.toMatch(/\bz-10\b|\bz-20\b/);
  });
});
