import { joinFieldPath } from "../common/field-path";
import { createPlatformAuthoringIssue, type PlatformAuthoringIssue } from "../common/issues";
import type { FieldPath } from "../common/field-path";
import type {
  ValueEntry,
  ValueEntryArray,
  ValueEntryArrayItem,
  ValueEntryComposite,
  ValueEntryKind,
  ValueEntryObject,
  ValueEntryPath,
  ValueEntryScalar,
} from "./types";

export type ValueEntryValidationIssue = PlatformAuthoringIssue;

const VALUE_ENTRY_SCALAR_KINDS: readonly ValueEntryScalar["kind"][] = ["null", "boolean", "integer", "number", "string"];
const VALUE_ENTRY_COMPOSITE_KINDS: readonly ValueEntryComposite["kind"][] = ["array", "object"];

export function createValueEntryValidationIssue(field: FieldPath, issue: string): ValueEntryValidationIssue {
  return createPlatformAuthoringIssue(field, issue);
}

export function isValueEntryScalarKind(kind: ValueEntryKind): kind is ValueEntryScalar["kind"] {
  return VALUE_ENTRY_SCALAR_KINDS.includes(kind as ValueEntryScalar["kind"]);
}

export function isValueEntryCompositeKind(kind: ValueEntryKind): kind is ValueEntryComposite["kind"] {
  return VALUE_ENTRY_COMPOSITE_KINDS.includes(kind as ValueEntryComposite["kind"]);
}

export function validateValueEntryPathTokens(pathTokens: ValueEntryPath, field: FieldPath = "pathTokens"): ValueEntryValidationIssue[] {
  if (!Array.isArray(pathTokens)) {
    return [createValueEntryValidationIssue(field, "Path tokens must be an array.")];
  }

  const issues: ValueEntryValidationIssue[] = [];

  pathTokens.forEach((token, index) => {
    if (typeof token !== "string" || token.length === 0) {
      issues.push(createValueEntryValidationIssue(joinFieldPath(field, `[${index}]`), "Path tokens must be non-empty strings."));
    }
  });

  return issues;
}

export function validateValueEntryScalar(value: ValueEntryScalar, field: FieldPath = "value"): ValueEntryValidationIssue[] {
  const issues = validateValueEntryPathTokens(value.pathTokens, joinFieldPath(field, "pathTokens"));

  switch (value.kind) {
    case "null":
      if (value.value !== null) {
        issues.push(createValueEntryValidationIssue(joinFieldPath(field, "value"), "Null entries must contain a null value."));
      }
      break;
    case "boolean":
      if (typeof value.value !== "boolean") {
        issues.push(createValueEntryValidationIssue(joinFieldPath(field, "value"), "Boolean entries must contain a boolean value."));
      }
      break;
    case "integer":
      if (typeof value.value !== "number" || !Number.isInteger(value.value)) {
        issues.push(createValueEntryValidationIssue(joinFieldPath(field, "value"), "Integer entries must contain an integer value."));
      }
      break;
    case "number":
      if (typeof value.value !== "number" || Number.isNaN(value.value)) {
        issues.push(createValueEntryValidationIssue(joinFieldPath(field, "value"), "Number entries must contain a finite numeric value."));
      }
      break;
    case "string":
      if (typeof value.value !== "string") {
        issues.push(createValueEntryValidationIssue(joinFieldPath(field, "value"), "String entries must contain a string value."));
      }
      break;
  }

  return issues;
}

export function validateValueEntryArrayItem(item: ValueEntryArrayItem, field: FieldPath = "items"): ValueEntryValidationIssue[] {
  const issues = validateValueEntryPathTokens(item.pathTokens, joinFieldPath(field, "pathTokens"));

  if (!Number.isInteger(item.index) || item.index < 0) {
    issues.push(createValueEntryValidationIssue(joinFieldPath(field, "index"), "Array item indexes must be non-negative integers."));
  }

  issues.push(...validateValueEntryNode(item.value, joinFieldPath(field, "value")));
  return issues;
}

export function validateValueEntryArray(value: ValueEntryArray, field: FieldPath = "value"): ValueEntryValidationIssue[] {
  const issues = validateValueEntryPathTokens(value.pathTokens, joinFieldPath(field, "pathTokens"));

  value.items.forEach((item, index) => {
    issues.push(...validateValueEntryArrayItem(item, joinFieldPath(field, `items[${index}]`)));
  });

  return issues;
}

export function validateValueEntryObject(value: ValueEntryObject, field: FieldPath = "value"): ValueEntryValidationIssue[] {
  const issues = validateValueEntryPathTokens(value.pathTokens, joinFieldPath(field, "pathTokens"));

  value.fields.forEach((fieldEntry, index) => {
    if (typeof fieldEntry.key !== "string" || fieldEntry.key.length === 0) {
      issues.push(createValueEntryValidationIssue(joinFieldPath(field, `fields[${index}].key`), "Object field keys must be non-empty strings."));
    }

    issues.push(...validateValueEntryPathTokens(fieldEntry.pathTokens, joinFieldPath(field, `fields[${index}].pathTokens`)));
    issues.push(...validateValueEntryNode(fieldEntry.value, joinFieldPath(field, `fields[${index}].value`)));
  });

  return issues;
}

export function validateValueEntryNode(value: ValueEntry, field: FieldPath = "value"): ValueEntryValidationIssue[] {
  switch (value.kind) {
    case "null":
    case "boolean":
    case "integer":
    case "number":
    case "string":
      return validateValueEntryScalar(value, field);
    case "array":
      return validateValueEntryArray(value, field);
    case "object":
      return validateValueEntryObject(value, field);
  }
}

export function validateValueEntryKind(value: ValueEntry, expectedKinds: readonly ValueEntryKind[], field: FieldPath = "value.kind"): ValueEntryValidationIssue[] {
  if (expectedKinds.includes(value.kind)) {
    return [];
  }

  return [createValueEntryValidationIssue(field, `Expected one of ${expectedKinds.join(", ")}.`)];
}

export function validateValueEntryPrimitiveShape(value: ValueEntry, field: FieldPath = "value"): ValueEntryValidationIssue[] {
  return validateValueEntryNode(value, field);
}
