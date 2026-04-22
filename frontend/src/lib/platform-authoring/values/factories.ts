import type { JsonPrimitive } from "../schema/types";
import type {
  ValueEntry,
  ValueEntryArray,
  ValueEntryArrayItem,
  ValueEntryBoolean,
  ValueEntryComposite,
  ValueEntryInteger,
  ValueEntryKind,
  ValueEntryNull,
  ValueEntryObject,
  ValueEntryObjectField,
  ValueEntryNumber,
  ValueEntryPath,
  ValueEntryScalar,
  ValueEntryString,
} from "./types";

const DEFAULT_VALUE_ENTRY_PATH: ValueEntryPath = [];

export function createValueEntryPath(pathTokens: readonly string[] = []): ValueEntryPath {
  return [...pathTokens];
}

export function createEmptyValueEntryPath(): ValueEntryPath {
  return [];
}

export function createDefaultValueEntry(kind: ValueEntryKind = "string"): ValueEntry {
  switch (kind) {
    case "null":
      return createNullValueEntry();
    case "boolean":
      return createBooleanValueEntry(false);
    case "integer":
      return createIntegerValueEntry(0);
    case "number":
      return createNumberValueEntry(0);
    case "array":
      return createArrayValueEntry([]);
    case "object":
      return createObjectValueEntry([]);
    case "string":
    default:
      return createStringValueEntry("");
  }
}

export function createValueEntryFromPrimitive(value: JsonPrimitive): ValueEntryScalar {
  if (value === null) {
    return createNullValueEntry();
  }

  switch (typeof value) {
    case "boolean":
      return createBooleanValueEntry(value);
    case "number":
      return Number.isInteger(value) ? createIntegerValueEntry(value) : createNumberValueEntry(value);
    case "string":
      return createStringValueEntry(value);
  }
}

export function createNullValueEntry(pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryNull {
  return { kind: "null", pathTokens: createValueEntryPath(pathTokens), value: null } satisfies ValueEntryNull;
}

export function createBooleanValueEntry(
  value = false,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryBoolean {
  return { kind: "boolean", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryBoolean;
}

export function createIntegerValueEntry(
  value = 0,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryInteger {
  return { kind: "integer", pathTokens: createValueEntryPath(pathTokens), value: Math.trunc(value) } satisfies ValueEntryInteger;
}

export function createNumberValueEntry(
  value = 0,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryNumber {
  return { kind: "number", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryNumber;
}

export function createStringValueEntry(
  value = "",
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryString {
  return { kind: "string", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryString;
}

export function createArrayValueEntry(items: ValueEntryArrayItem[] = [], pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryArray {
  return { kind: "array", pathTokens: createValueEntryPath(pathTokens), items } satisfies ValueEntryArray;
}

export function createObjectValueEntry(fields: ValueEntryObjectField[] = [], pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryObject {
  return { kind: "object", pathTokens: createValueEntryPath(pathTokens), fields } satisfies ValueEntryObject;
}

export function createValueEntryArrayItem(
  index: number,
  value: ValueEntry = createDefaultValueEntry("string"),
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryArrayItem {
  return { index, pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryArrayItem;
}

export function createValueEntryObjectField(
  key: string,
  value: ValueEntry = createDefaultValueEntry("string"),
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryObjectField {
  return { key, pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryObjectField;
}

export function createEmptyValueEntryComposite(kind: ValueEntryComposite["kind"]): ValueEntryComposite {
  return kind === "array" ? createArrayValueEntry() : createObjectValueEntry();
}

export function isValueEntryScalar(value: ValueEntry): value is ValueEntryScalar {
  return value.kind === "null" || value.kind === "boolean" || value.kind === "integer" || value.kind === "number" || value.kind === "string";
}
