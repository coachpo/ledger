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
