import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PortfolioFormDialog } from "./portfolio-form-dialog";

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

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Global Growth" },
    });
    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "global_growth" },
    });
    fireEvent.change(screen.getByLabelText("Base Currency"), {
      target: { value: "aud" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);

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
