import type { ReactNode } from "react";
import { LayoutGrid, List, Search, type LucideIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/components/ui/utils";

export type ResourceToolbarSearchProps = {
  disabled?: boolean;
  id: string;
  label: string;
  name?: string;
  placeholder?: string;
  testId?: string;
  value: string;
  onChange: (value: string) => void;
};

export type ResourceToolbarViewOption = {
  disabled?: boolean;
  icon?: LucideIcon;
  label: string;
  testId?: string;
  value: string;
};

export type ResourceToolbarProps = {
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  filters?: ReactNode;
  resultSummary?: ReactNode;
  search?: ResourceToolbarSearchProps;
  selectionSummary?: ReactNode;
  viewMode?: string;
  viewModes?: readonly ResourceToolbarViewOption[];
  onViewModeChange?: (value: string) => void;
};

const defaultViewModes: readonly ResourceToolbarViewOption[] = [
  { icon: LayoutGrid, label: "Cards view", value: "cards" },
  { icon: List, label: "Table view", value: "table" },
];

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
        className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        aria-label={label}
        className="h-8 pl-8 text-xs"
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

function ResourceToolbarViewToggle({
  viewMode,
  viewModes,
  onViewModeChange,
}: Pick<
  ResourceToolbarProps,
  "viewMode" | "viewModes" | "onViewModeChange"
>) {
  if (!viewMode || !onViewModeChange) {
    return null;
  }

  const options = viewModes ?? defaultViewModes;

  return (
    <ToggleGroup
      type="single"
      value={viewMode}
      onValueChange={(value) => {
        if (value) {
          onViewModeChange(value);
        }
      }}
    >
      {options.map((option) => {
        const Icon = option.icon;

        return (
          <ToggleGroupItem
            aria-label={option.label}
            className="h-8 w-8 px-0"
            data-testid={option.testId}
            disabled={option.disabled}
            key={option.value}
            value={option.value}
          >
            {Icon ? <Icon aria-hidden={true} /> : null}
          </ToggleGroupItem>
        );
      })}
    </ToggleGroup>
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
  viewMode,
  viewModes,
  onViewModeChange,
}: ResourceToolbarProps) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {search ? <ResourceToolbarSearch {...search} /> : null}
        {filters}
        <ResourceToolbarViewToggle
          viewMode={viewMode}
          viewModes={viewModes}
          onViewModeChange={onViewModeChange}
        />
        {actions ? (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {(resultSummary || selectionSummary || children) ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
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
