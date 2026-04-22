import type { FieldPath } from "./field-path";

export interface PlatformAuthoringIssue {
  field: FieldPath;
  issue: string;
}

export function createPlatformAuthoringIssue(
  field: FieldPath,
  issue: string,
): PlatformAuthoringIssue {
  return { field, issue };
}

export function toPlatformAuthoringError(issue: PlatformAuthoringIssue): Error {
  return new Error(issue.issue);
}
