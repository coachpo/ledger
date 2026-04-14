export function sortByKey<T extends { key: string }>(items: T[]): T[] {
  return [...items].sort((left, right) => left.key.localeCompare(right.key));
}

export function parseLineList(value: string): string[] {
  return value.split(/\r?\n/).map((entry) => entry.trim()).filter(Boolean);
}

export function toLineList(value: string[] | null | undefined): string {
  return Array.isArray(value) ? value.join("\n") : "";
}

export function stringifyJson(value: unknown): string {
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

export function parseJsonValue<T>(label: string, value: string, fallback: T): T {
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  try {
    return JSON.parse(trimmed) as T;
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

export function formatOriginLabel(origin: string): string {
  return origin.charAt(0).toUpperCase() + origin.slice(1);
}

export function formatStatusLabel(status: string): string {
  return status.toLowerCase().replace(/_/g, " ");
}

export function formatKindLabel(kind: string): string {
  return kind.replace(/_/g, " ");
}
