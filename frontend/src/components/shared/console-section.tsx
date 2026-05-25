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

export type ConsoleSectionTone = "default" | "muted" | "warning" | "danger";
export type ConsoleSectionDensity = "compact" | "comfortable";

export type ConsoleSectionProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  density?: ConsoleSectionDensity;
  description?: ReactNode;
  title: ReactNode;
  tone?: ConsoleSectionTone;
};

const sectionClassByTone: Record<ConsoleSectionTone, string> = {
  default: "",
  muted: "bg-muted/30",
  warning: "border-muted-foreground/40",
  danger: "border-destructive/40",
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
  density = "compact",
  description,
  title,
  tone = "default",
}: ConsoleSectionProps) {
  return (
    <Card className={cn("gap-4", sectionClassByTone[tone], className)} data-tone={tone}>
      <CardHeader className={headerClassByDensity[density]}>
        <div className="min-w-0">
          <CardTitle className="text-sm font-semibold tracking-tight">{title}</CardTitle>
          {description ? <CardDescription className="mt-1 text-xs leading-5">{description}</CardDescription> : null}
        </div>
        {actions ? <CardAction>{actions}</CardAction> : null}
      </CardHeader>
      <CardContent className={contentClassByDensity[density]}>{children}</CardContent>
    </Card>
  );
}
