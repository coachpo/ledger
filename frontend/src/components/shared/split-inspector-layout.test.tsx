import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SheetInspectorLayout, SplitInspectorLayout } from "./split-inspector-layout";

type InspectorTab = "summary" | "activity";

function TabbedInspectorFixture() {
  const [activeTab, setActiveTab] = useState<InspectorTab>("summary");
  const onClose = vi.fn();

  return (
    <SplitInspectorLayout<InspectorTab>
      activeTab={activeTab}
      emptyInspector={<p>No item selected</p>}
      inspectorActions={<button onClick={onClose} type="button">Close inspector</button>}
      inspectorTitle="Reusable inspector"
      leftPane={<div>Source list</div>}
      onActiveTabChange={setActiveTab}
      tabs={[
        { content: <p>Summary payload</p>, label: "Summary", value: "summary" },
        { content: <p>Activity payload</p>, label: "Activity", value: "activity" },
      ]}
    />
  );
}

describe("SplitInspectorLayout", () => {
  it("renders source and inspector panes with controlled tabs", () => {
    render(<TabbedInspectorFixture />);

    const layout = screen.getByTestId("split-inspector-layout");
    expect(layout).toHaveAttribute("data-inspector-state", "open");
    expect(screen.getByTestId("split-inspector-resize-handle")).toBeInTheDocument();
    expect(screen.getByLabelText("Inspector source panel")).toHaveTextContent("Source list");
    expect(screen.getByLabelText("Inspector panel")).toHaveTextContent("Reusable inspector");

    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("data-state", "active");
    expect(screen.getByText("Summary payload")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Activity" }), { button: 0 });

    expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute("data-state", "active");
    expect(screen.getByText("Activity payload")).toBeInTheDocument();
    expect(screen.queryByText("Summary payload")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close inspector" }));
  });

  it("renders caller-provided empty inspector content when closed", () => {
    render(
      <SplitInspectorLayout
        emptyInspector={<p>Select a row before inspection</p>}
        inspectorOpen={false}
        leftPane={<div>Rows</div>}
        rightPane={<p>Selected detail</p>}
      />,
    );

    expect(screen.getByTestId("split-inspector-layout")).toHaveAttribute("data-inspector-state", "closed");
    const rightPane = screen.getByTestId("split-inspector-right-pane");
    expect(within(rightPane).getByTestId("split-inspector-empty")).toHaveTextContent("Select a row before inspection");
    expect(within(rightPane).queryByText("Selected detail")).not.toBeInTheDocument();
  });

  it("renders plain right-pane content without requiring tabs", () => {
    render(
      <SplitInspectorLayout
        emptyInspector={<p>No selection</p>}
        inspectorTitle="Inspector shell"
        leftPane={<div>Inventory</div>}
        rightPane={<p>Generic inspector body</p>}
      />,
    );

    expect(screen.getByText("Inspector shell")).toBeInTheDocument();
    expect(screen.getByText("Generic inspector body")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("applies panel sizing and vertical direction without route knowledge", () => {
    render(
      <SplitInspectorLayout
        direction="vertical"
        emptyInspector={<p>Empty</p>}
        inspectorOpen={false}
        leftPane={<div>Top panel</div>}
        leftPanel={{ defaultSize: 40, minSize: 25 }}
        rightPanel={{ defaultSize: 60, minSize: 30 }}
        testId="vertical-inspector"
      />,
    );

    const layout = screen.getByTestId("vertical-inspector");
    expect(layout).toHaveAttribute("data-panel-group-direction", "vertical");
    expect(layout).toHaveClass("min-w-0", "overflow-hidden", "rounded-xl");
  });

  it("renders the inspector in a sheet without mounting an inline right pane", () => {
    render(
      <SheetInspectorLayout
        emptyInspector={<p>No selection</p>}
        inspectorOpen
        inspectorTitle="Sheet inspector"
        leftPane={<div>Mobile source list</div>}
        rightPane={<p>Sheet inspector payload</p>}
        testId="mobile-inspector"
      />,
    );

    expect(screen.getByTestId("mobile-inspector")).toHaveAttribute(
      "data-inspector-mode",
      "sheet",
    );
    expect(screen.getByTestId("split-inspector-left-pane")).toHaveTextContent(
      "Mobile source list",
    );
    expect(screen.queryByTestId("split-inspector-right-pane")).not.toBeInTheDocument();
    expect(screen.queryByTestId("split-inspector-resize-handle")).not.toBeInTheDocument();
    expect(screen.getByTestId("split-inspector-sheet-body")).toHaveTextContent(
      "Sheet inspector payload",
    );
  });
});
