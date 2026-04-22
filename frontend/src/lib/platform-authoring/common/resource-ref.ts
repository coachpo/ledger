import { joinFieldPath, type FieldPath } from "./field-path";
import {
  createPlatformAuthoringIssue,
  toPlatformAuthoringError,
  type PlatformAuthoringIssue,
} from "./issues";
import { parseLineList } from "./serialization";

export interface ResourceRef {
  key: string;
  version: number | null;
}

function invalidResourceRefIssue(field: FieldPath, label: string): PlatformAuthoringIssue {
  return createPlatformAuthoringIssue(field, `${label} entries must use key or key@version.`);
}

function requiredResourceRefIssue(field: FieldPath, label: string): PlatformAuthoringIssue {
  return createPlatformAuthoringIssue(field, `${label} is required.`);
}

export function validateResourceRef(
  label: string,
  value: string,
  field: FieldPath = label,
): PlatformAuthoringIssue[] {
  const trimmed = value.trim();

  if (!trimmed) {
    return [requiredResourceRefIssue(field, label)];
  }

  const [keyPart, versionPart] = trimmed.split("@", 2);
  const key = keyPart.trim();

  if (!key) {
    return [requiredResourceRefIssue(field, label)];
  }

  if (!versionPart) {
    return [];
  }

  const version = Number(versionPart.trim());

  return Number.isInteger(version) && version > 0 ? [] : [invalidResourceRefIssue(field, label)];
}

export function parseResourceRef(label: string, value: string): ResourceRef {
  const [issue] = validateResourceRef(label, value);

  if (issue) {
    throw toPlatformAuthoringError(issue);
  }

  const [keyPart, versionPart] = value.trim().split("@", 2);
  const key = keyPart.trim();

  if (!versionPart) {
    return { key, version: null };
  }

  return { key, version: Number(versionPart.trim()) };
}

export function validateResourceRefs(label: string, value: string): PlatformAuthoringIssue[] {
  return parseLineList(value).flatMap((entry, index) =>
    validateResourceRef(label, entry, joinFieldPath(label, `[${index}]`)),
  );
}

export function parseResourceRefs(label: string, value: string): ResourceRef[] {
  const [issue] = validateResourceRefs(label, value);

  if (issue) {
    throw toPlatformAuthoringError(issue);
  }

  return parseLineList(value).map((entry) => parseResourceRef(label, entry));
}

export function formatResourceRef(ref: Pick<ResourceRef, "key"> & { version?: number | null }): string {
  return toVersionedRefValue(ref.key, ref.version ?? null);
}

export function toVersionedRefValue(key: string, version?: number | null): string {
  return version ? `${key}@${version}` : key;
}

export const parseVersionedRef = parseResourceRef;
export const parseVersionedRefs = parseResourceRefs;
