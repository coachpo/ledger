import { useCallback, useState } from "react";

export type SplitInspectorSelection = string | number;

export type UseSplitInspectorStateOptions<
  TSelection extends SplitInspectorSelection,
  TTab extends string,
> = {
  initialOpen?: boolean;
  initialSelection?: TSelection | null;
  initialTab: TTab;
  resetTabOnSelectionChange?: boolean;
};

export type SelectSplitInspectorOptions<TTab extends string> = {
  open?: boolean;
  tab?: TTab;
};

export type UseSplitInspectorStateResult<
  TSelection extends SplitInspectorSelection,
  TTab extends string,
> = {
  activeTab: TTab;
  clearSelection: () => void;
  closeInspector: () => void;
  isInspectorOpen: boolean;
  openInspector: () => void;
  resetInspector: () => void;
  select: (selection: TSelection, options?: SelectSplitInspectorOptions<TTab>) => void;
  selected: TSelection | null;
  setActiveTab: (tab: TTab) => void;
};

export function useSplitInspectorState<
  TSelection extends SplitInspectorSelection = string,
  TTab extends string = string,
>({
  initialOpen,
  initialSelection = null,
  initialTab,
  resetTabOnSelectionChange = true,
}: UseSplitInspectorStateOptions<TSelection, TTab>): UseSplitInspectorStateResult<TSelection, TTab> {
  const resolvedInitialOpen = initialOpen ?? initialSelection !== null;
  const [selected, setSelected] = useState<TSelection | null>(initialSelection);
  const [activeTab, setActiveTab] = useState<TTab>(initialTab);
  const [isInspectorOpen, setInspectorOpen] = useState(resolvedInitialOpen);

  const select = useCallback(
    (selection: TSelection, options?: SelectSplitInspectorOptions<TTab>) => {
      setSelected(selection);
      setInspectorOpen(options?.open ?? true);
      if (options?.tab) {
        setActiveTab(options.tab);
        return;
      }
      if (resetTabOnSelectionChange) {
        setActiveTab(initialTab);
      }
    },
    [initialTab, resetTabOnSelectionChange],
  );

  const clearSelection = useCallback(() => {
    setSelected(null);
    setInspectorOpen(false);
    setActiveTab(initialTab);
  }, [initialTab]);

  const closeInspector = useCallback(() => {
    setInspectorOpen(false);
  }, []);

  const openInspector = useCallback(() => {
    setInspectorOpen(true);
  }, []);

  const resetInspector = useCallback(() => {
    setSelected(initialSelection);
    setInspectorOpen(resolvedInitialOpen);
    setActiveTab(initialTab);
  }, [initialSelection, initialTab, resolvedInitialOpen]);

  return {
    activeTab,
    clearSelection,
    closeInspector,
    isInspectorOpen,
    openInspector,
    resetInspector,
    select,
    selected,
    setActiveTab,
  };
}
