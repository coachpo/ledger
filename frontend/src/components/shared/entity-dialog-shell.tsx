import type { ReactNode } from "react";

import {
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

export type EntityDialogShellProps = {
  children: ReactNode;
  className?: string;
  constraintStrip?: ReactNode;
  description?: ReactNode;
  footer: ReactNode;
  title: ReactNode;
};

export function EntityDialogShell({
  children,
  className,
  constraintStrip,
  description,
  footer,
  title,
}: EntityDialogShellProps) {
  return (
    <DialogContent
      className={cn(
        "flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl",
        className,
      )}
    >
      <DialogHeader className="shrink-0 px-5 pt-5 text-left">
        <DialogTitle>{title}</DialogTitle>
        {description ? <DialogDescription>{description}</DialogDescription> : null}
      </DialogHeader>
      {constraintStrip ? (
        <div className="shrink-0 px-5" data-slot="entity-dialog-constraint-strip">
          {constraintStrip}
        </div>
      ) : null}
      <Separator />
      <div
        className="min-h-0 flex-1 overflow-auto overscroll-contain px-5 py-4"
        data-slot="entity-dialog-body"
      >
        {children}
      </div>
      <Separator />
      <DialogFooter className="shrink-0 px-5 pb-5">{footer}</DialogFooter>
    </DialogContent>
  );
}
