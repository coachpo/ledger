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

    expect(
      screen.getByRole("heading", { level: 1, name: "Runtime Console" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Updated 2 minutes ago")).toHaveClass(
      "text-xs",
      "text-muted-foreground",
    );
    expect(
      screen.getByText("Ready").closest("[data-slot='badge']"),
    ).toHaveAttribute("data-tone", "success");
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders compact density as a flat unboxed header", () => {
    render(
      <PageContextBar
        density="compact"
        meta="Compact metadata"
        title="Compact Context"
      />,
    );

    const root = screen
      .getByText("Compact Context")
      .closest("[data-slot='page-context-bar']");

    expect(root).toHaveClass("gap-3");
    expect(root?.closest("[data-slot='card']")).not.toBeInTheDocument();
    expect(screen.getByText("Compact metadata")).toHaveAttribute(
      "data-slot",
      "page-context-meta",
    );
  });

  it("places the H1 and description in the same responsive row", () => {
    render(
      <PageContextBar
        description="Default stacked context."
        title="Stacked Context"
      />,
    );

    const title = screen.getByRole("heading", {
      level: 1,
      name: "Stacked Context",
    });
    const description = screen.getByText("Default stacked context.");

    expect(title.parentElement).toBe(description.parentElement);
    expect(title.parentElement).toHaveClass(
      "flex-col",
      "md:flex-row",
      "md:items-baseline",
    );
    expect(description).toHaveAttribute("data-slot", "page-context-description");
    expect(description).toHaveClass(
      "min-w-0",
      "max-w-3xl",
      "text-sm",
      "leading-6",
    );
  });

  it("keeps toolbar status and actions in the right-side area", () => {
    render(
      <PageContextBar
        description="Compact toolbar context."
        layout="toolbar"
        status={
          <ResourceStatusStrip items={[{ label: "Ready", value: "3" }]} />
        }
        title="Toolbar Context"
      />,
    );

    const root = screen
      .getByText("Toolbar Context")
      .closest("[data-slot='page-context-bar']");
    const actionRegion = screen.getByText("Ready").closest(
      "[data-slot='page-context-actions']",
    );

    expect(root).toHaveClass("sm:flex-row", "sm:items-start");
    expect(actionRegion).toHaveClass("sm:ml-3", "sm:justify-end");
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

    const root = screen
      .getByText("Extensions")
      .closest("[data-slot='page-context-bar']");
    const meta = screen.getByText("Backend slim contract");
    const status = screen.getByText("Enabled").closest("[role='list']");

    expect(root).toHaveClass("lg:flex-row", "lg:items-center");
    expect(screen.getByText("Slim route contract.")).toHaveClass("leading-6");
    expect(meta.parentElement).toHaveClass("lg:justify-center");
    expect(status).toBeInTheDocument();
    expect(screen.getByText("3 results returned")).toBeInTheDocument();
  });

  it("stays visual-only without boxed, sticky, or shell-offset chrome", () => {
    render(<PageContextBar title="Visual Context" />);

    const root = screen
      .getByText("Visual Context")
      .closest("[data-slot='page-context-bar']");

    expect(root).not.toBeNull();
    expect(root?.closest("[data-slot='card']")).not.toBeInTheDocument();
    expect(root?.className).not.toMatch(/\bborder\b|\bbg-card\b|\brounded/);
    expect(root?.className).not.toMatch(/\bsticky\b/);
    expect(root?.className).not.toMatch(/\btop-0\b/);
    expect(root?.className).not.toMatch(/\bz-10\b|\bz-20\b/);
  });
});
