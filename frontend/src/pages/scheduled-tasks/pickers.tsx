import { useEffect, useMemo, useState } from "react";
import { CalendarIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type LocalTimeValue = {
  hour: string;
  minute: string;
};

type ScheduleTimePickerProps = {
  disabled?: boolean;
  hourTestId?: string;
  label: string;
  minuteTestId?: string;
  value: string;
  onChange: (value: string) => void;
};

type ScheduleDateTimePickerProps = {
  clearLabel: string;
  defaultTime?: string;
  disabled?: boolean;
  hourTestId?: string;
  label: string;
  labelId: string;
  minuteTestId?: string;
  placeholder: string;
  triggerId: string;
  triggerTestId?: string;
  value: string;
  onChange: (value: string) => void;
};

const DEFAULT_TIME_VALUE: LocalTimeValue = { hour: "00", minute: "00" };
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) => hour.toString().padStart(2, "0"));
const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, minute) => minute.toString().padStart(2, "0"));

function parseLocalTime(value: string): LocalTimeValue | null {
  const match = /^(?:[01]\d|2[0-3]):[0-5]\d$/.exec(value.trim());
  if (!match) {
    return null;
  }
  const [hour, minute] = value.split(":");
  return hour && minute ? { hour, minute } : null;
}

function parseLocalDateTime(value: string): { date: Date | null; time: LocalTimeValue | null } {
  const match = /^(\d{4})-(\d{2})-(\d{2})T([01]\d|2[0-3]):([0-5]\d)$/.exec(value.trim());
  if (!match) {
    return { date: null, time: null };
  }
  const year = Number.parseInt(match[1] ?? "", 10);
  const monthIndex = Number.parseInt(match[2] ?? "", 10) - 1;
  const day = Number.parseInt(match[3] ?? "", 10);
  const hour = match[4] ?? "00";
  const minute = match[5] ?? "00";
  const date = new Date(year, monthIndex, day);

  if (
    Number.isNaN(date.getTime()) ||
    date.getFullYear() !== year ||
    date.getMonth() !== monthIndex ||
    date.getDate() !== day
  ) {
    return { date: null, time: { hour, minute } };
  }

  return { date, time: { hour, minute } };
}

function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function composeLocalDateTime(date: Date, time: LocalTimeValue): string {
  return `${formatLocalDate(date)}T${time.hour}:${time.minute}`;
}

function formatDateDisplay(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function TimeSelect({
  ariaLabel,
  disabled = false,
  options,
  testId,
  value,
  onValueChange,
}: {
  ariaLabel: string;
  disabled?: boolean;
  options: string[];
  testId?: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  return (
    <Select disabled={disabled} value={value} onValueChange={onValueChange}>
      <SelectTrigger aria-label={ariaLabel} data-testid={testId} size="sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

export function ScheduleTimePicker({
  disabled = false,
  hourTestId,
  label,
  minuteTestId,
  value,
  onChange,
}: ScheduleTimePickerProps) {
  const time = useMemo(() => parseLocalTime(value) ?? DEFAULT_TIME_VALUE, [value]);

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
      <TimeSelect
        ariaLabel={`${label} hour`}
        disabled={disabled}
        options={HOUR_OPTIONS}
        testId={hourTestId}
        value={time.hour}
        onValueChange={(hour) => onChange(`${hour}:${time.minute}`)}
      />
      <span aria-hidden="true" className="text-sm text-muted-foreground">:</span>
      <TimeSelect
        ariaLabel={`${label} minute`}
        disabled={disabled}
        options={MINUTE_OPTIONS}
        testId={minuteTestId}
        value={time.minute}
        onValueChange={(minute) => onChange(`${time.hour}:${minute}`)}
      />
    </div>
  );
}

export function ScheduleDateTimePicker({
  clearLabel,
  defaultTime,
  disabled = false,
  hourTestId,
  label,
  labelId,
  minuteTestId,
  placeholder,
  triggerId,
  triggerTestId,
  value,
  onChange,
}: ScheduleDateTimePickerProps) {
  const [open, setOpen] = useState(false);
  const defaultTimeValue = useMemo(
    () => parseLocalTime(defaultTime ?? "") ?? DEFAULT_TIME_VALUE,
    [defaultTime],
  );
  const parsedValue = useMemo(() => parseLocalDateTime(value), [value]);
  const selectedDate = parsedValue.date;
  const [timeDraft, setTimeDraft] = useState<LocalTimeValue>(parsedValue.time ?? defaultTimeValue);

  useEffect(() => {
    if (parsedValue.time) {
      setTimeDraft(parsedValue.time);
      return;
    }
    if (!value) {
      setTimeDraft(defaultTimeValue);
    }
  }, [defaultTimeValue, parsedValue.time, value]);

  const triggerText = selectedDate
    ? `${formatDateDisplay(selectedDate)} · ${timeDraft.hour}:${timeDraft.minute}`
    : placeholder;

  const updateTime = (nextTime: LocalTimeValue) => {
    setTimeDraft(nextTime);
    if (selectedDate) {
      onChange(composeLocalDateTime(selectedDate, nextTime));
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          aria-labelledby={`${labelId} ${triggerId}-value`}
          className="w-full justify-start text-left font-normal data-[empty=true]:text-muted-foreground"
          data-empty={!selectedDate}
          data-testid={triggerTestId}
          disabled={disabled}
          id={triggerId}
          type="button"
          variant="outline"
        >
          <CalendarIcon data-icon="inline-start" />
          <span className="truncate" id={`${triggerId}-value`}>
            {triggerText}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <div className="flex flex-col">
          <Calendar defaultMonth={selectedDate ?? undefined} mode="single" selected={selectedDate ?? undefined} onSelect={(date) => date && onChange(composeLocalDateTime(date, timeDraft))} />
          <div className="grid gap-3 border-t p-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">Hour</Label>
              <TimeSelect
                ariaLabel={`${label} hour`}
                disabled={disabled}
                options={HOUR_OPTIONS}
                testId={hourTestId}
                value={timeDraft.hour}
                onValueChange={(hour) => updateTime({ ...timeDraft, hour })}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">Minute</Label>
              <TimeSelect
                ariaLabel={`${label} minute`}
                disabled={disabled}
                options={MINUTE_OPTIONS}
                testId={minuteTestId}
                value={timeDraft.minute}
                onValueChange={(minute) => updateTime({ ...timeDraft, minute })}
              />
            </div>
          </div>
          <div className="flex justify-end border-t p-3">
            <Button
              aria-label={clearLabel}
              disabled={disabled || !value}
              size="sm"
              type="button"
              variant="ghost"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
