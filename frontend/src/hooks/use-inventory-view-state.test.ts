import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useInventoryViewState } from "./use-inventory-view-state";

describe("useInventoryViewState", () => {
  it("calls onCardsMode exactly when switching from table to cards", () => {
    const onCardsMode = vi.fn();
    const { result } = renderHook(() =>
      useInventoryViewState({ initialViewMode: "table", onCardsMode }),
    );

    expect(result.current.viewMode).toBe("table");

    act(() => result.current.onViewModeChange("cards"));
    expect(result.current.viewMode).toBe("cards");
    expect(onCardsMode).toHaveBeenCalledTimes(1);

    act(() => result.current.onViewModeChange("cards"));
    expect(onCardsMode).toHaveBeenCalledTimes(1);

    act(() => result.current.onViewModeChange("table"));
    expect(result.current.viewMode).toBe("table");
    expect(onCardsMode).toHaveBeenCalledTimes(1);

    act(() => result.current.setViewMode("cards"));
    expect(result.current.viewMode).toBe("cards");
    expect(onCardsMode).toHaveBeenCalledTimes(2);
  });

  it("ignores non-inventory view values from generic toolbar callbacks", () => {
    const onCardsMode = vi.fn();
    const { result } = renderHook(() =>
      useInventoryViewState({ initialViewMode: "cards", onCardsMode }),
    );

    act(() => result.current.onViewModeChange("timeline"));

    expect(result.current.viewMode).toBe("cards");
    expect(onCardsMode).not.toHaveBeenCalled();
  });
});
