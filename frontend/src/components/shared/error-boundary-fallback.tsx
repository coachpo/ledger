import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

type ErrorBoundaryFallbackProps = {
  error: Error | null;
  onReset: () => void;
};

export function ErrorBoundaryFallback({
  error,
  onReset,
}: ErrorBoundaryFallbackProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
          <AlertTriangle className="size-6" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl tracking-tight">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">
            The page hit an unexpected error while rendering.
          </p>
          {error ? (
            <p className="rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
              {error.message}
            </p>
          ) : null}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={onReset}>Try again</Button>
          <Button type="button" variant="outline" onClick={() => window.location.reload()}>
            Reload app
          </Button>
        </div>
      </div>
    </div>
  );
}
