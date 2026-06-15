import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type MetricCardDensity = "default" | "compact";
export type MetricCardTone = "default" | "muted";

type MetricCardProps = {
  density?: MetricCardDensity;
  footer?: ReactNode;
  icon?: LucideIcon;
  iconClassName?: string;
  note?: string;
  provenance?: ReactNode;
  status?: ReactNode;
  title: string;
  to?: string;
  tone?: MetricCardTone;
  value: string;
  valueClassName?: string;
};

const cardClassByTone: Record<MetricCardTone, string> = {
  default: "",
  muted: "bg-ui-surface-grouped/70",
};

const contentClassByDensity: Record<MetricCardDensity, string> = {
  default: "p-4",
  compact: "p-3",
};

function MetricCardBody({
  density = "default",
  footer,
  icon: Icon,
  iconClassName,
  note,
  provenance,
  status,
  title,
  value,
  valueClassName,
}: Omit<MetricCardProps, "to" | "tone">) {
  return (
    <CardContent className={contentClassByDensity[density]}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-xs font-medium tracking-tight text-muted-foreground">{title}</p>
          <p className={cn("text-xl font-semibold tracking-tight text-foreground tabular-nums", valueClassName)}>{value}</p>
          {note ? <p className="line-clamp-1 text-[11px] text-muted-foreground">{note}</p> : null}
        </div>
        {Icon ? (
          <div className={cn("rounded-lg bg-muted/50 p-1.5 text-muted-foreground", iconClassName)}>
            <Icon className="size-4" />
          </div>
        ) : null}
      </div>
      {(status || provenance) ? (
        <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2">
          {status}
          {provenance}
        </div>
      ) : null}
      {footer ? <div className="mt-3 min-w-0 text-xs text-muted-foreground">{footer}</div> : null}
    </CardContent>
  );
}

export function MetricCard(props: MetricCardProps) {
  const cardClassName = cn(cardClassByTone[props.tone ?? "default"]);

  if (props.to) {
    return (
      <Link
        className={cn(
          "block rounded-xl border border-border/70 bg-card/95 text-card-foreground shadow-ui-xs outline-none transition-[background-color,border-color,box-shadow] hover:border-border hover:bg-accent/35 hover:shadow-ui-sm focus-visible:[box-shadow:var(--ui-focus-shadow)]",
          cardClassName,
        )}
        to={props.to}
      >
        <MetricCardBody {...props} />
      </Link>
    );
  }

  return (
    <Card className={cardClassName}>
      <MetricCardBody {...props} />
    </Card>
  );
}
