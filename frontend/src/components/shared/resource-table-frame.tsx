import type { ReactNode } from "react";

import { cn } from "@/components/ui/utils";

export type ResourceTableFrameProps = {
  children: ReactNode;
  className?: string;
  testId?: string;
};

export function ResourceTableFrame({
  children,
  className,
  testId,
}: ResourceTableFrameProps) {
  return (
    <div
      className={cn(
        "min-w-0 max-w-full overflow-hidden rounded-xl border border-border/70 bg-card/95 shadow-ui-xs",
        className,
      )}
      data-testid={testId}
    >
      {children}
    </div>
  );
}
