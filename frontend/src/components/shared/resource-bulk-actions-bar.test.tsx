import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResourceBulkActionsBar } from "./resource-bulk-actions-bar";

describe("ResourceBulkActionsBar", () => {
  it("renders nothing when no resources are selected", () => {
    render(
      <ResourceBulkActionsBar
        resourceLabel="reports"
        selectedCount={0}
        testId="bulk-actions"
        totalCount={4}
        onClear={() => {}}
        onDeleteSelected={() => {}}
      />,
    );

    expect(screen.queryByTestId("bulk-actions")).not.toBeInTheDocument();
  });

  it("renders selected-count summary and route-owned action callbacks", () => {
    const onClear = vi.fn();
    const onDeleteSelected = vi.fn();

    render(
      <ResourceBulkActionsBar
        resourceLabel="reports"
        selectedCount={2}
        testId="bulk-actions"
        totalCount={4}
        onClear={onClear}
        onDeleteSelected={onDeleteSelected}
      />,
    );

    expect(screen.getByTestId("bulk-actions")).toHaveTextContent(
      "2 of 4 reports selected",
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    expect(onDeleteSelected).toHaveBeenCalledTimes(1);
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("allows callers to provide a route-specific summary", () => {
    render(
      <ResourceBulkActionsBar
        deletePending
        resourceLabel="scheduled tasks"
        selectedCount={1}
        summary="1 selected from the current page"
        totalCount={12}
        onClear={() => {}}
        onDeleteSelected={() => {}}
      />,
    );

    expect(screen.getByText("1 selected from the current page")).toBeVisible();
    expect(screen.getByRole("button", { name: "Delete selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
  });
});
