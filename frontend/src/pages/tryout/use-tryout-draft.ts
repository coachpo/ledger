import { useState } from "react";

import type { TryoutDraft } from "./shared";
import { buildNewTryoutInputRow, initialDraft } from "./shared";

export function useTryoutDraftState(onChange?: () => void) {
  const [draft, setDraft] = useState<TryoutDraft>(initialDraft);

  const notifyChange = () => {
    onChange?.();
  };

  const updateDraft = <Key extends keyof TryoutDraft>(key: Key, value: TryoutDraft[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    notifyChange();
  };

  const togglePersonaProfile = (personaKey: string) => {
    setDraft((current) => ({
      ...current,
      personaProfileKeys: current.personaProfileKeys.includes(personaKey)
        ? current.personaProfileKeys.filter((entry) => entry !== personaKey)
        : [...current.personaProfileKeys, personaKey],
    }));
    notifyChange();
  };

  const addRuntimeInputRow = () => {
    setDraft((current) => ({
      ...current,
      runtimeInputsOpen: true,
      runtimeInputRows: [...current.runtimeInputRows, buildNewTryoutInputRow()],
    }));
    notifyChange();
  };

  const updateRuntimeInputRow = (rowId: string, field: "key" | "value", value: string) => {
    setDraft((current) => ({
      ...current,
      runtimeInputRows: current.runtimeInputRows.map((row) =>
        row.id === rowId ? { ...row, [field]: value } : row,
      ),
    }));
    notifyChange();
  };

  const removeRuntimeInputRow = (rowId: string) => {
    setDraft((current) => ({
      ...current,
      runtimeInputRows: current.runtimeInputRows.filter((row) => row.id !== rowId),
    }));
    notifyChange();
  };

  return {
    addRuntimeInputRow,
    draft,
    removeRuntimeInputRow,
    setDraft,
    togglePersonaProfile,
    updateDraft,
    updateRuntimeInputRow,
  };
}
