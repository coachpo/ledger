import type { TemplateRuntimeInputs } from "@/lib/types/text-template";

export type RuntimeInputRow = {
  id: string;
  key: string;
  value: string;
};

const runtimeInputCounters = new Map<string, number>();

function nextRuntimeInputId(prefix: string): string {
  const nextValue = (runtimeInputCounters.get(prefix) ?? 0) + 1;
  runtimeInputCounters.set(prefix, nextValue);
  return `${prefix}-runtime-input-${nextValue}`;
}

export function createRuntimeInputRow(
  prefix: string,
  key = "",
  value = "",
): RuntimeInputRow {
  return {
    id: nextRuntimeInputId(prefix),
    key,
    value,
  };
}

export function createRuntimeInputRows(
  prefix: string,
  inputs?: TemplateRuntimeInputs,
): RuntimeInputRow[] {
  return Object.entries(inputs ?? {}).map(([key, value]) =>
    createRuntimeInputRow(prefix, key, value),
  );
}

export function buildRuntimeInputs(rows: RuntimeInputRow[]): TemplateRuntimeInputs {
  const result: TemplateRuntimeInputs = {};

  for (const row of rows) {
    const key = row.key.trim();
    const value = row.value.trim();
    if (!key || !value) {
      continue;
    }
    result[key] = value;
  }

  return result;
}
