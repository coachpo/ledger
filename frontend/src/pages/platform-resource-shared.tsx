import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

type VersionedRef = {
  key: string;
  version?: number | null;
};

export function sortByKey<T extends { key: string }>(items: readonly T[]): T[] {
  return [...items].sort((left, right) => left.key.localeCompare(right.key));
}

export function parseLineList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function toLineList(value: string[] | null | undefined): string {
  return Array.isArray(value) ? value.join("\n") : "";
}

export function stringifyJson(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  return JSON.stringify(value, null, 2);
}

export function parseJsonValue<T>(label: string, value: string, fallback: T): T {
  const trimmed = value.trim();

  if (!trimmed) {
    return fallback;
  }

  try {
    return JSON.parse(trimmed) as T;
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

export function parseRequiredText(label: string, value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }

  return trimmed;
}

export function parseOptionalNumber(
  label: string,
  value: string,
  options: { integer?: boolean; min?: number } = {},
): number | undefined {
  const trimmed = value.trim();

  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);

  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a number.`);
  }

  if (options.integer && !Number.isInteger(parsed)) {
    throw new Error(`${label} must be a whole number.`);
  }

  if (options.min !== undefined && parsed < options.min) {
    throw new Error(`${label} must be at least ${options.min}.`);
  }

  return parsed;
}

export function toVersionedRefValue(key: string, version?: number | null): string {
  return version ? `${key}@${version}` : key;
}

export function parseVersionedRef(label: string, value: string): VersionedRef {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }

  const [keyPart, versionPart] = trimmed.split("@", 2);
  const key = keyPart.trim();

  if (!key) {
    throw new Error(`${label} is required.`);
  }

  if (!versionPart) {
    return { key };
  }

  const version = Number(versionPart.trim());

  if (!Number.isInteger(version) || version <= 0) {
    throw new Error(`${label} entries must use key or key@version.`);
  }

  return { key, version };
}

export function parseVersionedRefs(label: string, value: string): VersionedRef[] {
  return parseLineList(value).map((entry) => parseVersionedRef(label, entry));
}

export function formatStatusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export function PlatformResourceBadges(props: {
  extra?: ReactNode;
  status: string;
  version?: number;
}) {
  const { extra, status, version } = props;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {typeof version === "number" ? <Badge variant="outline">v{version}</Badge> : null}
      <Badge variant="secondary" className="capitalize">
        {formatStatusLabel(status)}
      </Badge>
      {extra}
    </div>
  );
}
