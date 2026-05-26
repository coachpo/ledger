import { useCallback, useRef, useState } from "react";

export type InventoryViewMode = "cards" | "table";

export type UseInventoryViewStateOptions = {
  initialViewMode?: InventoryViewMode;
  onCardsMode: () => void;
};

function isInventoryViewMode(value: string): value is InventoryViewMode {
  return value === "cards" || value === "table";
}

export function useInventoryViewState({
  initialViewMode = "cards",
  onCardsMode,
}: UseInventoryViewStateOptions) {
  const viewModeRef = useRef<InventoryViewMode>(initialViewMode);
  const [viewMode, setViewModeState] =
    useState<InventoryViewMode>(initialViewMode);

  const setViewMode = useCallback(
    (nextViewMode: InventoryViewMode) => {
      const previousViewMode = viewModeRef.current;

      if (previousViewMode === nextViewMode) {
        return;
      }

      viewModeRef.current = nextViewMode;
      setViewModeState(nextViewMode);

      if (previousViewMode === "table" && nextViewMode === "cards") {
        onCardsMode();
      }
    },
    [onCardsMode],
  );

  const onViewModeChange = useCallback(
    (value: string) => {
      if (isInventoryViewMode(value)) {
        setViewMode(value);
      }
    },
    [setViewMode],
  );

  return {
    viewMode,
    onViewModeChange,
    setViewMode,
  };
}
