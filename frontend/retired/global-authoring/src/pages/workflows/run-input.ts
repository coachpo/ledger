import { buildRunInputDefaultValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { encodeValueEntry, validateAndDecodeValueEntry } from "@/lib/platform-authoring/values/codec";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";
import type { UnknownRecord } from "@/lib/types/common";

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function createDefaultRunInputValue(schema: SchemaIRNode): ValueEntry {
  const defaultValue = buildRunInputDefaultValue(schema);

  if (isRecord(defaultValue) && typeof defaultValue.ticker === "string") {
    return encodeValueEntry({ ...defaultValue, ticker: "AAPL" });
  }

  if (isRecord(defaultValue)) {
    return encodeValueEntry(defaultValue);
  }

  return encodeValueEntry({});
}
export function decodeRunInputValue(value: ValueEntry): UnknownRecord {
  const decoded = validateAndDecodeValueEntry(value);

  if (!decoded.ok || !isRecord(decoded.value)) {
    return {};
  }

  return decoded.value;
}
