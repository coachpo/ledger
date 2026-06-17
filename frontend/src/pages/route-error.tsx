import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, Home } from "lucide-react";

import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
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
    <CanonicalErrorPage
      action={
        <Button asChild size="sm">
          <Link to="/workflow-packages">
            <Home data-icon="inline-start" />
            Open workflow packages
          </Link>
        </Button>
      }
      contentTestId="route-error-content"
      description="React Router redirected this route into SignalDeck's product-owned error boundary."
      descriptionTestId="route-error-description"
      icon={<AlertTriangle className="size-4 text-destructive" />}
      meta={
        <>
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
        </>
      }
      metaTestId="route-error-meta"
      panelDescription={<p className="max-w-4xl leading-6">{details.description}</p>}
      panelTestId="route-error-panel"
      panelTitle="Route error boundary"
      rootElement="main"
      statusItems={[
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
      statusTestId="route-error-status"
      testId="route-error-page"
      title={details.title}
      tone="danger"
    />
  );
}
