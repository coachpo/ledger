import { createArrayValueEntry, createBooleanValueEntry, createIntegerValueEntry, createNullValueEntry, createObjectValueEntry, createStringValueEntry, createNumberValueEntry, createValueEntryArrayItem, createValueEntryObjectField } from "./factories";
import { validateValueEntryNode } from "./validation";
import type { JsonPrimitive, SchemaIRPrimitive } from "../schema/types";
import type {
  ValueEntry,
  ValueEntryComposite,
  ValueEntryPath,
  ValueEntryScalar,
} from "./types";

export type ValueEntryCodecIssue = {
  path: string;
  message: string;
};

export type ValueEntryCodecResult<T> =
  | { ok: true; value: T }
  | { ok: false; issues: ValueEntryCodecIssue[] };

function toIssuePath(pathTokens: ValueEntryPath): string {
  return pathTokens.join(".");
}

function toCodecIssues(issues: ReturnType<typeof validateValueEntryNode>): ValueEntryCodecIssue[] {
  return issues.map((issue) => ({ path: issue.field, message: issue.issue }));
}

export function encodePrimitiveValueEntry(value: JsonPrimitive | null, pathTokens: ValueEntryPath = []): ValueEntryScalar {
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

export function serializeValueEntry(value: ValueEntry): JsonPrimitive | JsonPrimitive[] | Record<string, JsonPrimitive | JsonPrimitive[] | Record<string, unknown>> {
  return decodeValueEntry(value) as JsonPrimitive | JsonPrimitive[] | Record<string, JsonPrimitive | JsonPrimitive[] | Record<string, unknown>>;
}

export function validateAndDecodeValueEntry(value: ValueEntry): ValueEntryCodecResult<unknown> {
  const issues = toCodecIssues(validateValueEntryNode(value));
  if (issues.length > 0) {
    return { ok: false, issues };
  }

  return { ok: true, value: decodeValueEntry(value) };
}

export function isCodecCompatiblePrimitive(value: unknown): value is SchemaIRPrimitive {
  return value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string";
}

export function valueEntryPathToString(pathTokens: ValueEntryPath): string {
  return toIssuePath(pathTokens);
}

export function isCompositeValueEntry(value: ValueEntry): value is ValueEntryComposite {
  return value.kind === "array" || value.kind === "object";
}
