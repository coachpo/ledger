import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

export {
  parseJsonValue,
  parseLineList,
  stringifyJson,
  toLineList,
} from "@/lib/platform-authoring/common/serialization";
export {
  parseVersionedRef,
  parseVersionedRefs,
  toVersionedRefValue,
  type ResourceRef,
} from "@/lib/platform-authoring/common/resource-ref";

export function sortByKey<T extends { key: string }>(items: readonly T[]): T[] {
  return [...items].sort((left, right) => left.key.localeCompare(right.key));
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
