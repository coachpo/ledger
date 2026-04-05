import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RuntimeInputRow } from "@/lib/runtime-inputs";

type TemplateRuntimeInputsSectionProps = {
  open: boolean;
  rows: RuntimeInputRow[];
  onAddRow: () => void;
  onOpenChange: (open: boolean) => void;
  onRemoveRow: (rowId: string) => void;
  onUpdateRow: (rowId: string, field: "key" | "value", value: string) => void;
};

export function TemplateRuntimeInputsSection({
  open,
  rows,
  onAddRow,
  onOpenChange,
  onRemoveRow,
  onUpdateRow,
}: TemplateRuntimeInputsSectionProps) {
  return (
    <div className="border-b border-border bg-muted/30 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Runtime Inputs
        </span>
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
      {open || rows.length > 0 ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">
            Reuse one template by supplying compile-time values such as `ticker`,
            `portfolio_slug`, or `analysis_tag`.
          </p>
          {rows.length === 0 ? (
            <p className="text-xs italic text-muted-foreground">
              No runtime inputs yet. Add one to parameterize this template.
            </p>
          ) : null}
          {rows.map((row) => (
            <div key={row.id} className="flex items-center gap-2">
              <Input
                value={row.key}
                onChange={(event) => onUpdateRow(row.id, "key", event.target.value)}
                placeholder="ticker"
                className="h-8 max-w-[16rem] text-xs"
              />
              <Input
                value={row.value}
                onChange={(event) => onUpdateRow(row.id, "value", event.target.value)}
                placeholder="AAPL"
                className="h-8 flex-1 text-xs"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onRemoveRow(row.id)}
                aria-label={`Remove runtime input ${row.key || row.id}`}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
