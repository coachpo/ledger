import { AlertTriangle } from "lucide-react";

import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
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
    <CanonicalErrorPage
      action={
        <>
          <Button onClick={onReset}>Try again</Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => window.location.reload()}
          >
            Reload app
          </Button>
        </>
      }
      contentTestId="error-boundary-fallback-content"
      description="The page hit an unexpected error while rendering."
      descriptionTestId="error-boundary-fallback-description"
      icon={<AlertTriangle className="size-4 text-destructive" />}
      meta={
        <>
          <ProvenanceBadge
            detail="error boundary"
            label="Surface"
            tone="destructive"
          />
          <ProvenanceBadge
            detail="application render"
            label="Failure"
            tone="warning"
          />
        </>
      }
      metaTestId="error-boundary-fallback-meta"
      panelDescription={
        error ? (
          <p
            className="w-full max-w-4xl break-words rounded-xl border border-border/70 bg-ui-surface-grouped px-3 py-2 text-sm leading-6 text-muted-foreground"
            data-testid="error-boundary-fallback-error"
          >
            {error.message}
          </p>
        ) : undefined
      }
      panelTestId="error-boundary-fallback-panel"
      panelTitle="Something went wrong"
      rootElement="div"
      statusItems={[
        { label: "State", tone: "danger", value: "Render failure" },
        { label: "Fallback", tone: "neutral", value: "Application shell" },
      ]}
      statusTestId="error-boundary-fallback-status"
      testId="error-boundary-fallback-page"
      title="Something went wrong"
      tone="danger"
    />
  );
}
