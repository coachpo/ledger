export type TimeZoneOption = {
  label: string;
  value: string;
};

const DEFAULT_TIME_ZONE = "UTC";
const BASE_TIME_ZONE_OPTIONS: TimeZoneOption[] = [
  { label: "UTC", value: "UTC" },
  { label: "US Eastern (America/New_York)", value: "America/New_York" },
  { label: "US Central (America/Chicago)", value: "America/Chicago" },
  { label: "US Mountain (America/Denver)", value: "America/Denver" },
  { label: "US Mountain - Arizona (America/Phoenix)", value: "America/Phoenix" },
  { label: "US Pacific (America/Los_Angeles)", value: "America/Los_Angeles" },
  { label: "US Alaska (America/Anchorage)", value: "America/Anchorage" },
  { label: "US Hawaii (Pacific/Honolulu)", value: "Pacific/Honolulu" },
  { label: "London (Europe/London)", value: "Europe/London" },
  { label: "Berlin (Europe/Berlin)", value: "Europe/Berlin" },
  { label: "Paris (Europe/Paris)", value: "Europe/Paris" },
  { label: "Madrid (Europe/Madrid)", value: "Europe/Madrid" },
  { label: "Rome (Europe/Rome)", value: "Europe/Rome" },
  { label: "Tokyo (Asia/Tokyo)", value: "Asia/Tokyo" },
  { label: "Seoul (Asia/Seoul)", value: "Asia/Seoul" },
  { label: "Shanghai (Asia/Shanghai)", value: "Asia/Shanghai" },
  { label: "Hong Kong (Asia/Hong_Kong)", value: "Asia/Hong_Kong" },
  { label: "Singapore (Asia/Singapore)", value: "Asia/Singapore" },
  { label: "Kolkata (Asia/Kolkata)", value: "Asia/Kolkata" },
  { label: "Sydney (Australia/Sydney)", value: "Australia/Sydney" },
  { label: "Melbourne (Australia/Melbourne)", value: "Australia/Melbourne" },
  { label: "Auckland (Pacific/Auckland)", value: "Pacific/Auckland" },
];

function formatFallbackTimeZoneLabel(timeZone: string): string {
  const zoneName = timeZone.split("/").at(-1)?.replaceAll("_", " ") ?? timeZone;
  return `${zoneName} (${timeZone})`;
}

function buildTimeZoneOption(value: string, suffix?: string): TimeZoneOption {
  const matchingBaseOption = BASE_TIME_ZONE_OPTIONS.find((option) => option.value === value);
  const label = matchingBaseOption?.label ?? formatFallbackTimeZoneLabel(value);
  return {
    label: suffix ? `${label} · ${suffix}` : label,
    value,
  };
}

export function resolveBrowserTimeZone(): string | null {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
}

export function getDefaultTimeZone(browserTimeZone: string | null): string {
  return browserTimeZone ?? DEFAULT_TIME_ZONE;
}

export function buildTimeZoneOptions({
  browserTimeZone,
  selectedTimeZone,
}: {
  browserTimeZone: string | null;
  selectedTimeZone?: string | null;
}): TimeZoneOption[] {
  const normalizedSelectedTimeZone = selectedTimeZone?.trim() ?? "";
  const curatedOptions = BASE_TIME_ZONE_OPTIONS.filter((option) => option.value !== browserTimeZone);

  if (!normalizedSelectedTimeZone) {
    return browserTimeZone
      ? [buildTimeZoneOption(browserTimeZone, "Current browser timezone"), ...curatedOptions]
      : curatedOptions;
  }

  const hasSelectedOption = curatedOptions.some((option) => option.value === normalizedSelectedTimeZone);
  const selectedOption =
    normalizedSelectedTimeZone !== browserTimeZone && !hasSelectedOption
      ? [buildTimeZoneOption(normalizedSelectedTimeZone, "Saved on schedule")]
      : [];

  return browserTimeZone
    ? [buildTimeZoneOption(browserTimeZone, "Current browser timezone"), ...selectedOption, ...curatedOptions]
    : [...selectedOption, ...curatedOptions];
}
