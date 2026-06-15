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
    <div className="min-h-screen bg-ui-canvas px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div
        className="mx-auto flex w-full max-w-6xl flex-col gap-6"
        data-testid="error-boundary-fallback-content"
      >
        <div
          className="w-full max-w-none rounded-2xl border border-border/70 bg-card/95 p-8 shadow-ui-lg"
          data-testid="error-boundary-fallback-card"
        >
          <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
            <AlertTriangle className="size-6" />
          </div>
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl tracking-tight">Something went wrong</h1>
            <p className="text-sm text-muted-foreground">
              The page hit an unexpected error while rendering.
            </p>
            {error ? (
              <p
                className="w-full max-w-4xl break-words rounded-xl border border-border/70 bg-ui-surface-grouped px-3 py-2 text-sm leading-6 text-muted-foreground"
                data-testid="error-boundary-fallback-error"
              >
                {error.message}
              </p>
            ) : null}
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button onClick={onReset}>Try again</Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => window.location.reload()}
            >
              Reload app
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
