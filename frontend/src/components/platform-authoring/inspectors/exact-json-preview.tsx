import { type ComponentProps } from "react";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";

type ExactJsonPreviewProps = {
  ariaLabel?: string;
  textareaClassName?: string;
  value: string;
} & ComponentProps<"div">;

export function ExactJsonPreview({
  ariaLabel = "Exact raw JSON",
  className,
  textareaClassName,
  value,
  ...props
}: ExactJsonPreviewProps) {
  return (
    <div className={cn("flex min-h-0 flex-col", className)} {...props}>
      <Textarea
        aria-label={ariaLabel}
        className={cn("min-h-72 font-mono text-xs leading-relaxed", textareaClassName)}
        readOnly
        spellCheck={false}
        value={value}
      />
    </div>
  );
}
