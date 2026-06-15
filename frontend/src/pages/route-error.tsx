import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, Home } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";

type RouteErrorDetails = {
  description: string;
  eyebrow: string;
  statusLabel: string;
  title: string;
};

function routeErrorDetails(error: unknown): RouteErrorDetails {
  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      return {
        description:
          "The route request could not find the resource it expected. Return to a known workspace route to continue.",
        eyebrow: "Route error 404",
        statusLabel: "404",
        title: "Route resource not found",
      };
    }

    return {
      description:
        "SignalDeck could not finish loading this route. Return to a known workspace route or retry after the service recovers.",
      eyebrow: `Route error ${error.status}`,
      statusLabel: String(error.status),
      title: error.statusText || "Route failed to load",
    };
  }

  if (error instanceof Error) {
    return {
      description:
        "SignalDeck hit an unexpected routed failure before this workspace could render safely.",
      eyebrow: "Route error",
      statusLabel: "Render failure",
      title: "Route failed to render",
    };
  }

  return {
    description:
      "SignalDeck received an unknown routed failure before this workspace could render safely.",
    eyebrow: "Route error",
    statusLabel: "Unknown failure",
    title: "Route failed to load",
  };
}

export function RouteErrorPage() {
  const error = useRouteError();
  const details = routeErrorDetails(error);

  return (
    <main
      className="min-h-screen bg-background px-4 py-10 sm:px-6 lg:px-8"
      data-testid="route-error-page"
    >
      <div
        className="mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-5xl flex-col justify-center gap-4"
        data-testid="route-error-content"
      >
        <header className="flex min-w-0 flex-col gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 className="max-w-3xl text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-[1.75rem]">
              {details.title}
            </h1>
            <p
              className="max-w-2xl text-sm leading-6 text-muted-foreground"
              data-testid="route-error-description"
            >
              React Router redirected this route into SignalDeck's product-owned
              error boundary.
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-3">
            <div className="min-w-0" data-testid="route-error-status">
              <ResourceStatusStrip
                className="w-fit max-w-full"
                items={[
                  {
                    label: "State",
                    tone: "danger",
                    value: details.statusLabel,
                  },
                  {
                    label: "Fallback",
                    tone: "neutral",
                    value: "Workflow packages",
                  },
                ]}
              />
            </div>
            <div
              className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground"
              data-testid="route-error-meta"
            >
              <ProvenanceBadge
                detail="error boundary"
                label="Surface"
                tone="destructive"
              />
              <ProvenanceBadge
                detail={details.eyebrow}
                label="Failure"
                tone="warning"
              />
            </div>
          </div>
        </header>
        <EmptyStatePanel
          action={
            <Button asChild size="sm">
              <Link to="/workflow-packages">
                <Home data-icon="inline-start" />
                Open workflow packages
              </Link>
            </Button>
          }
          description={details.description}
          icon={<AlertTriangle className="size-4 text-destructive" />}
          title="Route error boundary"
          tone="danger"
        />
      </div>
    </main>
  );
}
