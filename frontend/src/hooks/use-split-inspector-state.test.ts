import { createElement as h } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useSplitInspectorState } from "./use-split-inspector-state";

type InspectorTab = "details" | "events";

function InspectorStateHarness({
  initialOpen,
  initialSelection = null,
  resetTabOnSelectionChange = true,
}: {
  initialOpen?: boolean;
  initialSelection?: string | null;
  resetTabOnSelectionChange?: boolean;
}) {
  const inspector = useSplitInspectorState<string, InspectorTab>({
    initialOpen,
    initialSelection,
    initialTab: "details",
    resetTabOnSelectionChange,
  });

  return h(
    "div",
    null,
    h("output", { "aria-label": "selected" }, inspector.selected ?? "none"),
    h("output", { "aria-label": "open" }, String(inspector.isInspectorOpen)),
    h("output", { "aria-label": "tab" }, inspector.activeTab),
    h("button", { onClick: () => inspector.select("alpha"), type: "button" }, "Select alpha"),
    h("button", { onClick: () => inspector.select("beta", { tab: "events" }), type: "button" }, "Select beta events"),
    h("button", { onClick: () => inspector.setActiveTab("events"), type: "button" }, "Show events"),
    h("button", { onClick: inspector.closeInspector, type: "button" }, "Close"),
    h("button", { onClick: inspector.openInspector, type: "button" }, "Open"),
    h("button", { onClick: inspector.clearSelection, type: "button" }, "Clear"),
    h("button", { onClick: inspector.resetInspector, type: "button" }, "Reset"),
  );
}

function renderHarness(props: Parameters<typeof InspectorStateHarness>[0] = {}) {
  return render(h(InspectorStateHarness, props));
}

function expectState({
  open,
  selected,
  tab,
}: {
  open: string;
  selected: string;
  tab: InspectorTab;
}) {
  expect(screen.getByLabelText("selected")).toHaveTextContent(selected);
  expect(screen.getByLabelText("open")).toHaveTextContent(open);
  expect(screen.getByLabelText("tab")).toHaveTextContent(tab);
}

describe("useSplitInspectorState", () => {
  it("opens selected items, switches tabs, and closes without clearing selection", () => {
    renderHarness();

    expectState({ open: "false", selected: "none", tab: "details" });
    fireEvent.click(screen.getByRole("button", { name: "Select alpha" }));
    expectState({ open: "true", selected: "alpha", tab: "details" });

    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    expectState({ open: "true", selected: "alpha", tab: "events" });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expectState({ open: "false", selected: "alpha", tab: "events" });

    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expectState({ open: "true", selected: "alpha", tab: "events" });
  });

  it("clears selection, closes the inspector, and resets the tab", () => {
    renderHarness();

    fireEvent.click(screen.getByRole("button", { name: "Select beta events" }));
    expectState({ open: "true", selected: "beta", tab: "events" });

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    expectState({ open: "false", selected: "none", tab: "details" });
  });

  it("resets tabs on selection changes unless a selection supplies a tab", () => {
    renderHarness();

    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    expectState({ open: "false", selected: "none", tab: "events" });

    fireEvent.click(screen.getByRole("button", { name: "Select alpha" }));
    expectState({ open: "true", selected: "alpha", tab: "details" });

    fireEvent.click(screen.getByRole("button", { name: "Select beta events" }));
    expectState({ open: "true", selected: "beta", tab: "events" });
  });

  it("can preserve an active tab across selection changes", () => {
    renderHarness({ resetTabOnSelectionChange: false });

    fireEvent.click(screen.getByRole("button", { name: "Show events" }));
    fireEvent.click(screen.getByRole("button", { name: "Select alpha" }));

    expectState({ open: "true", selected: "alpha", tab: "events" });
  });

  it("resets to the configured initial selection and open state", () => {
    renderHarness({ initialOpen: true, initialSelection: "seed" });

    expectState({ open: "true", selected: "seed", tab: "details" });
    fireEvent.click(screen.getByRole("button", { name: "Select beta events" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expectState({ open: "false", selected: "none", tab: "details" });

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    expectState({ open: "true", selected: "seed", tab: "details" });
  });
});
