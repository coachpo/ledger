import * as React from "react";

import { cn } from "./utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-muted-foreground/75 selection:bg-primary selection:text-primary-foreground border-input flex h-[var(--ui-size-control-md)] w-full min-w-0 rounded-md border bg-input-background px-3 py-1 text-base shadow-inner shadow-black/[0.02] outline-none transition-[background-color,border-color,color,box-shadow] duration-[var(--ui-motion-duration-base)] ease-[var(--ui-motion-ease-standard)] file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/35 dark:shadow-black/20",
        "focus-visible:border-ring focus-visible:ring-0 focus-visible:[box-shadow:var(--ui-focus-shadow)]",
        "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
