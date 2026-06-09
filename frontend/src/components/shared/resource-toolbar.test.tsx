import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";

import { ResourceFilterBar } from "./resource-filter-bar";
import { ResourceToolbar } from "./resource-toolbar";

describe("ResourceToolbar", () => {
  it("renders compact search controls with caller-owned handlers", () => {
    const onSearchChange = vi.fn();

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
      />,
    );

    const searchInput = screen.getByRole("textbox", {
      name: "Search packages",
    });
    expect(searchInput).toHaveClass("h-8", "pl-8", "text-xs");
    expect(screen.getByText("3 packages shown")).toHaveClass(
      "text-muted-foreground",
    );
    expect(screen.queryByRole("radio", { name: "Cards view" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Table view" })).not.toBeInTheDocument();

    fireEvent.change(searchInput, { target: { value: "beta" } });

    expect(onSearchChange).toHaveBeenCalledWith("beta");
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
});
