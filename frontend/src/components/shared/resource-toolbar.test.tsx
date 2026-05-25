import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";

import { ResourceFilterBar } from "./resource-filter-bar";
import { ResourceToolbar } from "./resource-toolbar";

describe("ResourceToolbar", () => {
  it("renders compact search and view controls with caller-owned handlers", () => {
    const onSearchChange = vi.fn();
    const onViewModeChange = vi.fn();

    render(
      <ResourceToolbar
        resultSummary="3 packages shown"
        search={{
          id: "package-search",
          label: "Search packages",
          placeholder: "Search packages...",
          value: "alpha",
          onChange: onSearchChange,
        }}
        viewMode="cards"
        onViewModeChange={onViewModeChange}
      />,
    );

    const searchInput = screen.getByRole("textbox", {
      name: "Search packages",
    });
    expect(searchInput).toHaveClass("h-8", "pl-8", "text-xs");
    expect(screen.getByText("3 packages shown")).toHaveClass(
      "text-muted-foreground",
    );

    fireEvent.change(searchInput, { target: { value: "beta" } });
    fireEvent.click(screen.getByRole("radio", { name: "Table view" }));

    expect(onSearchChange).toHaveBeenCalledWith("beta");
    expect(onViewModeChange).toHaveBeenCalledWith("table");
    expect(screen.getByRole("radio", { name: "Cards view" })).toHaveAttribute(
      "data-state",
      "on",
    );
  });

  it("keeps filter affordances, actions, and selection summary presentational", () => {
    const onClearOwner = vi.fn();
    const onClearAll = vi.fn();
    const onExport = vi.fn();

    render(
      <ResourceToolbar
        actions={(
          <Button size="sm" type="button" variant="outline" onClick={onExport}>
            Export
          </Button>
        )}
        filters={(
          <ResourceFilterBar
            summary="Filters"
            testId="resource-filter-bar"
            items={[
              {
                active: true,
                clearLabel: "Clear owner filter",
                id: "owner",
                label: "Owner",
                value: "Finance",
                onClear: onClearOwner,
              },
            ]}
            onClearAll={onClearAll}
          />
        )}
        selectionSummary={<span>2 of 5 selected</span>}
      />,
    );

    const filterBar = screen.getByTestId("resource-filter-bar");
    expect(filterBar).toHaveClass("rounded-md", "border", "bg-muted/30");
    expect(screen.getByText("2 of 5 selected")).toBeInTheDocument();
    expect(screen.getByText("Owner").closest("[data-slot='badge']")).toHaveAttribute(
      "data-active",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear owner filter" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(onClearOwner).toHaveBeenCalledTimes(1);
    expect(onClearAll).toHaveBeenCalledTimes(1);
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("renders caller-supplied view modes without forcing card/table choices", () => {
    const onViewModeChange = vi.fn();

    render(
      <ResourceToolbar
        viewMode="timeline"
        viewModes={[
          { label: "Timeline view", value: "timeline" },
          { label: "Ledger view", value: "ledger" },
        ]}
        onViewModeChange={onViewModeChange}
      />,
    );

    const group = screen.getByRole("group");
    expect(within(group).getByRole("radio", { name: "Timeline view" })).toHaveAttribute(
      "data-state",
      "on",
    );

    fireEvent.click(within(group).getByRole("radio", { name: "Ledger view" }));
    expect(onViewModeChange).toHaveBeenCalledWith("ledger");
  });
});
