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
});
