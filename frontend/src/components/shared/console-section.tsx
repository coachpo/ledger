import type { ReactNode } from "react";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

type ConsoleSectionTone = "default" | "muted" | "warning" | "danger";
type ConsoleSectionDensity = "compact" | "comfortable";

export type ConsoleSectionProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  density?: ConsoleSectionDensity;
  description?: ReactNode;
  testId?: string;
  title: ReactNode;
  tone?: ConsoleSectionTone;
};

const sectionClassByTone: Record<ConsoleSectionTone, string> = {
  default: "",
  muted: "bg-ui-surface-grouped/70",
  warning: "border-chart-3/35 bg-chart-3/10",
  danger: "border-destructive/35 bg-destructive/5",
};

const headerClassByDensity: Record<ConsoleSectionDensity, string> = {
  compact: "px-4 pt-4",
  comfortable: "px-6 pt-6",
};

const contentClassByDensity: Record<ConsoleSectionDensity, string> = {
  compact: "px-4 pb-4",
  comfortable: "px-6 pb-6",
};

export function ConsoleSection({
  actions,
  children,
  className,
  contentClassName,
  density = "compact",
  description,
  testId,
  title,
  tone = "default",
}: ConsoleSectionProps) {
  return (
    <Card
      className={cn("gap-4", sectionClassByTone[tone], className)}
      data-testid={testId}
      data-tone={tone}
    >
      <CardHeader className={headerClassByDensity[density]}>
        <div className="min-w-0">
          <CardTitle className="text-sm font-semibold tracking-tight">
            {title}
          </CardTitle>
          {description ? (
            <CardDescription className="mt-1 text-xs leading-5">
              {description}
            </CardDescription>
          ) : null}
        </div>
        {actions ? <CardAction>{actions}</CardAction> : null}
      </CardHeader>
      <CardContent className={cn(contentClassByDensity[density], contentClassName)}>
        {children}
      </CardContent>
    </Card>
  );
}
