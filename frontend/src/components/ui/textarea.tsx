import * as React from "react";

import { cn } from "./utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "resize-none border-input placeholder:text-muted-foreground/75 aria-invalid:border-destructive aria-invalid:ring-destructive/20 flex field-sizing-content min-h-16 w-full rounded-md border bg-input-background px-3 py-2 text-base shadow-inner shadow-black/[0.02] outline-none transition-[background-color,border-color,color,box-shadow] duration-[var(--ui-motion-duration-base)] ease-[var(--ui-motion-ease-standard)] focus-visible:border-ring focus-visible:ring-0 focus-visible:[box-shadow:var(--ui-focus-shadow)] disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/35 dark:shadow-black/20 dark:aria-invalid:ring-destructive/40",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
