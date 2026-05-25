import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useResourceSelectionState } from "./use-resource-selection-state";

type Resource = {
  id: string;
  name: string;
};

const resources: Resource[] = [
  { id: "alpha", name: "Alpha" },
  { id: "beta", name: "Beta" },
  { id: "gamma", name: "Gamma" },
];

describe("useResourceSelectionState", () => {
  it("toggles selected ids, item batches, and reset state", () => {
    const { result } = renderHook(() =>
      useResourceSelectionState({
        getId: (resource: Resource) => resource.id,
        initialSelectedIds: ["beta"],
        items: resources,
      }),
    );

    expect(result.current.selectedItems.map((item) => item.id)).toEqual([
      "beta",
    ]);
    expect(result.current.someSelected).toBe(true);
    expect(result.current.allSelected).toBe(false);

    act(() => result.current.toggleSelected("alpha"));
    expect([...result.current.selectedIds].sort()).toEqual(["alpha", "beta"]);

    act(() => result.current.setItemsSelected([resources[1]], false));
    expect([...result.current.selectedIds]).toEqual(["alpha"]);

    act(() => result.current.selectAll());
    expect(result.current.allSelected).toBe(true);
    expect(result.current.selectedCount).toBe(3);

    act(() => result.current.clearSelection());
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.someSelected).toBe(false);

    act(() => result.current.resetSelection());
    expect([...result.current.selectedIds]).toEqual(["beta"]);
  });

  it("derives selected counts from the caller-supplied visible items", () => {
    const { rerender, result } = renderHook(
      ({ items }: { items: Resource[] }) =>
        useResourceSelectionState({
          getId: (resource: Resource) => resource.id,
          initialSelectedIds: ["alpha", "gamma"],
          items,
        }),
      { initialProps: { items: resources } },
    );

    expect(result.current.selectedCount).toBe(2);
    expect(result.current.someSelected).toBe(true);
    expect(result.current.allSelected).toBe(false);

    rerender({ items: [resources[0]] });

    expect(result.current.selectedCount).toBe(1);
    expect(result.current.allSelected).toBe(true);
    expect([...result.current.selectedIds].sort()).toEqual(["alpha", "gamma"]);

    act(() => result.current.setIdsSelected(["alpha"], false));
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.isSelected("gamma")).toBe(true);
  });
});
