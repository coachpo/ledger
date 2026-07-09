import type { ReactNode } from "react";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/components/ui/utils";

type ResourceToolbarSearchProps = {
  disabled?: boolean;
  id: string;
  label: string;
  name?: string;
  placeholder?: string;
  testId?: string;
  value: string;
  onChange: (value: string) => void;
};

export type ResourceToolbarProps = {
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  filters?: ReactNode;
  resultSummary?: ReactNode;
  search?: ResourceToolbarSearchProps;
  selectionSummary?: ReactNode;
};

function ResourceToolbarSearch({
  disabled,
  id,
  label,
  name,
  placeholder,
  testId,
  value,
  onChange,
}: ResourceToolbarSearchProps) {
  return (
    <div className="relative max-w-sm flex-1" role="search">
      <Label htmlFor={id} className="sr-only">
        {label}
      </Label>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        aria-label={label}
        className="h-[var(--ui-size-control-sm)] pl-9 text-xs"
        disabled={disabled}
        id={id}
        name={name}
        placeholder={placeholder}
        data-testid={testId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export function ResourceToolbar({
  actions,
  children,
  className,
  filters,
  resultSummary,
  search,
  selectionSummary,
}: ResourceToolbarProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-xl border border-border/70 bg-card/80 p-2 shadow-ui-xs",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {search ? <ResourceToolbarSearch {...search} /> : null}
        {filters}
        {actions ? (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {(resultSummary || selectionSummary || children) ? (
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-muted-foreground">
          <div className="min-w-0 text-xs text-muted-foreground">
            {resultSummary}
          </div>
          {selectionSummary ? (
            <div className="flex min-w-0 items-center gap-2">
              {selectionSummary}
            </div>
          ) : null}
          {children}
        </div>
      ) : null}
    </div>
  );
}
