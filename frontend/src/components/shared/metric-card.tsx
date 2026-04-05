import type { LucideIcon } from "lucide-react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

type MetricCardProps = {
  icon?: LucideIcon;
  iconClassName?: string;
  note?: string;
  title: string;
  to?: string;
  value: string;
  valueClassName?: string;
};

function MetricCardBody({
  icon: Icon,
  iconClassName,
  note,
  title,
  value,
  valueClassName,
}: Omit<MetricCardProps, "to">) {
  return (
    <CardContent className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium tracking-tight text-muted-foreground">
            {title}
          </p>
          <p className={cn("text-xl font-semibold tracking-tight text-foreground", valueClassName)}>{value}</p>
          {note ? <p className="text-[11px] text-muted-foreground line-clamp-1">{note}</p> : null}
        </div>
        {Icon ? (
          <div className={cn("rounded-md p-1.5 text-muted-foreground", iconClassName)}>
            <Icon className="size-4" />
          </div>
        ) : null}
      </div>
    </CardContent>
  );
}

export function MetricCard(props: MetricCardProps) {
  if (props.to) {
    return (
      <Link
        className="bg-card text-card-foreground block rounded-xl border transition-shadow hover:shadow-md"
        to={props.to}
      >
        <MetricCardBody {...props} />
      </Link>
    );
  }

  return (
    <Card>
      <MetricCardBody {...props} />
    </Card>
  );
}
