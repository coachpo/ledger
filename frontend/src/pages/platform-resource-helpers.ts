export {
  stringifyJson,
} from "@/lib/platform-authoring/common/serialization";

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
