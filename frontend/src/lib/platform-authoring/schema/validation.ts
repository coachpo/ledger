import type { FieldPath } from "../common/field-path";
import { joinFieldPath } from "../common/field-path";
import type { PlatformAuthoringIssue } from "../common/issues";
import { createPlatformAuthoringIssue } from "../common/issues";

export type SchemaValidationIssue = PlatformAuthoringIssue;

export const createSchemaValidationIssue = createPlatformAuthoringIssue;

export function joinSchemaPath(path: FieldPath, segment: string): FieldPath {
  return joinFieldPath(path, segment);
}

const UNSUPPORTED_SCHEMA_KEYWORD_MESSAGES: Record<string, string> = {
  additionalProperties: "additionalProperties is not supported; objects are closed by default",
  allowAdditionalProperties: "allowAdditionalProperties is not supported; objects are closed by default",
  allOf: "allOf is not supported",
  else: "if/then/else is not supported",
  if: "if/then/else is not supported",
  not: "not is not supported",
  oneOf: "Only discriminated anyOf unions are supported",
  patternProperties: "patternProperties is not supported",
  then: "if/then/else is not supported",
};

export function getUnsupportedSchemaKeywordMessage(keyword: string): string {
  return UNSUPPORTED_SCHEMA_KEYWORD_MESSAGES[keyword] ?? `Keyword ${JSON.stringify(keyword)} is not supported`;
}

export function isUnsupportedSchemaKeyword(keyword: string): boolean {
  return keyword in UNSUPPORTED_SCHEMA_KEYWORD_MESSAGES;
}
