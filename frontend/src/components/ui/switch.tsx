"use client";

import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";

import { cn } from "./utils";

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent bg-switch-background p-0.5 outline-none transition-[background-color,border-color,box-shadow] duration-[var(--ui-motion-duration-base)] data-[state=checked]:bg-primary data-[state=unchecked]:bg-switch-background focus-visible:border-ring focus-visible:ring-0 focus-visible:[box-shadow:var(--ui-focus-shadow)] disabled:cursor-not-allowed disabled:opacity-50 dark:data-[state=unchecked]:bg-input/80",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block size-4 rounded-full bg-card shadow-ui-xs ring-0 transition-transform duration-[var(--ui-motion-duration-base)] data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0 dark:data-[state=checked]:bg-primary-foreground dark:data-[state=unchecked]:bg-card-foreground",
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
