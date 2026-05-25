import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConsoleSection } from "./console-section";

describe("ConsoleSection", () => {
  it("renders heading, description, children, and isolated actions", () => {
    const onInspect = vi.fn();

    render(
      <ConsoleSection
        actions={<button onClick={onInspect} type="button">Inspect</button>}
        description="Evidence and controls stay grouped."
        title="Preflight"
      >
        <p>Runtime payload</p>
      </ConsoleSection>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));

    expect(screen.getByText("Preflight")).toBeInTheDocument();
    expect(screen.getByText("Evidence and controls stay grouped.")).toHaveClass("text-xs");
    expect(screen.getByText("Runtime payload")).toBeInTheDocument();
    expect(onInspect).toHaveBeenCalledTimes(1);
  });

  it("applies tone and density classes deterministically", () => {
    render(
      <ConsoleSection density="comfortable" title="Warnings" tone="warning">
        <p>Check constraints</p>
      </ConsoleSection>,
    );

    expect(screen.getByText("Warnings").closest("[data-slot='card']")).toHaveAttribute("data-tone", "warning");
    expect(screen.getByText("Warnings").closest("[data-slot='card-header']")).toHaveClass("px-6", "pt-6");
    expect(screen.getByText("Check constraints").closest("[data-slot='card-content']")).toHaveClass("px-6", "pb-6");
  });
});
