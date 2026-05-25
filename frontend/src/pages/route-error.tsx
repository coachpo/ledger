import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, Home } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
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
    <main className="flex min-h-screen items-center justify-center bg-background p-6" data-testid="route-error-page">
      <div className="flex w-full max-w-2xl flex-col gap-3">
        <PageContextBar
          description="React Router redirected this route into SignalDeck's product-owned error boundary."
          meta={
            <div className="flex flex-wrap items-center gap-2">
              <ProvenanceBadge detail="error boundary" label="Surface" tone="destructive" />
              <ProvenanceBadge detail={details.eyebrow} label="Failure" tone="warning" />
            </div>
          }
          status={
            <ResourceStatusStrip
              items={[
                { label: "State", tone: "danger", value: details.statusLabel },
                { label: "Fallback", tone: "neutral", value: "Workflow packages" },
              ]}
            />
          }
          title="Route error boundary"
        />
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
          title={<h1 className="text-2xl font-semibold tracking-tight">{details.title}</h1>}
          tone="danger"
        />
      </div>
    </main>
  );
}
