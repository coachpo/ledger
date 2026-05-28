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
        status={
          <ResourceStatusStrip items={[{ label: "Ready", tone: "success" }]} />
        }
        title="Runtime Console"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(screen.getByText("Runtime Console")).toBeInTheDocument();
    expect(screen.getByText("Updated 2 minutes ago")).toHaveClass(
      "text-xs",
      "text-muted-foreground",
    );
    expect(
      screen.getByText("Ready").closest("[data-slot='badge']"),
    ).toHaveAttribute("data-tone", "success");
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

    expect(
      screen.getByText("Compact Context").closest("[data-slot='card-header']"),
    ).toHaveClass("px-4", "pt-4");
    expect(
      screen.getByText("Compact metadata").closest("[data-slot='card-content']"),
    ).toHaveClass("px-4", "pb-3");
  });

  it("keeps stacked layout as the default and uses toolbar layout only when requested", () => {
    const { rerender } = render(
      <PageContextBar
        description="Default stacked context."
        title="Stacked Context"
      />,
    );

    expect(
      screen.getByText("Stacked Context").closest("[data-slot='card-header']"),
    ).toBeInTheDocument();

    rerender(
      <PageContextBar
        description="Compact toolbar context."
        layout="toolbar"
        status={
          <ResourceStatusStrip items={[{ label: "Ready", value: "3" }]} />
        }
        title="Toolbar Context"
      />,
    );

    expect(
      screen.getByText("Toolbar Context").closest("[data-slot='card-header']"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Toolbar Context").closest("[data-slot='card-content']"),
    ).toHaveClass("p-3", "sm:flex-row", "sm:items-center");
    expect(screen.getByText("Toolbar Context").parentElement).toHaveClass(
      "sm:flex-row",
      "sm:items-baseline",
    );
    expect(screen.getByText("Compact toolbar context.")).toHaveClass(
      "min-w-0",
      "truncate",
      "text-xs",
    );
    expect(
      screen.getByText("Ready").closest("[role='list']"),
    ).toBeInTheDocument();
  });

  it("can place toolbar metadata between title copy and status when requested", () => {
    render(
      <PageContextBar
        actions={<span>3 results returned</span>}
        description="Slim route contract."
        layout="toolbar"
        meta={<span>Backend slim contract</span>}
        status={
          <ResourceStatusStrip items={[{ label: "Enabled", value: "1" }]} />
        }
        title="Extensions"
        toolbarMetaPlacement="middle"
      />,
    );

    const content = screen
      .getByText("Extensions")
      .closest("[data-slot='card-content']");
    const meta = screen.getByText("Backend slim contract");
    const status = screen.getByText("Enabled").closest("[role='list']");

    expect(content).toHaveClass("lg:flex-row", "lg:items-center");
    expect(screen.getByText("Slim route contract.")).not.toHaveClass(
      "truncate",
    );
    expect(meta.parentElement).toHaveClass("lg:justify-center");
    expect(status).toBeInTheDocument();
    expect(screen.getByText("3 results returned")).toBeInTheDocument();
  });

  it("stays visual-only without sticky positioning or shell offsets", () => {
    render(<PageContextBar title="Visual Context" />);

    const card = screen
      .getByText("Visual Context")
      .closest("[data-slot='card']");

    expect(card).not.toBeNull();
    expect(card?.className).not.toMatch(/\bsticky\b/);
    expect(card?.className).not.toMatch(/\btop-0\b/);
    expect(card?.className).not.toMatch(/\bz-10\b|\bz-20\b/);
  });
});
