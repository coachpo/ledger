import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PortfolioFormDialog } from "./portfolio-form-dialog";

function expectSharedDialogShell(dialog: HTMLElement) {
  const body = dialog.querySelector('[data-slot="entity-dialog-body"]');
  const footer = dialog.querySelector('[data-slot="dialog-footer"]');

  expect(
    dialog.querySelector('[data-slot="entity-dialog-constraint-strip"]'),
  ).toBeNull();
  expect(body).toBeTruthy();
  expect(footer).toBeTruthy();
  expect(
    Array.from(
      dialog.querySelectorAll(
        '[data-slot="entity-dialog-body"], [data-slot="dialog-footer"]',
      ),
    ),
  ).toEqual([body, footer]);
}

describe("PortfolioFormDialog", () => {
  it("submits the default base currency when creating a portfolio", async () => {
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
    expect(dialog).not.toHaveTextContent("3-letter code");
    expect(screen.queryByLabelText("Base Currency")).not.toBeInTheDocument();
    expectSharedDialogShell(dialog);

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Global Growth" },
    });
    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "global_growth" },
    });
    fireEvent.submit(screen.getByLabelText("Name").closest("form")!);

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        baseCurrency: "USD",
        description: null,
        name: "Global Growth",
        slug: "global_growth",
      }),
    );
  });
});
