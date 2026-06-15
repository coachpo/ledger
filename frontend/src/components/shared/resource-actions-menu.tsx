import type { ComponentProps, ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/components/ui/utils";

export type ResourceActionsMenuProps = {
  align?: ComponentProps<typeof DropdownMenuContent>["align"];
  ariaLabel: string;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  disabled?: boolean;
  testId?: string;
  triggerClassName?: string;
  triggerVariant?: ComponentProps<typeof Button>["variant"];
};

export function ResourceActionsMenu({
  align = "end",
  ariaLabel,
  children,
  className,
  contentClassName,
  disabled = false,
  testId,
  triggerClassName,
  triggerVariant = "ghost",
}: ResourceActionsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={ariaLabel}
          className={cn("size-8", triggerClassName)}
          data-testid={testId}
          disabled={disabled}
          size="icon"
          type="button"
          variant={triggerVariant}
        >
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={align}
        className={cn(contentClassName, className)}
      >
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
