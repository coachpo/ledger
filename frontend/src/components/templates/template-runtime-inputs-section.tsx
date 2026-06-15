import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/components/ui/utils";
import type { RuntimeInputRow } from "@/lib/runtime-inputs";

type TemplateRuntimeInputsSectionProps = {
  className?: string;
  open: boolean;
  rows: RuntimeInputRow[];
  onAddRow: () => void;
  onOpenChange: (open: boolean) => void;
  onRemoveRow: (rowId: string) => void;
  onUpdateRow: (rowId: string, field: "key" | "value", value: string) => void;
};

export function TemplateRuntimeInputsSection({
  className,
  open,
  rows,
  onAddRow,
  onOpenChange,
  onRemoveRow,
  onUpdateRow,
}: TemplateRuntimeInputsSectionProps) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-xl border border-border bg-card p-3",
        className,
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="min-w-0">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Runtime Inputs
          </span>
          <p className="text-xs leading-5 text-muted-foreground">
            Values resolve `inputs.*` placeholders in preview and generation.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => onOpenChange(!open)}
          >
            {open ? "Hide" : "Show"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onAddRow}
          >
            Add Input
          </Button>
        </div>
      </div>
      {open || rows.length > 0 ? (
        <div className="mt-2 flex flex-col gap-2">
          {rows.length === 0 ? (
            <p className="rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-xs italic text-muted-foreground shadow-ui-xs">
              No runtime inputs yet.
            </p>
          ) : null}
          {rows.map((row) => (
            <div
              key={row.id}
              className="grid min-w-0 gap-2 sm:grid-cols-[minmax(8rem,14rem)_minmax(0,1fr)_2rem]"
            >
              <Input
                aria-label={`Runtime input key ${row.key || row.id}`}
                value={row.key}
                onChange={(event) =>
                  onUpdateRow(row.id, "key", event.target.value)
                }
                placeholder="ticker"
                className="h-8 min-w-0 text-xs"
              />
              <Input
                aria-label={`Runtime input value ${row.key || row.id}`}
                value={row.value}
                onChange={(event) =>
                  onUpdateRow(row.id, "value", event.target.value)
                }
                placeholder="AAPL"
                className="h-8 min-w-0 text-xs"
              />
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() => onRemoveRow(row.id)}
                aria-label={`Remove runtime input ${row.key || row.id}`}
              >
                <X className="size-3" />
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
