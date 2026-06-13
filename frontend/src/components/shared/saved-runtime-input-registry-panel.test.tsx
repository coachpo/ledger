import type { ComponentType } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

type SavedRuntimeInputRegistryEntry = {
  id: number;
  label: string;
  mode: "history" | "preset";
  sourceLabel: string;
  stale: boolean;
  staleReasonLines: string[];
};

type SavedRuntimeInputRegistryPanelProps = {
  capMessage: string;
  createDisabled: boolean;
  createPending: boolean;
  error: Error | null;
  errorTitle: string;
  helperCopy: string;
  historyEmptyMessage: string;
  historyEntries: readonly SavedRuntimeInputRegistryEntry[];
  loading: boolean;
  loadingMessage: string;
  presetEntries: readonly SavedRuntimeInputRegistryEntry[];
  presetEmptyMessage: string;
  presetNameLabel: string;
  presetNamePlaceholder: string;
  presetNameValue: string;
  presetLimit: number;
  saveLabel: string;
  staleNoticeTitle: string;
  title: string;
  workflowBadgeFallback: string;
  workflowKey: string;
  onCreate: () => void;
  onDelete: (entry: SavedRuntimeInputRegistryEntry) => void;
  onLoad: (entry: SavedRuntimeInputRegistryEntry) => void;
  onOverwrite: (entry: SavedRuntimeInputRegistryEntry) => void;
  onPresetNameChange: (value: string) => void;
};

async function loadSavedRuntimeInputRegistryPanel() {
  const modulePath = "./saved-runtime-input-registry-panel";
  const module = await import(modulePath);
  return module.SavedRuntimeInputRegistryPanel as ComponentType<SavedRuntimeInputRegistryPanelProps>;
}

function entry(
  overrides: Partial<SavedRuntimeInputRegistryEntry> &
    Pick<SavedRuntimeInputRegistryEntry, "id" | "label" | "mode">,
): SavedRuntimeInputRegistryEntry {
  const { id, label, mode, ...rest } = overrides;

  return {
    id,
    label,
    mode,
    sourceLabel:
      mode === "history"
        ? "Captured 2026-05-08 11:00 UTC"
        : "Updated 2026-05-08 09:00 UTC",
    stale: false,
    staleReasonLines: [],
    ...rest,
  };
}

function createProps(overrides: Partial<SavedRuntimeInputRegistryPanelProps> = {}): SavedRuntimeInputRegistryPanelProps {
  return {
    capMessage: "Saved runtime input presets are capped at 20 per workflow. Delete one before saving another.",
    createDisabled: false,
    createPending: false,
    error: null,
    errorTitle: "Saved inputs unavailable",
    helperCopy: "Choose a workflow to load saved runtime input presets or launch history.",
    historyEmptyMessage: "No launch history yet.",
    historyEntries: [],
    loading: false,
    loadingMessage: "Loading saved inputs for this workflow...",
    presetEntries: [],
    presetEmptyMessage: "No saved runtime input presets for this workflow.",
    presetNameLabel: "Saved runtime input preset name",
    presetNamePlaceholder: "Preset name",
    presetNameValue: "",
    presetLimit: 20,
    saveLabel: "Save current JSON",
    staleNoticeTitle: "Saved against older workflow metadata.",
    title: "Saved inputs",
    workflowBadgeFallback: "workflow pending",
    workflowKey: "",
    onCreate: vi.fn(),
    onDelete: vi.fn(),
    onLoad: vi.fn(),
    onOverwrite: vi.fn(),
    onPresetNameChange: vi.fn(),
    ...overrides,
  };
}

describe("SavedRuntimeInputRegistryPanel", () => {
  it("supports workflow badge fallback, route-specific copy, tabs, and count badges before a workflow is selected", async () => {
    const SavedRuntimeInputRegistryPanel = await loadSavedRuntimeInputRegistryPanel();

    render(<SavedRuntimeInputRegistryPanel {...createProps()} />);

    expect(screen.getByText("Saved inputs")).toBeVisible();
    expect(screen.getByText("workflow pending")).toBeVisible();
    expect(screen.getByText("Choose a workflow to load saved runtime input presets or launch history.")).toBeVisible();
    expect(screen.getByRole("tab", { name: /presets/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /history/i })).toBeVisible();
    expect(screen.getAllByText("0/20")).toHaveLength(2);
    expect(screen.queryByText("No saved runtime input presets for this workflow.")).not.toBeInTheDocument();
    expect(screen.queryByText("No launch history yet.")).not.toBeInTheDocument();
  });

  it("renders helper loading, error, and empty states with a workflow badge and schedule-specific copy", async () => {
    const SavedRuntimeInputRegistryPanel = await loadSavedRuntimeInputRegistryPanel();

    render(
      <SavedRuntimeInputRegistryPanel
        {...createProps({
          error: new Error("Saved inputs failed"),
          errorTitle: "Saved scheduled inputs unavailable",
          helperCopy: "Load saved runtime input presets or reuse previous run inputs as a starting point for this task.",
          loading: true,
          loadingMessage: "Loading saved inputs for daily_research...",
          title: "Schedule input presets",
          workflowKey: "daily_research",
        })}
      />,
    );

    expect(screen.getByText("Schedule input presets")).toBeVisible();
    expect(screen.getByText("daily_research")).toBeVisible();
    expect(screen.getByText("Load saved runtime input presets or reuse previous run inputs as a starting point for this task.")).toBeVisible();
    expect(screen.getByText("Loading saved inputs for daily_research...")).toBeVisible();
    expect(screen.getByText("Saved scheduled inputs unavailable")).toBeVisible();
    expect(screen.getByText("Saved inputs failed")).toBeVisible();
    expect(screen.getByText("No saved runtime input presets for this workflow.")).toBeVisible();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /history/i }), { button: 0 });
    expect(screen.getByText("No launch history yet.")).toBeVisible();
  });

  it("shows stale notices plus preset-only overwrite and delete actions while history stays load-only", async () => {
    const SavedRuntimeInputRegistryPanel = await loadSavedRuntimeInputRegistryPanel();
    const preset = entry({
      id: 7,
      label: "Morning preset",
      mode: "preset",
      stale: true,
      staleReasonLines: ["manifestHash: Manifest changed"],
    });
    const history = entry({
      id: 11,
      label: "Run #99",
      mode: "history",
      sourceLabel: "Captured 2026-05-08 11:00 UTC",
    });
    const onDelete = vi.fn();
    const onLoad = vi.fn();
    const onOverwrite = vi.fn();

    render(
      <SavedRuntimeInputRegistryPanel
        {...createProps({
          historyEntries: [history],
          onDelete,
          onLoad,
          onOverwrite,
          presetEntries: [preset],
          workflowKey: "market_review",
        })}
      />,
    );

    const presetRow = screen.getByTestId("saved-runtime-input-preset-7");
    expect(within(presetRow).getByText("Stale")).toBeVisible();
    expect(within(presetRow).getByText("Saved against older workflow metadata.")).toBeVisible();
    expect(within(presetRow).getByText("manifestHash: Manifest changed")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Load saved runtime input preset Morning preset" }));
    fireEvent.click(screen.getByRole("button", { name: "Overwrite saved runtime input preset Morning preset" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete saved runtime input preset Morning preset" }));
    expect(onLoad).toHaveBeenCalledWith(preset);
    expect(onOverwrite).toHaveBeenCalledWith(preset);
    expect(onDelete).toHaveBeenCalledWith(preset);

    fireEvent.mouseDown(screen.getByRole("tab", { name: /history/i }), { button: 0 });
    const historyRow = screen.getByTestId("saved-runtime-input-history-11");
    expect(within(historyRow).getByRole("button", { name: "Load history input Run #99" })).toBeVisible();
    expect(within(historyRow).queryByRole("button", { name: /overwrite/i })).not.toBeInTheDocument();
    expect(within(historyRow).queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });
});
