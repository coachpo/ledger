import { useCallback, useMemo, useRef, useState } from "react";

export type ResourceSelectionId = number | string;

export type UseResourceSelectionStateOptions<
  TItem,
  TId extends ResourceSelectionId,
> = {
  getId: (item: TItem) => TId;
  initialSelectedIds?: readonly TId[];
  items: readonly TItem[];
};

function createIdSet<TId extends ResourceSelectionId>(ids: readonly TId[]) {
  return new Set<TId>(ids);
}

export function useResourceSelectionState<
  TItem,
  TId extends ResourceSelectionId,
>({
  getId,
  initialSelectedIds = [],
  items,
}: UseResourceSelectionStateOptions<TItem, TId>) {
  const initialSelectedIdsRef = useRef(initialSelectedIds);
  const [selectedIds, setSelectedIds] = useState<Set<TId>>(() =>
    createIdSet(initialSelectedIds),
  );

  const itemIds = useMemo(() => items.map(getId), [getId, items]);

  const selectedItems = useMemo(
    () => items.filter((item) => selectedIds.has(getId(item))),
    [getId, items, selectedIds],
  );

  const setIdsSelected = useCallback(
    (ids: readonly TId[], selected: boolean) => {
      setSelectedIds((previous) => {
        const next = new Set(previous);
        ids.forEach((id) => {
          if (selected) {
            next.add(id);
          } else {
            next.delete(id);
          }
        });
        return next;
      });
    },
    [],
  );

  const setItemsSelected = useCallback(
    (itemsToUpdate: readonly TItem[], selected: boolean) => {
      setIdsSelected(itemsToUpdate.map(getId), selected);
    },
    [getId, setIdsSelected],
  );

  const toggleSelected = useCallback((id: TId, selected?: boolean) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      const shouldSelect = selected ?? !next.has(id);
      if (shouldSelect) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const resetSelection = useCallback(() => {
    setSelectedIds(createIdSet(initialSelectedIdsRef.current));
  }, []);

  const selectAll = useCallback(() => {
    setIdsSelected(itemIds, true);
  }, [itemIds, setIdsSelected]);

  const allSelected =
    itemIds.length > 0 && itemIds.every((id) => selectedIds.has(id));
  const someSelected = itemIds.some((id) => selectedIds.has(id));

  return {
    allSelected,
    selectedCount: selectedItems.length,
    selectedIds,
    selectedItems,
    someSelected,
    clearSelection,
    isSelected: (id: TId) => selectedIds.has(id),
    resetSelection,
    selectAll,
    setIdsSelected,
    setItemsSelected,
    setSelectedIds,
    toggleSelected,
  };
}
