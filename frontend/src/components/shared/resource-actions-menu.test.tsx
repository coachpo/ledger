import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DropdownMenuItem } from "@/components/ui/dropdown-menu";

import { ResourceActionsMenu } from "./resource-actions-menu";

describe("ResourceActionsMenu", () => {
  it("renders a consistently labelled row action trigger", () => {
    render(
      <ResourceActionsMenu
        ariaLabel="Open actions for Report A"
        testId="report-actions"
      >
        <DropdownMenuItem>Download</DropdownMenuItem>
      </ResourceActionsMenu>,
    );

    const trigger = screen.getByRole("button", {
      name: "Open actions for Report A",
    });

    expect(trigger).toHaveClass("size-8");
    expect(trigger).toHaveAttribute("data-testid", "report-actions");
  });

  it("keeps route-owned action callbacks in the caller", async () => {
    const onSelect = vi.fn();

    render(
      <ResourceActionsMenu ariaLabel="Open actions for Template A">
        <DropdownMenuItem onSelect={onSelect}>Delete</DropdownMenuItem>
      </ResourceActionsMenu>,
    );

    const trigger = screen.getByRole("button", {
      name: "Open actions for Template A",
    });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("supports route-specific trigger variants and content sizing", () => {
    render(
      <ResourceActionsMenu
        ariaLabel="More actions for Schedule A"
        contentClassName="w-48"
        triggerClassName="h-8 w-8"
        triggerVariant="outline"
      >
        <DropdownMenuItem>Edit</DropdownMenuItem>
      </ResourceActionsMenu>,
    );

    expect(
      screen.getByRole("button", { name: "More actions for Schedule A" }),
    ).toHaveClass("h-8", "w-8");
  });
});
