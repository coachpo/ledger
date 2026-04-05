import { Braces, ChevronDown, Loader2 } from "lucide-react";

import { PlaceholderGroup, type PlaceholderItem } from "@/components/templates/placeholder-group";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { PlaceholderTree } from "@/lib/types/text-template";

type PlaceholderReferenceGroup = {
  description?: string;
  items: PlaceholderItem[];
  title: string;
};

const STATIC_PLACEHOLDER_GROUPS: PlaceholderReferenceGroup[] = [
  {
    title: "Inputs",
    description: "Compile-time values supplied from the editor when previewing or generating a report.",
    items: [
      { path: "inputs", type: "object" },
      { path: "inputs.ticker", type: "string" },
      { path: "inputs.portfolio_slug", type: "string" },
      { path: "inputs.analysis_tag", type: "string" },
    ],
  },
  {
    title: "Portfolio",
    items: [
      { path: "portfolios", type: "list" },
      { path: "portfolios.<slug>", type: "object" },
      { path: "portfolios.<slug>.name", type: "string" },
      { path: "portfolios.<slug>.description", type: "string" },
      { path: "portfolios.<slug>.base_currency", type: "string" },
      { path: "portfolios.<slug>.position_count", type: "number" },
      { path: "portfolios.<slug>.balance_count", type: "number" },
      { path: "portfolios.<slug>.total_value", type: "number" },
      { path: "portfolios.<slug>.unrealized_pnl", type: "number" },
      { path: "portfolios.<slug>.created_at", type: "datetime" },
      { path: "portfolios.<slug>.updated_at", type: "datetime" },
    ],
  },
  {
    title: "Dynamic Portfolio Selectors",
    description: "Use input-driven selectors when one template should work across multiple portfolios or tickers.",
    items: [
      { path: 'portfolios.by_slug(inputs.portfolio_slug).name', type: "string" },
      { path: 'portfolios.by_slug(inputs.portfolio_slug).positions', type: "list" },
      {
        path: 'portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity',
        type: "string",
      },
      {
        path: 'portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).market_value',
        type: "number",
      },
    ],
  },
  {
    title: "Balance",
    items: [
      { path: "portfolios.<slug>.balance", type: "object" },
      { path: "portfolios.<slug>.balance.label", type: "string" },
      { path: "portfolios.<slug>.balance.amount", type: "string" },
      { path: "portfolios.<slug>.balance.operation_type", type: "string" },
      { path: "portfolios.<slug>.balance.currency", type: "string" },
    ],
  },
  {
    title: "Position",
    items: [
      { path: "portfolios.<slug>.positions", type: "list" },
      { path: "portfolios.<slug>.positions.<SYMBOL>", type: "object" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.quantity", type: "string" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.average_cost", type: "string" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.currency", type: "string" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.name", type: "string" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.market_value", type: "number" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.unrealized_pnl", type: "number" },
      { path: "portfolios.<slug>.positions.<SYMBOL>.unrealized_pnl_percent", type: "number" },
    ],
  },
  {
    title: "Report",
    description: "Exact report references stay available when you already know a saved report name.",
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
    description:
      "Use these when the latest matching report matters more than a fixed saved name. `reports[0]` is the newest report. Valid selectors that match nothing compile to an empty string.",
    items: [
      { path: "reports.latest", type: "object" },
      { path: 'reports.latest("AAPL").content', type: "string" },
      { path: 'reports.latest(inputs.ticker).content', type: "string" },
      { path: "reports[0].name", type: "string" },
      { path: 'reports.by_tag("weekly_review").latest', type: "object" },
      { path: 'reports.by_tag(inputs.analysis_tag).latest', type: "object" },
      { path: 'reports.by_tag("weekly_review").latest.content', type: "string" },
    ],
  },
];

type TemplatePlaceholderReferenceProps = {
  isLoading: boolean;
  onClose: () => void;
  onInsert: (path: string) => void;
  open: boolean;
  placeholderTree?: PlaceholderTree;
};

export function TemplatePlaceholderReference({
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
    <div className="border-t border-border">
      <div className="flex items-center gap-2 bg-muted/50 px-4 py-2">
        <Braces className="h-3 w-3 text-muted-foreground" />
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Placeholder Reference
        </span>
        {isLoading ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /> : null}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto h-5 w-5"
          onClick={onClose}
        >
          <ChevronDown className="h-3 w-3" />
        </Button>
      </div>
      <ScrollArea className="h-[220px] lg:h-[240px]">
        <div className="flex flex-wrap gap-x-8 gap-y-1 px-4 py-2">
          {STATIC_PLACEHOLDER_GROUPS.map((group) => (
            <PlaceholderGroup
              key={group.title}
              title={group.title}
              description={group.description}
              items={group.items}
              onInsert={onInsert}
            />
          ))}

          {placeholderTree?.portfolios.map((portfolio) => (
            <PlaceholderGroup
              key={portfolio.slug}
              title={portfolio.name}
              items={[
                { path: `portfolios.${portfolio.slug}`, type: "object" },
                ...portfolio.positions.map((position) => ({
                  path: `portfolios.${portfolio.slug}.positions.${position.symbol}`,
                  type: "object",
                })),
              ]}
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
