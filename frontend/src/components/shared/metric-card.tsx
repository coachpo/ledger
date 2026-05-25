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
  muted: "bg-muted/30",
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
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium tracking-tight text-muted-foreground">{title}</p>
          <p className={cn("text-xl font-semibold tracking-tight text-foreground", valueClassName)}>{value}</p>
          {note ? <p className="line-clamp-1 text-[11px] text-muted-foreground">{note}</p> : null}
        </div>
        {Icon ? (
          <div className={cn("rounded-md p-1.5 text-muted-foreground", iconClassName)}>
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
          "block rounded-xl border bg-card text-card-foreground transition-shadow hover:shadow-md",
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
