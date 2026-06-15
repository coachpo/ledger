import { cn } from "./utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-ui-surface-grouped", className)}
      {...props}
    />
  );
}

export { Skeleton };
