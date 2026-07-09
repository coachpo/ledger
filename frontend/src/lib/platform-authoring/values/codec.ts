import { createArrayValueEntry, createBooleanValueEntry, createIntegerValueEntry, createNullValueEntry, createObjectValueEntry, createStringValueEntry, createNumberValueEntry, createValueEntryArrayItem, createValueEntryObjectField } from "./factories";
import type { JsonPrimitive } from "../schema/types";
import type {
  ValueEntry,
  ValueEntryPath,
  ValueEntryScalar,
} from "./types";

function toIssuePath(pathTokens: ValueEntryPath): string {
  return pathTokens.join(".");
}

function encodePrimitiveValueEntry(value: JsonPrimitive | null, pathTokens: ValueEntryPath = []): ValueEntryScalar {
  if (value === null) {
    return createNullValueEntry(pathTokens);
  }

  switch (typeof value) {
    case "boolean":
      return createBooleanValueEntry(value, pathTokens);
    case "number":
      return Number.isInteger(value) ? createIntegerValueEntry(value, pathTokens) : createNumberValueEntry(value, pathTokens);
    case "string":
      return createStringValueEntry(value, pathTokens);
  }
}

export function encodeValueEntry(value: unknown, pathTokens: ValueEntryPath = []): ValueEntry {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return encodePrimitiveValueEntry(value, pathTokens);
  }

  if (typeof value === "number") {
    return Number.isInteger(value) ? createIntegerValueEntry(value, pathTokens) : createNumberValueEntry(value, pathTokens);
  }

  if (Array.isArray(value)) {
    return createArrayValueEntry(
      value.map((item, index) => createValueEntryArrayItem(index, encodeValueEntry(item, [...pathTokens, String(index)]), [...pathTokens, String(index)])),
      pathTokens,
    );
  }

  if (value && typeof value === "object") {
    const objectValue = value as Record<string, unknown>;
    return createObjectValueEntry(
      Object.entries(objectValue).map(([key, entryValue]) =>
        createValueEntryObjectField(key, encodeValueEntry(entryValue, [...pathTokens, key]), [...pathTokens, key]),
      ),
      pathTokens,
    );
  }

  return createStringValueEntry(String(value ?? ""), pathTokens);
}

export function decodeValueEntry(value: ValueEntry): unknown {
  switch (value.kind) {
    case "null":
    case "boolean":
    case "integer":
    case "number":
    case "string":
      return value.value;
    case "array":
      return value.items.map((item) => decodeValueEntry(item.value));
    case "object":
      return value.fields.reduce<Record<string, unknown>>((accumulator, field) => {
        accumulator[field.key] = decodeValueEntry(field.value);
        return accumulator;
      }, {});
  }
}

export function valueEntryPathToString(pathTokens: ValueEntryPath): string {
  return toIssuePath(pathTokens);
}
