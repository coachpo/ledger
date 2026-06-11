import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Dialog } from "@/components/ui/dialog";

import { EntityDialogShell } from "./entity-dialog-shell";
import { ResourceStatusStrip } from "./resource-status-strip";

describe("EntityDialogShell", () => {
  it("composes accessible dialog title, description, constraints, body, and footer", () => {
    render(
      <Dialog open>
        <EntityDialogShell
          constraintStrip={<ResourceStatusStrip items={[{ label: "Ready", tone: "success" }]} />}
          description="Review this entity before saving."
          footer={<button type="button">Save entity</button>}
          title="Entity editor"
        >
          <p>Editable entity content</p>
        </EntityDialogShell>
      </Dialog>,
    );

    expect(screen.getByRole("dialog", { name: "Entity editor" })).toBeInTheDocument();
    expect(screen.getByText("Review this entity before saving.")).toBeInTheDocument();
    expect(screen.getByText("Ready").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "success");
    expect(screen.getByText("Editable entity content").closest("[data-slot='entity-dialog-body']")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save entity" }).closest("[data-slot='dialog-footer']")).toBeInTheDocument();
  });

  it("keeps fixed dialog chrome outside a viewport-constrained scroll body", () => {
    render(
      <Dialog open>
        <EntityDialogShell
          constraintStrip={<ResourceStatusStrip items={[{ label: "Blocked", tone: "danger" }]} />}
          description="Review long diagnostics before saving."
          footer={<button type="button">Save entity</button>}
          title="Scrollable entity editor"
        >
          <div>Long body content</div>
        </EntityDialogShell>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog", {
      name: "Scrollable entity editor",
    });
    const header = dialog.querySelector("[data-slot='dialog-header']");
    const constraintStrip = dialog.querySelector(
      "[data-slot='entity-dialog-constraint-strip']",
    );
    const body = dialog.querySelector("[data-slot='entity-dialog-body']");
    const footer = dialog.querySelector("[data-slot='dialog-footer']");
    const separators = dialog.querySelectorAll("[data-slot='separator-root']");

    expect(dialog).toHaveClass(
      "flex",
      "max-h-[calc(100dvh-2rem)]",
      "flex-col",
      "gap-0",
      "overflow-hidden",
      "p-0",
    );
    expect(dialog).not.toHaveClass("grid");
    expect(header).toHaveClass("shrink-0");
    expect(constraintStrip).toHaveClass("shrink-0");
    expect(body).toHaveClass(
      "min-h-0",
      "flex-1",
      "overflow-auto",
      "overscroll-contain",
    );
    expect(footer).toHaveClass("shrink-0");
    expect(Array.from(separators)).toHaveLength(2);
    expect(
      Array.from(separators).every((separator) =>
        separator.classList.contains("shrink-0"),
      ),
    ).toBe(true);
    expect(
      Array.from(
        dialog.querySelectorAll(
          "[data-slot='dialog-header'], [data-slot='entity-dialog-constraint-strip'], [data-slot='separator-root'], [data-slot='entity-dialog-body'], [data-slot='dialog-footer']",
        ),
      ).map((region) => region.getAttribute("data-slot")),
    ).toEqual([
      "dialog-header",
      "entity-dialog-constraint-strip",
      "separator-root",
      "entity-dialog-body",
      "separator-root",
      "dialog-footer",
    ]);
  });
});
