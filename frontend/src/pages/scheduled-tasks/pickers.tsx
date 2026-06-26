import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type ScheduleTimePickerProps = {
  disabled?: boolean;
  label: string;
  value: string;
  onChange: (value: string) => void;
};

type ScheduleDateTimePickerProps = {
  clearLabel: string;
  disabled?: boolean;
  label: string;
  labelId: string;
  placeholder: string;
  triggerId: string;
  triggerTestId?: string;
  value: string;
  onChange: (value: string) => void;
};

const DEFAULT_TIME = "00:00";
const LOCAL_TIME_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const LOCAL_DATE_TIME_RE = /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/;

function safeTime(value: string, fallback = DEFAULT_TIME): string {
  return LOCAL_TIME_RE.test(value.trim()) ? value.trim() : fallback;
}

function safeDateTime(value: string): string {
  return LOCAL_DATE_TIME_RE.test(value.trim()) ? value.trim() : "";
}

export function ScheduleTimePicker({
  disabled = false,
  label,
  value,
  onChange,
}: ScheduleTimePickerProps) {
  return (
    <Input
      aria-label={label}
      disabled={disabled}
      step={60}
      type="time"
      value={safeTime(value)}
      onChange={(event) => onChange(safeTime(event.currentTarget.value))}
    />
  );
}

export function ScheduleDateTimePicker({
  clearLabel,
  disabled = false,
  label,
  labelId,
  placeholder,
  triggerId,
  triggerTestId,
  value,
  onChange,
}: ScheduleDateTimePickerProps) {
  const normalizedValue = safeDateTime(value);

  return (
    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
      <Input
        aria-labelledby={labelId}
        aria-label={label}
        data-testid={triggerTestId}
        disabled={disabled}
        id={triggerId}
        placeholder={placeholder}
        step={60}
        type="datetime-local"
        value={normalizedValue}
        onChange={(event) => {
          const nextValue = safeDateTime(event.currentTarget.value);
          onChange(nextValue || event.currentTarget.value);
        }}
      />
      <Button
        aria-label={clearLabel}
        disabled={disabled || !value}
        size="sm"
        type="button"
        variant="ghost"
        onClick={() => onChange("")}
      >
        Clear
      </Button>
    </div>
  );
}
