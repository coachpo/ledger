import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useResourceFilterState } from "./use-resource-filter-state";

type Resource = {
  kind: "package" | "report";
  name: string;
  owner: "finance" | "platform";
};

const resources: Resource[] = [
  { kind: "package", name: "Alpha Workflow", owner: "platform" },
  { kind: "report", name: "Finance Summary", owner: "finance" },
  { kind: "package", name: "Beta Workflow", owner: "finance" },
];

describe("useResourceFilterState", () => {
  it("filters caller-supplied items with normalized search text", () => {
    const { result } = renderHook(() =>
      useResourceFilterState({
        items: resources,
        searchText: (resource) => `${resource.name} ${resource.kind}`,
      }),
    );

    expect(result.current.filteredItems).toHaveLength(3);

    act(() => result.current.setSearch("  WORKFLOW "));

    expect(result.current.normalizedSearch).toBe("workflow");
    expect(result.current.filteredItems.map((item) => item.name)).toEqual([
      "Alpha Workflow",
      "Beta Workflow",
    ]);
    expect(result.current.hasActiveFilters).toBe(true);
  });

  it("lets callers combine search and arbitrary filter predicates", () => {
    const { result } = renderHook(() =>
      useResourceFilterState<Resource, "owner">({
        filterItem: (resource, state) => {
          const owner = state.filters.owner;
          const matchesOwner = owner ? resource.owner === owner : true;
          const matchesSearch = state.normalizedSearch
            ? resource.name.toLowerCase().includes(state.normalizedSearch)
            : true;
          return matchesOwner && matchesSearch;
        },
        initialFilters: { owner: "finance" },
        initialSearch: "summary",
        items: resources,
      }),
    );

    expect(result.current.filteredItems.map((item) => item.name)).toEqual([
      "Finance Summary",
    ]);
    expect(result.current.activeFilterCount).toBe(1);

    act(() => result.current.setFilter("owner", "platform"));
    expect(result.current.filteredItems).toEqual([]);

    act(() => result.current.clearFilter("owner"));
    expect(result.current.filteredItems.map((item) => item.name)).toEqual([
      "Finance Summary",
    ]);

    act(() => result.current.resetAll());
    expect(result.current.search).toBe("summary");
    expect(result.current.activeFilters).toEqual({ owner: "finance" });
  });
});
