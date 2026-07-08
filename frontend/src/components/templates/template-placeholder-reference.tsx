import { Braces, ChevronDown, Loader2 } from "lucide-react";

import {
  PlaceholderGroup,
  type PlaceholderItem,
} from "@/components/templates/placeholder-group";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/components/ui/utils";
import type { PlaceholderTree } from "@/lib/types/text-template";

type PlaceholderReferenceGroup = {
  description?: string;
  items: PlaceholderItem[];
  title: string;
};

const STATIC_PLACEHOLDER_GROUPS: PlaceholderReferenceGroup[] = [
  {
    title: "Inputs",
    description:
      "Compile-time values supplied from the editor when previewing or generating a report.",
    items: [
      { path: "inputs", type: "object" },
      { path: "inputs.ticker", type: "string" },
      { path: "inputs.analysis_tag", type: "string" },
    ],
  },
  {
    title: "Report",
    items: [
      { path: "reports", type: "list" },
      { path: "reports.<name>", type: "object" },
      { path: "reports.<name>.content", type: "string" },
      { path: "reports.<name>.name", type: "string" },
      { path: "reports.<name>.created_at", type: "datetime" },
    ],
  },
  {
    title: "Dynamic Report Selectors",
    description: "Latest and tagged report selectors.",
    items: [
      { path: "reports.latest", type: "object" },
      { path: 'reports.latest("AAPL").content', type: "string" },
      { path: "reports.latest(inputs.ticker).content", type: "string" },
      { path: "reports[0].name", type: "string" },
      { path: 'reports.by_tag("weekly_review").latest', type: "object" },
      { path: "reports.by_tag(inputs.analysis_tag).latest", type: "object" },
      {
        path: 'reports.by_tag("weekly_review").latest.content',
        type: "string",
      },
    ],
  },
];

type TemplatePlaceholderReferenceProps = {
  className?: string;
  isLoading: boolean;
  onClose: () => void;
  onInsert: (path: string) => void;
  open: boolean;
  placeholderTree?: PlaceholderTree;
};

export function TemplatePlaceholderReference({
  className,
  isLoading,
  onClose,
  onInsert,
  open,
  placeholderTree,
}: TemplatePlaceholderReferenceProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className={cn(
        "shrink-0 overflow-hidden rounded-xl border border-border bg-card",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-3 py-1.5">
        <Braces className="size-3 text-muted-foreground" />
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Placeholder Reference
        </span>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          Click a path to insert it into the markdown pane.
        </span>
        {isLoading ? (
          <Loader2 className="size-3 animate-spin text-muted-foreground" />
        ) : null}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto size-6"
          onClick={onClose}
          aria-label="Collapse placeholder reference"
        >
          <ChevronDown className="size-3" />
        </Button>
      </div>
      <ScrollArea className="h-[150px] lg:h-[160px]">
        <div className="grid grid-cols-1 gap-x-4 gap-y-1 px-3 py-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {STATIC_PLACEHOLDER_GROUPS.map((group) => (
            <PlaceholderGroup
              key={group.title}
              title={group.title}
              description={group.description}
              items={group.items}
              onInsert={onInsert}
            />
          ))}

          {placeholderTree?.reports.map((report) => (
            <PlaceholderGroup
              key={report.name}
              title={report.name}
              items={[
                { path: `reports.${report.name}`, type: "object" },
                { path: `reports.${report.name}.content`, type: "string" },
              ]}
              onInsert={onInsert}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
