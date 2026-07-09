import { useCallback, useMemo, useRef, useState } from "react";

export type ResourceFilterMap<TKey extends string = string> = Partial<
  Record<TKey, string>
>;

type ResourceFilterPredicateState<TKey extends string = string> = {
  filters: ResourceFilterMap<TKey>;
  normalizedSearch: string;
  search: string;
};

export type UseResourceFilterStateOptions<
  TItem,
  TFilterKey extends string = string,
> = {
  filterItem?: (
    item: TItem,
    state: ResourceFilterPredicateState<TFilterKey>,
  ) => boolean;
  initialFilters?: ResourceFilterMap<TFilterKey>;
  initialSearch?: string;
  items: readonly TItem[];
  searchText?: (item: TItem) => string;
};

function normalizeSearch(value: string) {
  return value.trim().toLowerCase();
}

function removeEmptyFilters<TKey extends string>(
  filters: ResourceFilterMap<TKey>,
): ResourceFilterMap<TKey> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => String(value ?? "").trim()),
  ) as ResourceFilterMap<TKey>;
}

export function useResourceFilterState<
  TItem,
  TFilterKey extends string = string,
>({
  filterItem,
  initialFilters = {},
  initialSearch = "",
  items,
  searchText,
}: UseResourceFilterStateOptions<TItem, TFilterKey>) {
  const initialSearchRef = useRef(initialSearch);
  const initialFiltersRef = useRef(initialFilters);
  const [search, setSearch] = useState(initialSearch);
  const [filters, setFilters] = useState<ResourceFilterMap<TFilterKey>>(
    () => removeEmptyFilters(initialFilters),
  );

  const normalizedSearch = useMemo(() => normalizeSearch(search), [search]);
  const activeFilters = useMemo(() => removeEmptyFilters(filters), [filters]);

  const setFilter = useCallback((key: TFilterKey, value: string) => {
    setFilters((previous) =>
      removeEmptyFilters({ ...previous, [key]: value }),
    );
  }, []);

  const clearFilter = useCallback((key: TFilterKey) => {
    setFilters((previous) => {
      const next = { ...previous };
      delete next[key];
      return next;
    });
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(removeEmptyFilters(initialFiltersRef.current));
  }, []);

  const resetAll = useCallback(() => {
    setSearch(initialSearchRef.current);
    setFilters(removeEmptyFilters(initialFiltersRef.current));
  }, []);

  const predicateState = useMemo(
    () => ({ filters: activeFilters, normalizedSearch, search }),
    [activeFilters, normalizedSearch, search],
  );

  const filteredItems = useMemo(() => {
    if (filterItem) {
      return items.filter((item) => filterItem(item, predicateState));
    }

    if (!normalizedSearch || !searchText) {
      return items;
    }

    return items.filter((item) =>
      searchText(item).toLowerCase().includes(normalizedSearch),
    );
  }, [filterItem, items, normalizedSearch, predicateState, searchText]);

  const activeFilterCount = Object.keys(activeFilters).length;

  return {
    activeFilterCount,
    activeFilters,
    filters,
    filteredItems,
    hasActiveFilters: normalizedSearch.length > 0 || activeFilterCount > 0,
    normalizedSearch,
    search,
    clearFilter,
    resetAll,
    resetFilters,
    setFilter,
    setFilters,
    setSearch,
  };
}
