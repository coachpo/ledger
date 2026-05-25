import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PortfolioFormDialog } from "./portfolio-form-dialog";

function expectSharedDialogShell(dialog: HTMLElement) {
  const constraintStrip = dialog.querySelector(
    '[data-slot="entity-dialog-constraint-strip"]',
  );
  const body = dialog.querySelector('[data-slot="entity-dialog-body"]');
  const footer = dialog.querySelector('[data-slot="dialog-footer"]');

  expect(constraintStrip).toBeTruthy();
  expect(body).toBeTruthy();
  expect(footer).toBeTruthy();
  expect(
    Array.from(
      dialog.querySelectorAll(
        '[data-slot="entity-dialog-constraint-strip"], [data-slot="entity-dialog-body"], [data-slot="dialog-footer"]',
      ),
    ),
  ).toEqual([constraintStrip, body, footer]);
}

describe("PortfolioFormDialog", () => {
  it("allows arbitrary 3-letter base currencies when creating a portfolio", async () => {
    const onSave = vi.fn();

    render(
      <PortfolioFormDialog
        open
        isPending={false}
        onOpenChange={() => {}}
        onSave={onSave}
      />,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Create Portfolio");
    expect(dialog).toHaveTextContent("Finance Workspace portfolio");
    expect(dialog).toHaveTextContent("3-letter code");
    expectSharedDialogShell(dialog);

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Global Growth" },
    });
    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "global_growth" },
    });
    fireEvent.change(screen.getByLabelText("Base Currency"), {
      target: { value: "aud" },
    });
    fireEvent.submit(screen.getByLabelText("Name").closest("form")!);

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        baseCurrency: "AUD",
        description: null,
        name: "Global Growth",
        slug: "global_growth",
      }),
    );
  });
});
