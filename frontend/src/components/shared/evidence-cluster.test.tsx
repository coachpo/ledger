import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceCluster } from "./evidence-cluster";

describe("EvidenceCluster", () => {
  it("renders labeled evidence with tone badges and descriptions", () => {
    render(
      <EvidenceCluster
        items={[
          { description: "Resolved from live checks.", label: "Source", tone: "verified", value: "Runtime" },
          { label: "Warning", tone: "warning", value: "Partial" },
        ]}
      />,
    );

    expect(screen.getByRole("list")).toHaveClass("grid", "gap-2", "sm:grid-cols-2");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Source").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "verified");
    expect(screen.getByText("Warning").closest("[data-slot='badge']")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("Resolved from live checks.")).toHaveClass("text-xs", "text-muted-foreground");
  });

  it("renders deterministic empty and inline layouts", () => {
    const { rerender } = render(<EvidenceCluster emptyLabel="No launch evidence" items={[]} />);

    expect(screen.getByText("No launch evidence")).toHaveClass("border-dashed", "text-muted-foreground");

    rerender(<EvidenceCluster items={[{ label: "Trace", value: "trace-1" }]} layout="inline" />);

    expect(screen.getByRole("list")).toHaveClass("flex", "flex-wrap", "items-center", "gap-2");
  });
});
