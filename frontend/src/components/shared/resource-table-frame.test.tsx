import type { ComponentType, ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";

type ResourceTableFrameProps = {
  children: ReactNode;
  className?: string;
  testId?: string;
};

async function loadResourceTableFrame() {
  const modulePath = "./resource-table-frame";
  const module = await import(modulePath);
  return module.ResourceTableFrame as ComponentType<ResourceTableFrameProps>;
}

describe("ResourceTableFrame", () => {
  it("wraps route-owned tables in a framed horizontally contained shell", async () => {
    const ResourceTableFrame = await loadResourceTableFrame();

    render(
      <ResourceTableFrame testId="resource-table-frame">
        <Table>
          <TableBody>
            <TableRow>
              <TableCell>Queued run</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </ResourceTableFrame>,
    );

    const frame = screen.getByTestId("resource-table-frame");
    expect(frame).toHaveClass("min-w-0", "max-w-full", "rounded-md", "border");
    expect(frame.querySelector("[data-slot='table-container']")).toHaveClass(
      "min-w-0",
      "w-full",
      "overflow-x-auto",
    );
    expect(screen.getByRole("table")).toBeVisible();
  });
});
