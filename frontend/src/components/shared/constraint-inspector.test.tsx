import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConstraintInspector } from "./constraint-inspector";

describe("ConstraintInspector", () => {
  it("renders blocking, warning, and requirement states deterministically", () => {
    render(
      <ConstraintInspector
        blocking={["Missing model connection"]}
        requirements={["At least one runnable workflow"]}
        summary="Preflight found launch constraints."
        title="Launch readiness"
        warnings={["Optional report tool unavailable"]}
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("data-state", "blocked");
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Blocking constraints")).getByText("Missing model connection")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Warnings")).getByText("Optional report tool unavailable")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Requirements")).getByText("At least one runnable workflow")).toBeInTheDocument();
  });

  it("renders ready state and empty buckets without route-specific copy", () => {
    render(<ConstraintInspector blocking={[]} title="Ready checks" />);

    expect(screen.getByRole("alert")).toHaveAttribute("data-state", "ready");
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("No blocking constraints.")).toBeInTheDocument();
    expect(screen.getByText("No warnings.")).toBeInTheDocument();
    expect(screen.getByText("No requirements.")).toBeInTheDocument();
  });
});
